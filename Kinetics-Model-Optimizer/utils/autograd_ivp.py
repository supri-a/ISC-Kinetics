from __future__ import absolute_import
from builtins import range

import scipy.integrate

import autograd.numpy as np
from autograd.extend import primitive, defvjp_argnums
from autograd import make_vjp
from autograd.misc import flatten
from autograd.builtins import tuple

@primitive
def solve_ivp(func, y0, t, func_args, **kwargs):
    
    def flat_func(t,y):
        return func(t, y, *func_args)

    sol = scipy.integrate.solve_ivp(flat_func, [t[0], t[-1]], y0, t_eval = t, **kwargs)
    return sol.y.T

def grad_solve_ivp(yt, func, y0, t, func_args, **kwargs):
    '''
    Mostly taken from the autograd implementation of odeint().

    '''
    
    T, D = np.shape(yt)
    flat_args, unflatten = flatten(func_args)
    
    def flat_func(t, y, flat_args):
        return func(t, y, *unflatten(flat_args))

    def unpack(x):
        #      y,      vjp_y,      vjp_t,    vjp_args
        return x[0:D], x[D:2 * D], x[2 * D], x[2 * D + 1:]

    def augmented_dynamics(t, augmented_state, flat_args):
        # Orginal system augmented with vjp_y, vjp_t and vjp_args.
        y, vjp_y, _, _ = unpack(augmented_state)
        vjp_all, dy_dt = make_vjp(flat_func, argnum=(0, 1, 2))(t, y, flat_args)
        vjp_y, vjp_t, vjp_args = vjp_all(-vjp_y)
        return np.hstack((dy_dt, vjp_y, vjp_t, vjp_args))

    def vjp_all(g):
        
        vjp_y = g[-1, :]
        vjp_t0 = 0
        time_vjp_list = []
        vjp_args = np.zeros(np.size(flat_args))
        
        for i in range(T - 1, 0, -1):

            # Compute effect of moving measurement time.
            vjp_cur_t = np.dot(func(t[i], yt[i, :], *func_args), g[i, :])
            time_vjp_list.append(vjp_cur_t)
            vjp_t0 = vjp_t0 - vjp_cur_t

            # Run augmented system backwards to the previous observation.
            aug_y0 = np.hstack((yt[i, :], vjp_y, vjp_t0, vjp_args))
            aug_ans = solve_ivp(augmented_dynamics, aug_y0, np.array([t[i], t[i - 1]]),
                            tuple((flat_args,)))
            _, vjp_y, vjp_t0, vjp_args = unpack(aug_ans[1])

            # Add gradient from current output.
            vjp_y = vjp_y + g[i - 1, :]

        time_vjp_list.append(vjp_t0)
        vjp_times = np.hstack(time_vjp_list)[::-1]

        return None, vjp_y, vjp_times, unflatten(vjp_args)
    return vjp_all


def argnums_unpack(all_vjp_builder):
    # A generic autograd helper function.  Takes a function that
    # builds vjps for all arguments, and wraps it to return only required vjps.
    def build_selected_vjps(argnums, ans, combined_args, kwargs):
        vjp_func = all_vjp_builder(ans, *combined_args, **kwargs)

        def chosen_vjps(g):  # Returns whichever vjps were asked for.
            all_vjps = vjp_func(g)
            return [all_vjps[argnum] for argnum in argnums]
        return chosen_vjps
    return build_selected_vjps

defvjp_argnums(solve_ivp, argnums_unpack(grad_solve_ivp))
# Numerics

This document covers the integrators we ship, the trade-offs between them, and when to use which.

## The big picture

We split the integrator zoo into three families:

| Family       | Examples                                       | Step control | Order | Symplectic | Stiff-friendly |
|--------------|------------------------------------------------|--------------|-------|------------|----------------|
| Adaptive     | `RK45`, `RK23`, `DOP853`, `Radau`, `BDF`, `LSODA` | adaptive   | 4-8   | no         | only `Radau`, `BDF`, `LSODA` |
| Fixed-step   | `RK4`, `Euler`                                 | fixed `dt`   | 1, 4  | no         | no             |
| Symplectic   | `leapfrog`, `velocity_verlet`, `yoshida4`      | fixed `dt`   | 2, 4  | **yes**    | no             |

All three families satisfy the same `Integrator` protocol (`integrate(rhs, t_span, y0, dt=, n_points=, rtol=, atol=)`) so callers can swap freely. The symplectic family additionally requires `grad_t_fn` and `grad_v_fn` keyword arguments — see below.

## Adaptive integrators

These are thin wrappers around `scipy.integrate.solve_ivp` (scipy >= 1.14). They handle step-size control, embedded error estimation, and dense output for resampling.

| Name      | Order | Best when                                                                 |
|-----------|-------|---------------------------------------------------------------------------|
| `RK45`    | 5(4)  | Default for non-stiff problems. The classical Dormand-Prince method.       |
| `RK23`    | 3(2)  | Loose-tolerance work where adaptive step is wanted but order isn't critical. |
| `DOP853`  | 8(5,3) | High accuracy on smooth problems. Excellent for Lorenz/Rössler at `rtol=1e-12`. |
| `Radau`   | 5     | Stiff implicit method; useful for stiff Hamiltonian or Chua-like ODEs.    |
| `BDF`     | 1-5   | Stiff variable-order method; faster than Radau on very stiff problems.    |
| `LSODA`   | adapt | Auto-detects stiffness. Convenient when you don't know in advance.        |

For Lorenz and Rössler at default parameters, `DOP853` with `rtol=1e-10, atol=1e-13` gives essentially noise-floor results.

### Calling convention

`adaptive.integrate(...)` accepts either `n_points` (uniform grid, uses scipy's dense output via `t_eval`) or `dt` (a uniform grid via `arange`), or neither (returns scipy's native step grid).

## Fixed-step integrators

For pedagogical baselines and for problems where you want bit-for-bit reproducibility independent of solver heuristics.

- **`RK4`** — Classical 4th-order Runge-Kutta. Global error :math:`O(h^4)`. With `dt=1e-3` on the harmonic oscillator it stays within `1e-7` of the analytic cosine over 10 periods.
- **`Euler`** — Explicit Euler (1st order). Included to make the order-vs.-error point in tests and examples. Diverges visibly from RK4 on the harmonic oscillator at the same step size.

Numba JIT is available via the `_NUMBA_AVAILABLE` flag in `chaotic_systems.core._numba`. Numba can't JIT through arbitrary Python `rhs` callables, so we don't blanket-decorate the integrator loops. If you want maximum throughput, JIT your RHS yourself and call the lower-level steppers directly:

```python
import numba
from chaotic_systems.integrators.fixed_step import _rk4_step

@numba.njit(cache=True)
def lorenz_rhs(t, y):
    sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
    return np.array([sigma * (y[1] - y[0]),
                     y[0] * (rho - y[2]) - y[1],
                     y[0] * y[1] - beta * y[2]])

# call _rk4_step in a numba-jitted outer loop for full speed
```

## Symplectic integrators

For *separable* Hamiltonian systems :math:`H(q, p) = T(p) + V(q)`, symplectic splitting methods preserve the canonical symplectic 2-form :math:`\omega = dq \wedge dp` exactly. The consequence — proven via backward error analysis — is that energy error is *bounded* over arbitrarily long times, not linearly drifting as it is for non-symplectic methods.

Three are exposed:

- **`velocity_verlet`** — 2nd order. The workhorse of molecular dynamics. Time-reversible. Stores `(q, p)` at the same time grid.
- **`leapfrog`** — Algebraically identical to velocity Verlet (synchronized variant).
- **`yoshida4`** — 4th order. Composition of three velocity-Verlet substeps with the coefficients from Yoshida (1990). Three times the work per step for two extra orders.

### Calling convention

Symplectic integrators don't consume a flat `rhs(t, y)`. They need the kinetic-side and potential-side gradients separately:

```python
from chaotic_systems.integrators import yoshida4, from_hamiltonian
from chaotic_systems.systems import HenonHeiles

sys = HenonHeiles()
grad_T, grad_V = from_hamiltonian(yoshida4, sys.hamiltonian)
traj = yoshida4.integrate(
    rhs=None,            # ignored
    t_span=(0.0, 1000.0),
    y0=sys.initial_state,
    dt=0.05,
    grad_t_fn=grad_T,
    grad_v_fn=grad_V,
)
```

### Performance / accuracy on the harmonic oscillator

Test setup: :math:`H = p^2/2 + q^2/2`, :math:`(q_0, p_0) = (1, 0)`, 1000 periods, `dt = 2*pi / 200` (200 steps/period).

| Integrator | max `|E - E_0|` | Notes                              |
|------------|------------------|------------------------------------|
| `velocity_verlet` | ~ 1.3e-4    | Bounded oscillation, O(dt^2).      |
| `yoshida4`        | ~ 1e-7      | Bounded oscillation, O(dt^4).      |
| `RK4`             | drifts       | Linear-in-time error growth.       |

See `tests/integrators/test_symplectic.py` for the actual assertions.

## When to use which

| Problem                                                                 | Recommended integrator     |
|-------------------------------------------------------------------------|----------------------------|
| Chaotic dissipative system, you want accuracy and speed (Lorenz, Rössler)| `DOP853` with tight tols   |
| Stiff system or you're unsure                                            | `LSODA`                    |
| Hamiltonian / conservative system, **separable** (Hénon-Heiles, SHO)     | `yoshida4` (or `velocity_verlet` if 2nd order is enough) |
| Hamiltonian system, **non-separable** (double pendulum)                  | `DOP853` with tight tols (RK isn't symplectic but the error stays small over the horizons we care about) |
| Pedagogical comparison / unit test                                       | `RK4` / `Euler`            |
| You want to JIT the inner loop yourself                                  | Roll your own around `_rk4_step` |

## Lyapunov exponent estimation

Two methods are exposed in `chaotic_systems.core.lyapunov`:

- **`largest_lyapunov_two_trajectory`** — Benettin's two-trajectory rescaling method. Robust, no Jacobian needed, gives only the largest exponent.
- **`lyapunov_spectrum`** — variational equations + continuous QR reorthonormalization. Returns the full spectrum :math:`\lambda_1 \ge \lambda_2 \ge \dots`. Requires (or finite-differences) the Jacobian.

For the Lorenz system with default parameters the two-trajectory method returns ~0.907 in about 5 seconds (see `examples/lyapunov_lorenz.py`); the canonical value is 0.9056 (Wolf et al. 1985).

## References

- E. Hairer, S. P. Nørsett, G. Wanner, *Solving Ordinary Differential Equations I: Nonstiff Problems*, 2nd ed., Springer 1993. (RK45, DOP853.)
- E. Hairer, C. Lubich, G. Wanner, *Geometric Numerical Integration*, 2nd ed., Springer 2006. (Symplectic theory.)
- H. Yoshida, *Construction of higher order symplectic integrators*, Physics Letters A 150 (1990), 262-268.
- G. Benettin, L. Galgani, A. Giorgilli, J.-M. Strelcyn, *Lyapunov Characteristic Exponents for smooth dynamical systems and for Hamiltonian systems; a method for computing all of them*, Meccanica 15 (1980), 9-30.
- A. Wolf, J. B. Swift, H. L. Swinney, J. A. Vastano, *Determining Lyapunov exponents from a time series*, Physica D 16 (1985), 285-317.

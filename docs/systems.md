# Systems

All systems live under `src/chaotic_systems/systems/`, one module per system. The registry at `chaotic_systems.systems.registry` is the public entry point used by the GUI. There are two flavours of registered system:

- **ODE flows** (`DynamicalSystem` subclasses): `list_systems()`, `list_system_names()`, `get_system(name)`.
- **Discrete maps** (`DiscreteSystem` subclasses): `list_maps()`, `list_map_names()`, `get_map(name)`.
- **Union API**: `list_all_systems()`, `get_any_system(name)`. Each instance carries a `kind` attribute (`"ode"` or `"map"`) the consumer can switch on.

The project ships **9 ODE-flow systems** and **5 discrete maps** (14 total).

## ODE flows

| Name             | State dim | Form                         | Conserved | Canonical chaotic regime                              |
|------------------|-----------|------------------------------|-----------|-------------------------------------------------------|
| `Lorenz`         | 3         | ODE                          | none      | sigma=10, rho=28, beta=8/3                            |
| `Rossler`        | 3         | ODE                          | none      | a=0.2, b=0.2, c=5.7                                   |
| `RosslerHyper`   | 4         | ODE (hyperchaotic)           | none      | a=0.25, b=3, c=0.5, d=0.05                            |
| `DoublePendulum` | 4         | Lagrangian -> ODE            | energy    | typical IC: (theta1=2.0, theta2=2.5)                  |
| `Chua`           | 3         | Piecewise-linear ODE         | none      | alpha=15.6, beta=28, m0=-1.143, m1=-0.714             |
| `HenonHeiles`    | 4         | Hamiltonian (separable)      | energy    | E ~ 0.125                                             |
| `Duffing`        | 2         | Driven 2nd-order ODE         | none      | alpha=-1, beta=1, delta=0.2, gamma=0.3, omega=1       |
| `MackeyGlass`    | 1         | Delay differential equation  | none      | beta=0.2, gamma=0.1, n=10, tau=17                     |
| `Kuramoto`       | N (=10)   | Network of phase oscillators | none      | K=1.5 (Lorentzian freq scale=0.5 => K_c=1)            |

## Discrete maps

| Name          | State dim | Form                                  | Area-preserving? | Canonical regime           |
|---------------|-----------|---------------------------------------|------------------|----------------------------|
| `Logistic`    | 1         | 1D quadratic iterate                  | no               | r=3.9                      |
| `HenonMap`    | 2         | 2D polynomial "stretch and fold"      | no (Jacobian=-b) | a=1.4, b=0.3               |
| `Ikeda`       | 2         | 2D laser-ring-cavity reduction        | no (contracting) | u=0.9                      |
| `StandardMap` | 2         | Chirikov twist map on the 2-torus     | yes (Jacobian=1) | K ≈ 0.971635 (golden-mean KAM threshold) |
| `ConradiMap`  | 2         | sin/cos of z² (trigonometric attractor) | no (dissipative; bounded to [-1,1]²) | a=5.46, b=4.55 |

---

## Lorenz '63 (`lorenz.py`)

$$\dot x = \sigma (y - x), \quad \dot y = x(\rho - z) - y, \quad \dot z = xy - \beta z.$$

The original strange attractor. Largest Lyapunov exponent ~0.9056. Kaplan-Yorke dimension ~2.062 (Sprott, *Chaos and Time-Series Analysis*, Oxford 2003, Table 5.1). State `[x, y, z]`. Default IC `[1, 1, 1]`.

Reference: E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci. 20 (1963), 130-141.

## Rössler attractor (`rossler.py`)

$$\dot x = -y - z, \quad \dot y = x + ay, \quad \dot z = b + z(x - c).$$

Simpler than Lorenz (only one nonlinearity), with a banded-spiral attractor. Largest Lyapunov exponent ~0.071. Default IC `[0.1, 0, 0]`.

Reference: O. E. Rössler, *An equation for continuous chaos*, Phys. Lett. A 57 (1976), 397-398.

## 4D Rössler hyperchaos (`rossler_hyper.py`)

$$\dot x = -y - z, \quad \dot y = x + ay + w, \quad \dot z = b + xz, \quad \dot w = -cz + dw.$$

Rössler's 1979 four-dimensional extension. The added `w` coordinate and the linear `-cz + dw` feedback produce **two positive Lyapunov exponents** — the defining feature of hyperchaos. At canonical parameters `(a, b, c, d) = (0.25, 3, 0.5, 0.05)` the measured spectrum is approximately `(+0.119, +0.017, 0.000, -21.15)`. Pair with the Diagnostics card to see the `(+, +, 0, -)` signature and a Kaplan-Yorke dimension `D_KY > 3` directly. Default IC `[-10, -6, 0, 10]`.

References: O. E. Rössler, *An equation for hyperchaos*, Phys. Lett. A 71 (1979), 155-157; T. Stankevich & D. Wilczak, *Computer-assisted proofs of existence of hyperchaotic dynamics*, Phys. Lett. A 379 (2015).

## Double pendulum (`double_pendulum.py`)

Two point masses on massless rods. Built via `LagrangianSystem` — the Euler-Lagrange equations are derived from the symbolic Lagrangian

$$L = T - V$$

with

$$T = \tfrac{1}{2}(m_1 + m_2) l_1^2 \dot\theta_1^2 + \tfrac{1}{2} m_2 l_2^2 \dot\theta_2^2 + m_2 l_1 l_2 \dot\theta_1 \dot\theta_2 \cos(\theta_1 - \theta_2),$$

$$V = -(m_1 + m_2) g l_1 \cos\theta_1 - m_2 g l_2 \cos\theta_2.$$

State `[theta1, theta2, theta1_dot, theta2_dot]`. The system is *not* separable, so symplectic splitting methods are not directly applicable; we use `DOP853` with tight tolerances. The `energy(y)` method gives the conserved total mechanical energy for verification.

Reference: L. D. Landau, E. M. Lifshitz, *Mechanics* (3rd ed.), Pergamon 1976.

## Chua's circuit (`chua.py`)

$$\dot x = \alpha(y - x - h(x)), \quad \dot y = x - y + z, \quad \dot z = -\beta y,$$

with the piecewise-linear *Chua diode*

$$h(x) = m_1 x + \tfrac{1}{2}(m_0 - m_1)(|x+1| - |x-1|).$$

The piecewise nature gives the famous "double-scroll" attractor.

Reference: T. Matsumoto, L. O. Chua, M. Komuro, *The Double Scroll*, IEEE Trans. Circuits Syst. CAS-32 (1985), 798-818.

## Hénon-Heiles (`henon_heiles.py`)

Separable Hamiltonian on $\mathbb{R}^4$:

$$H = \tfrac{1}{2}(p_x^2 + p_y^2) + \tfrac{1}{2}(x^2 + y^2) + x^2 y - \tfrac{1}{3} y^3.$$

State `[x, y, px, py]`. The system exhibits the mixed regular/chaotic phase space that motivates the Poincaré section diagnostic. Bounded for `E < 1/6`. The `.hamiltonian` property exposes the symbolic `HamiltonianSystem` so `yoshida4` can drive it.

Hénon-Heiles ships **parameter-free** — its standard form has no tunable constants, only the initial condition (which sets the energy). The GUI's parameter panel will be empty for this system; that's expected. See `examples/double_pendulum_energy.py` for an energy-conservation demo of the symplectic integrator on this system.

Reference: M. Hénon, C. Heiles, *The applicability of the third integral of motion: some numerical experiments*, Astron. J. 69 (1964), 73-79.

## Driven Duffing (`duffing.py`)

$$\ddot x + \delta \dot x + \alpha x + \beta x^3 = \gamma \cos(\omega t).$$

A canonical *forced* chaotic system; the chaos is the result of the periodic forcing rather than autonomous instability. State `[x, dot x]`. Note the system is non-autonomous (`t` appears in the RHS).

Reference: F. C. Moon, *Chaotic Vibrations*, Wiley 1987.

## Mackey-Glass DDE (`mackey_glass.py`)

$$\dot x(t) = \beta\,\frac{x(t - \tau)}{1 + x(t - \tau)^n} - \gamma\,x(t).$$

The first **delay differential equation** in the project — and the first chaotic DDE in the literature (Mackey & Glass 1977). State at any moment is the entire history segment on $[t - \tau, t]$, so the dynamics live on an *infinite-dimensional* manifold. Farmer (1982) computed the strange attractor's fractal dimension for the first time.

Canonical parameters: $\beta = 0.2$, $\gamma = 0.1$, $n = 10$, $\tau = 17$. Default IC `x(0) = 1.2`. The route to chaos as $\tau$ varies (Junges & Gallas 2012): unique fixed point for $\tau < 4.53$; Hopf bifurcation at $\tau \approx 4.53$; period-doubling cascade begins at $\tau \approx 13.3$; fully developed chaos at $\tau = 17$; hyperchaos beyond $\tau > 23$.

Implementation note: `MackeyGlass` inherits `DynamicalSystem` but overrides `simulate()` to dispatch to `chaotic_systems.integrators.dde.BellenRK4` directly, regardless of the requested integrator name. The system's `_rhs` raises if called from an ODE-only code path (the existing Lyapunov-spectrum estimator).

References: M. C. Mackey & L. Glass, *Oscillation and chaos in physiological control systems*, Science 197 (1977), 287-289; J. D. Farmer, *Chaotic attractors of an infinite-dimensional dynamical system*, Physica D 4 (1982), 366-393; E. M. Junges & J. A. C. Gallas, *Intricate routes to chaos in the Mackey-Glass delayed feedback system*, Phys. Lett. A 376 (2012), 2109-2116.

## Kuramoto N-oscillator network (`kuramoto.py`)

$$\dot\theta_i = \omega_i + \frac{K}{N} \sum_{j=1}^{N} \sin(\theta_j - \theta_i), \qquad i = 1, \dots, N.$$

The project's first **network dynamical system** — N phase oscillators with quenched random natural frequencies $\omega_i$, globally coupled with strength $K$. State vector is the phase angles $(\theta_1, \dots, \theta_N)$. As $K$ crosses the *critical coupling* $K_c$, the population undergoes a continuous phase transition from incoherence to partial synchronization, measured by the order parameter

$$r\,e^{i\psi} = \frac{1}{N} \sum_{j=1}^{N} e^{i\theta_j}.$$

For a Lorentzian frequency distribution of half-width $\gamma$, $K_c = 2\gamma$.

Canonical defaults: `N=10`, `K=1.5`, Lorentzian frequencies with `freq_scale=0.5` (so $K_c = 1.0$), seeded by `freq_seed=0` for reproducibility. The RHS uses the **mean-field reformulation** $\dot\theta_i = \omega_i + K r \sin(\psi - \theta_i)$, which is exact via the trig identity and `O(N)` instead of `O(N²)`. `N` is per-instance, not a tunable parameter — changing it would require rebuilding the solver pipeline; library callers can construct `Kuramoto(n=...)` for batched workflows.

References: Y. Kuramoto, *Self-entrainment of a population of coupled non-linear oscillators*, Int. Symp. Math. Probl. Theor. Phys. (Springer 1975), 420-422; S. H. Strogatz, *From Kuramoto to Crawford*, Physica D 143 (2000), 1-20; J. A. Acebrón et al., *The Kuramoto model: A simple paradigm for synchronization phenomena*, Rev. Mod. Phys. 77 (2005), 137-185.

## Logistic map (`logistic.py`)

$$x_{n+1} = r\,x_n (1 - x_n), \qquad x_n \in [0, 1].$$

The single-parameter logistic map is the simplest system that exhibits the *period-doubling cascade to chaos* (Feigenbaum 1978) and the canonical pedagogical entry point to discrete-time chaos (Strogatz §10.2). State `[x]`. Default `r = 3.9` (deep chaos past the period-doubling accumulation point $r_\infty \approx 3.5699$ and past the period-3 window at $r \approx 3.828$).

References: R. May, *Simple mathematical models with very complicated dynamics*, Nature 261 (1976), 459-467; M. J. Feigenbaum, *Quantitative universality for a class of nonlinear transformations*, J. Stat. Phys. 19 (1978), 25-52.

## Hénon map (`henon_map.py`)

$$x_{n+1} = 1 - a\,x_n^2 + y_n, \qquad y_{n+1} = b\,x_n.$$

The textbook 2D "stretch and fold" illustration of how a fractal *strange attractor* arises from a simple polynomial transformation. Jacobian determinant is the constant $-b$ — the map contracts area uniformly. Canonical parameters `(a, b) = (1.4, 0.3)`; Hénon (1976) reports $\lambda_1 \approx 0.42$ and $\lambda_2 \approx -1.62$ on the resulting Cantor-set-cross-arc attractor.

References: M. Hénon, *A two-dimensional mapping with a strange attractor*, Commun. Math. Phys. 50 (1976), 69-77; E. Ott, *Chaos in Dynamical Systems* (2nd ed., 2002), §4.

## Ikeda map (`ikeda.py`)

$$t_n = 0.4 - \frac{6}{1 + x_n^2 + y_n^2}, \quad x_{n+1} = 1 + u\,(x_n \cos t_n - y_n \sin t_n), \quad y_{n+1} = u\,(x_n \sin t_n + y_n \cos t_n).$$

Real-form reduction of the Ikeda (1979) model for a laser pulse in a nonlinear ring cavity. Single dissipation/gain knob `u` (Jacobian magnitude `u`). The canonical demo value `u = 0.9` yields the famous *Ikeda spiral* — a self-similar set of nested arcs. `u = 1` is area-preserving.

References: K. Ikeda, *Multiple-valued stationary state and its instability of the transmitted light by a ring cavity system*, Opt. Commun. 30 (1979), 257-261; S. M. Hammel, C. K. R. T. Jones, J. V. Moloney, *Global dynamical behavior of the optical field in a ring cavity*, J. Opt. Soc. Am. B 2 (1985), 552-564.

## Chirikov standard map (`standard_map.py`)

$$p_{n+1} = p_n + K \sin\theta_n \;(\bmod\,2\pi), \qquad \theta_{n+1} = \theta_n + p_{n+1} \;(\bmod\,2\pi).$$

The **universal local model** for near-integrable Hamiltonian dynamics in two degrees of freedom — what a generic twist map looks like near a resonance. **Area-preserving** for every `K` (Jacobian determinant identically 1). At `K = 0` the map is rigid rotation; for `K ≲ 1` KAM tori coexist with chaotic seas; the golden-mean KAM curve breaks at `K_c ≈ 0.9716354` (Greene 1979). Above $K_c$, global stochasticity. State `[theta, p]`. Default `K = 0.971635` puts the map exactly at the last-torus breakup.

References: B. V. Chirikov, *A universal instability of many-dimensional oscillator systems*, Phys. Rep. 52 (1979), 263-379; J. M. Greene, *A method for determining a stochastic transition*, J. Math. Phys. 20 (1979), 1183-1201; A. J. Lichtenberg & M. A. Lieberman, *Regular and Chaotic Dynamics* (2nd ed., 1992), §4.

---

## Adding a new system

1. Create `src/chaotic_systems/systems/<name>.py` exporting either a `DynamicalSystem` subclass (ODE flow) or a `DiscreteSystem` subclass (iterated map).
   - Set `name`, `latex`, optionally `lagrangian_latex`, `state_dim`, `parameters`, `default_initial_state`.
   - Cite the canonical reference in the module docstring.
   - Define canonical parameter values as module-level constants (`_DEFAULT_*`), not magic numbers inside the class body.
   - For ODE flows, implement `_rhs(self, t, y, params) -> ndarray`.
   - For discrete maps, implement `_step(self, y, params) -> ndarray`.
   - Add an `educational_notes` triple-quoted string with the "what / where to read / why it matters / what to try" structure used by the existing systems.
2. Register the class in `src/chaotic_systems/systems/registry.py` by adding a line to `_SYSTEM_CLASSES` (ODE) or `_MAP_CLASSES` (map). The registry instantiates each entry once at import time and surfaces it through `list_systems()` / `list_maps()` / `list_all_systems()`.
3. Add a row to the appropriate table above and a short description section below. Keep the docs and the registry in sync — that's the contract this document encodes.
4. Add `tests/systems/test_<name>.py` covering at minimum a short simulation and any conserved quantity (energy, Jacobi integral, Lyapunov-spectrum reference value, area preservation for maps, etc.).
5. For any polynomial ODE flow, consider adding a JAX-traceable RHS factory in `src/chaotic_systems/integrators/jax_backend.py` alongside the existing `lorenz_jax_rhs` / `rossler_jax_rhs` / `chua_jax_rhs` / `duffing_jax_rhs` / `rossler_hyper_jax_rhs`. This unblocks the JAX backend (I1) and the JAX basin path (D4) for the new system. Mirror the numpy `_rhs` exactly and pin parity with `tests/integrators/test_jax_polynomial_rhs.py`.

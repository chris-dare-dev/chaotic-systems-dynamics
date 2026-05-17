# Systems

All systems live under `src/chaotic_systems/systems/`, one module per system. The registry at `chaotic_systems.systems.registry` (`list_systems()`, `get_system(name)`) is the public entry point used by the GUI.

| Name           | State dim | Form                  | Conserved | Canonical chaotic regime              |
|----------------|-----------|-----------------------|-----------|---------------------------------------|
| `Lorenz`       | 3         | ODE                   | none      | sigma=10, rho=28, beta=8/3            |
| `Rossler`      | 3         | ODE                   | none      | a=0.2, b=0.2, c=5.7                   |
| `RosslerHyper` | 4         | ODE (hyperchaotic)    | none      | a=0.25, b=3, c=0.5, d=0.05            |
| `DoublePendulum` | 4       | Lagrangian -> ODE     | energy    | typical IC: (theta1=2.0, theta2=2.5)  |
| `Chua`         | 3         | Piecewise-linear ODE  | none      | alpha=15.6, beta=28, m0=-1.143, m1=-0.714 |
| `HenonHeiles`  | 4         | Hamiltonian (separable) | energy  | E ~ 0.125                              |
| `Duffing`      | 2         | driven 2nd-order ODE  | none      | alpha=-1, beta=1, delta=0.2, gamma=0.3, omega=1 |

## Lorenz '63 (`lorenz.py`)

$$\dot x = \sigma (y - x), \quad \dot y = x(\rho - z) - y, \quad \dot z = xy - \beta z.$$

The original strange attractor. Largest Lyapunov exponent ~0.9056. State `[x, y, z]`. Default IC `[1, 1, 1]`.

Reference: E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci. 20 (1963), 130-141.

## Rössler attractor (`rossler.py`)

$$\dot x = -y - z, \quad \dot y = x + ay, \quad \dot z = b + z(x - c).$$

Simpler than Lorenz (only one nonlinearity), with a banded-spiral attractor. Largest Lyapunov exponent ~0.071. Default IC `[0.1, 0, 0]`.

Reference: O. E. Rössler, *An equation for continuous chaos*, Phys. Lett. A 57 (1976), 397-398.

## 4D Rössler hyperchaos (`rossler_hyper.py`)

$$\dot x = -y - z, \quad \dot y = x + ay + w, \quad \dot z = b + xz, \quad \dot w = -cz + dw.$$

Rössler's 1979 four-dimensional extension. The added `w` coordinate and the linear `-cz + dw` feedback produce **two positive Lyapunov exponents** — the defining feature of hyperchaos. At canonical parameters `(a, b, c, d) = (0.25, 3, 0.5, 0.05)` the measured spectrum is approximately `(+0.119, +0.017, 0.000, -21.15)`. Pair with the Diagnostics card to see the `(+, +, 0, -)` signature directly. Default IC `[-10, -6, 0, 10]`.

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

Separable Hamiltonian on :math:`\mathbb{R}^4`:

$$H = \tfrac{1}{2}(p_x^2 + p_y^2) + \tfrac{1}{2}(x^2 + y^2) + x^2 y - \tfrac{1}{3} y^3.$$

State `[x, y, px, py]`. The system exhibits the mixed regular/chaotic phase space that motivates the Poincaré section diagnostic. Bounded for `E < 1/6`. The `.hamiltonian` property exposes the symbolic `HamiltonianSystem` so `yoshida4` can drive it.

Hénon-Heiles ships **parameter-free** — its standard form has no tunable constants, only the initial condition (which sets the energy). The GUI's parameter panel will be empty for this system; that's expected. See `examples/double_pendulum_energy.py` for an energy-conservation demo of the symplectic integrator on this system.

Reference: M. Hénon, C. Heiles, *The applicability of the third integral of motion: some numerical experiments*, Astron. J. 69 (1964), 73-79.

## Driven Duffing (`duffing.py`)

$$\ddot x + \delta \dot x + \alpha x + \beta x^3 = \gamma \cos(\omega t).$$

A canonical *forced* chaotic system; the chaos is the result of the periodic forcing rather than autonomous instability. State `[x, dot x]`. Note the system is non-autonomous (`t` appears in the RHS).

Reference: F. C. Moon, *Chaotic Vibrations*, Wiley 1987.

## Adding a new system

1. Create `src/chaotic_systems/systems/<name>.py` exporting a `DynamicalSystem` subclass.
   - Set `name`, `latex`, optionally `lagrangian_latex`, `state_dim`, `parameters`, `default_initial_state`.
   - Implement `_rhs(self, t, y, params) -> ndarray`.
2. Add the class to `_SYSTEMS` in `src/chaotic_systems/systems/registry.py`.
3. Add an entry to the table above and a short description below.
4. Add `tests/systems/test_<name>.py` covering at minimum a short simulation and any conserved quantity.

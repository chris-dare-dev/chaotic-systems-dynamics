# Examples

Runnable scripts that exercise the library end-to-end. Each can be run
from the repo root after `pip install -e .`:

| Script | What it does |
|---|---|
| `lyapunov_lorenz.py` | Estimate the largest Lyapunov exponent of the Lorenz attractor via Benettin's two-trajectory method. Expected output: ~0.906 vs. canonical 0.9056. |
| `lorenz_video.py [out.mp4]` | Render a 10-second MP4 of the Lorenz attractor headlessly (no display required). |
| `double_pendulum_energy.py` | Compare energy drift between adaptive RK45/DOP853 and a symplectic Yoshida-4 integrator on a Hamiltonian system. |
| `poincare_henon.py` | Compute a Poincaré section through `x = 0` on Hénon-Heiles for several initial conditions at the mixed-regime energy `E ~ 0.125`. |
| `lorenz_gui.py` | Launch the desktop GUI pre-loaded with Lorenz selected. Press `Ctrl-R` (or click `Run`) to integrate. |

```bash
python examples/lyapunov_lorenz.py
python examples/lorenz_video.py /tmp/lorenz.mp4
python examples/double_pendulum_energy.py
python examples/poincare_henon.py
python examples/lorenz_gui.py
```

None of the examples require a custom dev install — they only use the
public API surface documented in `docs/`.

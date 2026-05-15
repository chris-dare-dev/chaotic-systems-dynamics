# Security Policy

## Reporting a vulnerability

Email **me@chrisdare.net** with a description of the issue and, if possible, a minimal reproduction. Please do not file public GitHub issues for security-sensitive reports.

Expect an initial response within a few days. This is a solo, hobby-scale project, so timelines for fixes will be best-effort.

## Threat model

`chaotic-systems-dynamics` is a scientific desktop tool. The user runs it locally, with code they downloaded, against parameters they supplied. The threat model is correspondingly narrow — there is no server, no multi-tenant data, no authentication boundary.

That narrowness does not mean "no security concerns." The areas below are the ones that genuinely warrant care.

## In scope

### Parsing of user-supplied symbolic expressions

The roadmap (see `CONTEXT.md`) includes letting users define their own Lagrangians, Hamiltonians, or vector fields, likely via `sympy`. Anything that goes from a string into executable Python is a potential code-execution vector.

- **Never** use `eval()` or `exec()` on user-supplied strings.
- Use `sympy.sympify` with `evaluate=True` and an explicit, restricted symbol table. Note that `sympify` itself can execute arbitrary code if abused — pass `evaluate=True` and avoid the `locals`-as-globals pattern.
- Prefer `sympy.parsing.sympy_parser.parse_expr` with a vetted `transformations` tuple and an explicit `local_dict`.
- Code-generated vector fields (e.g. via `sympy.lambdify`) should compile from sanitized symbolic expressions, not from raw strings.

### File paths for export

Video / image export writes to disk based on user-supplied paths.

- Reject paths containing shell metacharacters when constructing `ffmpeg` commands; pass arguments as a list to `subprocess`, never via `shell=True`.
- Resolve paths and confirm they are under an expected directory (e.g. `assets/generated/` by default) before writing, when the path comes from a config or external source.
- Refuse to overwrite files outside the project unless the user explicitly opts in via a confirmation prompt.

### Dependency surface

Numerical and GUI dependencies (`numpy`, `scipy`, `sympy`, `matplotlib`, the chosen GUI toolkit, possibly `vtk` / `pyvista`, `imageio` / `ffmpeg`) are all reasonable, well-maintained projects, but each adds C/C++ surface area.

- Pin dependencies in `pyproject.toml` once chosen.
- Watch for advisories on the core stack — particularly anything in the image/video codec path (`imageio`, `Pillow`, `ffmpeg`).

### Future server-side rendering

If a remote rendering mode ever ships (deliberately out of scope today), the entire trust model changes. That work would require its own threat-model pass before landing.

## Out of scope

- Side-channel attacks against the host machine.
- Attacks that require an attacker to already have code execution on the user's machine.
- Denial-of-service via deliberately stiff systems / extreme parameters — the user can already crash their own integrator by picking bad parameters; this is a feature of letting users explore the math.
- Cryptographic correctness — no crypto is used.
- Authentication / authorization — there is no auth boundary.

## Defaults that help

- The project ships with a fixed library of well-defined systems. Custom user-defined systems are an opt-in advanced feature, gated by the parsing rules above.
- `assets/generated/` is the only directory the app writes media into by default.
- No network calls are made during simulation. Any future networked feature (e.g. shareable parameter URLs, telemetry) must be explicit and opt-in.

# PyPI Packaging Setup — Design

**Date:** 2026-04-22
**Status:** Approved

## Goal

Prepare the `mydeck` project for publication on PyPI. Migrate from the existing
`setup.py` + `setup.cfg` (which contains broken quoted metadata) to a single
PEP 621-compliant `pyproject.toml`, add a proper `LICENSE` file, and document
the release workflow.

## Package Identity

| Field         | Value                                                    |
| ------------- | -------------------------------------------------------- |
| Distribution  | `mydeck` (PyPI-normalized; `pip install mydeck`)          |
| Display name  | `MyDeck` (README headings and GitHub only)                |
| Version       | `0.1.0` (initial PyPI release)                            |
| License       | MIT — Copyright © 2026 Atsushi Kato, http://www.rwds.net/ |
| Python        | `>=3.10` (tested on Ubuntu 22.04 / 24.04 / 26.04)         |
| Author email  | `ktat.is@gmail.com`                                       |

PyPI availability was confirmed on 2026-04-22 (`/pypi/mydeck/json` → 404).
PyPI names are case- and separator-insensitive (PEP 503), so `MyDeck`,
`my-deck`, `my_deck` all normalize to the same namespace.

## File Changes

**Create:**

- `pyproject.toml` — PEP 621 metadata, setuptools build backend
- `LICENSE` — MIT license text with the copyright line above
- `MANIFEST.in` — explicit sdist inclusions/exclusions

**Delete:**

- `setup.py`
- `setup.cfg`
- `mydeck.egg-info/` (regenerated on build)
- `build/` (regenerated on build)

**Update:**

- `.gitignore` — add `dist/` and confirm `build/`, `*.egg-info/` coverage
- `README.md` / `README.ja.md` — add a "Release / Publishing" section pointing
  to the build-and-upload workflow below

## `pyproject.toml`

```toml
[project]
name = "mydeck"
version = "0.1.0"
description = "Handling STREAM DECK device — configure real devices and virtual decks in a browser"
readme = "README.md"
requires-python = ">=3.10"
license = { file = "LICENSE" }
authors = [{ name = "Atsushi Kato", email = "ktat.is@gmail.com" }]
keywords = ["streamdeck", "elgato", "keyboard", "hardware"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Operating System :: POSIX :: Linux",
  "Intended Audience :: End Users/Desktop",
  "Topic :: Multimedia",
]
dependencies = [
  "pyyaml",
  "streamdeck",
  "qrcode",
  "netifaces",
  "pidfile",
  "python-daemon",
  "psutil",
  "Pillow",
  "requests",
  "wand",
  "cairosvg",
  "pyotp",
  "pyzbar",
  "keyring",
]

[project.optional-dependencies]
dev = ["pytest", "mypy", "build", "twine"]

[project.scripts]
mydeck = "mydeck.my_decks_starter:main"

[project.urls]
Homepage = "https://github.com/ktat/mydeck"
Repository = "https://github.com/ktat/mydeck"
Issues = "https://github.com/ktat/mydeck/issues"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
mydeck = ["Assets/**/*", "html/**/*"]
```

## `MANIFEST.in`

Goal: keep sdist minimal. Include license/readme and non-Python package data;
exclude root-level scratch scripts (`c.py`, `d.py`, `t.py`, `t2.py`, `w.py`) and
build artifacts.

```
include LICENSE
include README.md
include README.ja.md
recursive-include src/mydeck/Assets *
recursive-include src/mydeck/html *
global-exclude __pycache__
global-exclude *.py[cod]
global-exclude .DS_Store
exclude c.py d.py t.py t2.py w.py run.log
prune build
prune dist
prune .mypy_cache
prune .pytest_cache
prune improvement
prune example
```

## Release Workflow (documented in README)

```bash
# Install build tooling once
pip install -e '.[dev]'

# Build sdist and wheel into dist/
python -m build

# Verify contents
tar tzf dist/mydeck-0.1.0.tar.gz | head -40
unzip -l dist/mydeck-0.1.0-py3-none-any.whl

# Upload to TestPyPI first
twine upload --repository testpypi dist/*

# Verify a fresh install works
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            mydeck

# Upload to production PyPI
twine upload dist/*
```

Credentials are stored in `~/.pypirc` or provided via `TWINE_USERNAME` /
`TWINE_PASSWORD` env vars (use `__token__` + API token from pypi.org account
settings).

## Verification Checklist

1. `python -m build` emits `dist/mydeck-0.1.0.tar.gz` and
   `dist/mydeck-0.1.0-py3-none-any.whl` without warnings.
2. `tar tzf dist/mydeck-0.1.0.tar.gz` includes `LICENSE`, `README.md`,
   `src/mydeck/Assets/...`, and `src/mydeck/html/...`.
3. `tar tzf` does **not** include `c.py`, `t.py`, `t2.py`, `w.py`, `d.py`,
   `run.log`, `build/`, `improvement/`, `example/`.
4. `twine check dist/*` passes.
5. In a fresh virtualenv, `pip install dist/mydeck-0.1.0-py3-none-any.whl`
   succeeds and the `mydeck` console entry point is on `$PATH`.
6. `mydeck --help` (or equivalent) runs without import errors — smoke test
   that package_data is correctly located.
7. TestPyPI upload succeeds and a fresh install from TestPyPI reproduces 5 & 6.

## Out of Scope

- GitHub Actions / Trusted Publishing automation (may be a follow-up).
- Splitting optional Linux-only dependencies (e.g., `netifaces`, `python-daemon`)
  behind platform markers — current deps are kept as-is.
- Version bump strategy for subsequent releases.

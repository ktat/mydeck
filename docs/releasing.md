# Releasing MyDeck to PyPI

Maintainer-only. This document describes how to cut a new release of `mydeck`
and publish it to PyPI.

## Prerequisites

- A PyPI account with upload rights for the `mydeck` project.
- A TestPyPI account (used for rehearsal uploads).
- An API token for each, stored in `~/.pypirc`:

  ```ini
  [distutils]
  index-servers =
      pypi
      testpypi

  [pypi]
  username = __token__
  password = pypi-<your-token>

  [testpypi]
  repository = https://test.pypi.org/legacy/
  username = __token__
  password = pypi-<your-token>
  ```

  Alternatively, set `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<token>`
  for the active shell.

## Release Steps

1. **Bump the version** in `pyproject.toml` (`project.version`) and commit.

2. **Clean previous artifacts:**

   ```sh
   rm -rf dist/ build/ src/*.egg-info/
   ```

3. **Set up a build environment** (once per machine):

   ```sh
   python3 -m venv .venv-build
   .venv-build/bin/pip install --upgrade build twine
   ```

4. **Build sdist and wheel:**

   ```sh
   .venv-build/bin/python -m build
   ```

   Expected output: `dist/mydeck-<version>.tar.gz` and
   `dist/mydeck-<version>-py3-none-any.whl`.

5. **Verify the artifacts:**

   ```sh
   .venv-build/bin/twine check dist/*
   tar tzf dist/mydeck-<version>.tar.gz | head -20
   ```

   Confirm `LICENSE`, `README.md`, `src/mydeck/Assets/`, and `src/mydeck/html/`
   are present.

6. **Upload to TestPyPI first:**

   ```sh
   .venv-build/bin/twine upload --repository testpypi dist/*
   ```

7. **Smoke-test the TestPyPI release** in a fresh virtualenv:

   ```sh
   python3 -m venv /tmp/mydeck-smoke
   /tmp/mydeck-smoke/bin/pip install \
       --index-url https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ \
       mydeck
   /tmp/mydeck-smoke/bin/mydeck --help
   ```

8. **Upload to production PyPI:**

   ```sh
   .venv-build/bin/twine upload dist/*
   ```

9. **Tag the release** and push:

   ```sh
   git tag -a v<version> -m "Release v<version>"
   git push origin v<version>
   ```

## Troubleshooting

- **`File already exists` on upload** — PyPI does not allow re-uploading the
  same version. Bump `project.version` and rebuild.
- **Missing `Assets/` or `html/` files in wheel** — re-check
  `[tool.setuptools.package-data]` in `pyproject.toml` and rebuild with a
  clean `dist/` and `build/`.

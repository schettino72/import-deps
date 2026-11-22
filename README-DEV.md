# Development

## Setup

Installs the package (editable) and all dev tools (pytest, coverage, doit, pyflakes, twine).
Dev tools are a [dependency group](https://packaging.python.org/en/latest/specifications/dependency-groups/)
named `dev` in `pyproject.toml`.

With pip (requires pip >= 25.1 for `--group`):

```bash
python -m venv .venv
source .venv/bin/activate         # fish: source .venv/bin/activate.fish
pip install --upgrade pip
pip install -e . --group dev
```

Or with uv (creates `.venv`, installs the `dev` group by default):

```bash
uv sync
```

## Running tests

With the venv activated:

```bash
pytest
```

Or with uv, without activating: `uv run pytest`

## Release

1. Update version in `pyproject.toml` and `import_deps/__init__.py`
2. Update `CHANGES` with release date
3. Build the package:

```bash
rm -f dist/*
python -m build      # needs: pip install build
# or: uv build
```

4. Upload to PyPI (venv activated):

```bash
twine upload dist/*
```

twine reads the token from `~/.pypirc` (`username = __token__`, `password = pypi-...`).

Or with uv: `uv publish --token <token>` (or set `UV_PUBLISH_TOKEN`).
uv does not read `~/.pypirc`.

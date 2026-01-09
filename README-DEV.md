# Development

## Setup

```bash
uv sync
```

## Running tests

```bash
pytest
```

## Release

1. Update version in `pyproject.toml` and `import_deps/__init__.py`
2. Update `CHANGES` with release date
3. Build the package:

```bash
rm -f dist/*
uv build
```

4. Upload to PyPI:

```bash
uv publish
```

Or with twine: `twine upload dist/*`

For authentication, set `UV_PUBLISH_TOKEN` env var or use `--token` flag.

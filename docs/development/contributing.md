# Contributing

## Design goals

- Docsub is not a type checker.
- Type annotation patterns that are too complex to express reasonably in docstrings, won't be supported.
  For these cases, docstub encourages fallback mechanisms (like inline annotations, or creating a stub file manually).


## Bug reports, feature requests and feedback

Head over to [docstub's issue tracker](https://github.com/scientific-python/docstub/issues) and feel very welcome to open an issue!


## Development workflow

This section assumes familiarity with Python development.
For a more general introduction you can check out [Scientific Python's Intro to development](https://learn.scientific-python.org/development/tutorials/dev-environment/).


### Setup a development environment

Create a [fork of docstub](https://github.com/scientific-python/docstub/fork) and clone your fork.
The following sections assume that you are running a shell inside that cloned project folder (`docstub/`).

```shell
pip install --group dev --editable .
pre-commit install
```


### Run tests

Run test suite and doctests:

```shell
python -m pytest
```

Check stub files for docstub:

```shell
python -m mypy.stubtest \
    --mypy-config-file "pyproject.toml" \
    --allowlist "stubtest_allow.txt" \
    docstub
```

Type check test suite:

```shell
python -m mypy "tests/"
python -m basedpyright "tests/"
```

Before committing you can also perform all linting checks explicitly with

```shell
pre-commit run --all
```


### Build the documentation

```shell
python -m sphinx --fresh-env --nitpicky --fail-on-warning "docs/" "docs/build/"
```

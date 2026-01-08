# Contributing

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


## Design goals

- Docstub is not a type checker.
- Docstub is not a linter.
- Docstub aims for readable type descriptions in docstrings.
  It should not introduce more complexity in docstrings than if [Python-native annotations](https://typing.python.org/en/latest/spec/glossary.html#term-annotation-expression) were used.
- Docstub encourages fallback mechanisms like inline annotations, or creating a stub file manually.
  This helps with cases that would have a poor readability in docstrings, would be very complex, or are not supported.

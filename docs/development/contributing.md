# Contributing

Thanks for trying out docstub and being interested in contributing!
We'd greatly appreciate feedback and bug reports, as well as pointers to where the documentation is confusing and unclear.

Our project follows [Scientific Python's Code of Conduct](https://scientific-python.org/code_of_conduct/).


## Reaching out

For bug reports, feature requests and feedback, head over to [docstub's issue tracker](https://github.com/scientific-python/docstub/issues) and feel very welcome to open an issue! 🚀

Before creating a feature request it might be useful to reference our [design guide](design.md), specifically our [goals](design.md#goals).


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

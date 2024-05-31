# docstub

> [!NOTE]
> In early development!

A command line tool to generate Python stub files (PYI) from type descriptions
in NumPyDoc style docstrings.


## Installation

```shell
pip install 'docstub [optional] @ git+https://github.com/lagru/docstub'
```


## Usage & configuration

```shell
docstub example/example_pkg/
```
will create stub files for `example_pkg/` in `example/example_pkg-stubs/`.
For now, refer to `docstub --help` for more.


### Declare imports and synonyms

Types in docstrings can and are used without having to import them. However,
when docstub creates stub files from these docstrings it actually needs to
know how to import those unknown types.

> [!TIP]
> docstub already knows about types in Python's `typing` or `collections.abc`
> modules. That means you can just use types like `Literal` or `Sequence`.

For now docstub's relies on users to declare unknown types[^static-analysis]
in a `docstub.toml` or `pyproject.toml` like this:
```toml
[tool.docstub.docnames]
np = { import = "numpy", as = "np" }
```
With this declaration, you can safely use things that are available in the
`numpy` namespace. E.g. docstub will recognize that `np.uint8` requires
`import numpy as np` and will include it in stub files if necessary.

docstub uses the keys of the `docnames` map to match unknown names used in
docstrings. So
```toml
[tool.docstub.docnames]
func = { use = "Callable", from = "typing" }
```
will allow using `func` as a synonym for `Callable`.

[^static-analysis]: Static and possibly runtime analysis to automatically find
                    unknown types is on the roadmap.


## Contributing

TBD


## Acknowledgements

Thanks to [docs2stubs](https://github.com/gramster/docs2stubs) by which this
project was heavily inspired and influenced.

# docstub

> [!NOTE]
> In early development!

A command line tool to generate Python stub files (PYI) from type descriptions
in NumPyDoc style docstrings.


## Installation

To try out docstub, for now, we recommend installing docstub directly from this
repo:

```shell
pip install 'docstub [optional] @ git+https://github.com/scientific-python/docstub'
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

While docstub is smart enough to find some types via static analysis of
definitions in the given source directory, it must be told about other types
for now. To do so, refer to the syntax and comments in the
`default_config.toml`.


## Contributing

TBD


## Acknowledgements

Thanks to [docs2stubs](https://github.com/gramster/docs2stubs) by which this
project was heavily inspired and influenced.

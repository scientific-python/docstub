# Installation

Docstub is available as a [package on PyPI](https://pypi.org/project/docstub/) and can be installed from there with your favorite package manager.
For example:

```shell
pip install docstub
```

For static analysis, docstub does not need to be installed in the same Python environment as your project!
You can use an isolated environment for docstub.
So things like `pipx run docstub` or `uv tool run docstub` will work, too.


## Development version

In case you want to check out an unreleased version you can install the latest version directly from the repository with:

```shell
pip install 'docstub @ git+https://github.com/scientific-python/docstub'
```

You can append `@COMMIT_SHA` to the repository URL above to intall a specific version other that the `main` branch.

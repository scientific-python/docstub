# Configuration files

Docstub will automatically look for configuration files in the current directory.
These files must be named

- `pyproject.toml`
- `docstub.toml`

Alternatively, config files can also be passed in the command line with the `--config` option.
In this case, docstub will not look for configuration files in the current directory.
When multiple configuration files are passed explicitly, their content is merged.

Out of the box, docstub makes use of an internal configuration files are always loaded.
One such file is [`numpy_config.toml`](../src/docstub/numpy_config.toml) which provides defaults for NumPy types.


## Configuration fields in `[tool.docstub]`

All configuration must be declared inside a `[tool.docstub]` table.


### `ignore_files`

[TOML type](https://toml.io/en/latest): array of string(s)

Ignore files and directories matching these [glob-style patterns](https://docs.python.org/3/library/glob.html#glob.translate).
Patterns that don't start with "/" are interpreted as relative to the
directory that contains the Python package for which stubs are generated.

Example:

```toml
[tool.docstub]
ignore_files = [
    "**/tests",
]
```

- Will ignore any directory anywhere that is named `tests`.


### `types`

[TOML type](https://toml.io/en/latest): table, mapping string to string

Types and their external modules to use in docstrings.
Docstub can't yet automatically discover where to import types from other packages from.
Instead, you can provide this information explicitly.
Any type on the left side will be associated with the given "module" on the right side.

Example:

```toml
[tool.docstub.types]
Path = "pathlib"
NDArray = "numpy.typing"
```

- Will allow using `Path` in docstrings and will use `from pathlib import Path` to import the type.
- Will allow using `NDarray` in docstrings and will use `from numpy.typing import NDArray` to import the type.


### `type_prefixes`

[TOML type](https://toml.io/en/latest): table, mapping string to string

Prefixes for external modules to match types in docstrings.
Docstub can't yet automatically discover where to import types from other packages from.
Instead, you can provide this information explicitly.
Any type in a docstring whose prefix matches the name given on the left side, will be associated with the given "module" on the right side.

Example:

```toml
[tool.docstub.type_prefixes]
np = "numpy"
plt = "matplotlib.pyplot
```

- Will match `np.uint8` and `np.typing.NDarray` and use `import numpy as np`.
- Will match `plt.Figure` use `import matplotlib.pyplot as plt`.


### `type_nicknames`

[TOML type](https://toml.io/en/latest): table, mapping string to string

Nicknames for types that can be used in docstrings to describe valid Python types or annotations.

Example:

```toml
[tool.docstub.type_nicknames]
func = "Callable"
buffer = "collections.abc.Buffer"
```

- Will map `func` to the `Callable`.
- Will map `buffer` to `collections.abc.Buffer`.

# Configuration

Docstub will automatically look for the following configuration files in the current directory:

- `pyproject.toml`
- `docstub.toml`
- `docstub.py`

We recommend using the TOML format for configuration files unless you need to use the Python format to provide your own [](#doctype_transformer).

Alternatively, config files can also be passed in the command line with the `--config` option.
In this case, docstub will **not** look for configuration files in the current directory.

When multiple configuration files are found/used, their content is merged in order.
In case of conflicts, the later file takes precedence.

Docstub also uses internal configuration files.
One such file is [`numpy_config.toml`](../src/docstub/numpy_config.toml) which provides defaults for NumPy types.


## Configuration fields

All configuration must be declared inside a `[tool.docstub]` table when using the TOML format.
With the Python format, these must be symbols defined at the global module scope.


### `ignore_files`

[TOML type](https://toml.io/en/latest): array of string(s)

Ignore files and directories matching these [glob-style patterns](https://docs.python.org/3/library/glob.html#glob.translate).
Patterns that don't start with "/" are interpreted as relative to the
directory that contains the Python package for which stubs are generated.

**Example:**

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

**Example:**

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

**Example:**

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

**Example:**

```toml
[tool.docstub.type_nicknames]
func = "Callable"
buffer = "collections.abc.Buffer"
```

- Will map `func` to the `Callable`.
- Will map `buffer` to `collections.abc.Buffer`.


### `doctype_grammar`

[TOML type](https://toml.io/en/latest): string

Override the default grammar with your own.
You can import, override and extend rules and terminals from "doctype.lark".
Note that if your grammar results in a modified tree, you need to implement a [custom transformer](#doctype_transformer) as well.

**Example:**

```toml
[tool.docstub]
grammar = """
%import doctype (start, WS_INLINE, ARRAY_NAME)

%extend ARRAY_NAME: "darray" 

%ignore WS_INLINE
"""
```

- Will allow using [array expressions](#natlang-array) with the term ``darray`` in addition to existing ones.


### `doctype_transformer`

Python type: {class}`lark.visitors.Transformer`

Provide your own class to transform the parsed doctype tree into a valid {term}`annotation expression`.

:::{note}
Only supported in `docstub.py` files!
:::

**Example:**

```python
# docstub.py

import lark.visitors
from docstub._doctype import DoctypeTransformer, Expr

@lark.visitors.v_args(tree=True)
class MyTransformer(DoctypeTransformer):
    def union(self, tree: lark.Tree) -> Expr:
        # Sort items in union alphabetically
        tree.children = sorted(tree.children, key=str)
        out = super().union(tree)
        return out

doctype_transformer = MyTransformer  # Declare the configuration field
```

- Will sort all members of a union alphabetically, regardless of order in the docstring.

# Create a plugin

Docstub has experimental support for plugins: standalone Python files that implement a set of hooks to reach directly into Docstub's runtime.
Plugins are loaded via the configuration field [`plugin_paths`](#plugin-paths).

For a reference of all available hooks see {mod}`docstub.plugins`.


## Example: Allow another name in array expressions

We want to expand docstub such that we can use `my_array` inside [array expressions](#natlang-array) like this:

- `my_array of dtype int` → `my_array[int]`
- `my_array of shape (4, 4)` → `my_array`

First we create the plugin:

```python
# my_array_plugin.py

from docstub.plugins import hookimpl

GRAMMAR = """
%import doctype (start, WS_INLINE, ARRAY_NAME)
%extend ARRAY_NAME: "my_array"
%ignore WS_INLINE
"""


@hookimpl
def docstub_load_doctype_grammar():
    return GRAMMAR
```

The enable the plugin in the configuration:

```toml
[tool.docstub]
plugin_paths = ["path/to/my_array_plugin.py"]
```


## Example: Expansion expression for qualnames

We want to expand docstub such that the following doctype transformations are possible

- `{Iterable, Sequence} of int(s)` → `Iterable[int] | Sequence[int]`
- `{list, set} of {int, float}` → `list[int] | list[float] | set[int] | set[float]`

First we create the plugin:

```python
# expansion_plugin.py

from itertools import product

import lark
from docstub.plugins import hookimpl
from docstub.doctype import DoctypeTransformer, Expr, Term, expand_expression

GRAMMAR = """
%import doctype (start, WS_INLINE, qualname)
%extend qualname: "{" qualname ("," qualname)+ "}" -> expansion
%ignore WS_INLINE
"""


@lark.visitors.v_args(tree=True)
class ExpansionTransformer(DoctypeTransformer):
    def start(self, tree):
        """Transform "start" rule.

        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        expr : Expr
        """
        assert len(tree.children) == 1
        child = expand_expression(tree.children[0], expand_rule="expansion")
        return Expr(rule="start", children=(child,))


@hookimpl
def docstub_load_doctype_grammar():
    return GRAMMAR


@hookimpl
def docstub_load_doctype_transformer():
    return ExpansionTransformer()
```

The enable the plugin in the configuration:

```toml
[tool.docstub]
plugin_paths = ["path/to/expansion_plugin.py"]
```

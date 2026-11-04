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

from itertools import product

import lark
from docstub.plugins import hookimpl
from docstub.doctype import DoctypeTransformer, Expr, Term

my_grammar = """
%import doctype (start, WS_INLINE, ARRAY_NAME)

%extend ARRAY_NAME: "my_array"

%ignore WS_INLINE
"""


@hookimpl
def docstub_load_doctype_grammar():
    return my_grammar
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
from docstub.doctype import DoctypeTransformer, Expr, Term

my_grammar = """
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
        children = map(self._expand_expression, tree.children)
        return Expr(rule="start", children=tuple(children))

    def expansion(self, tree):
        """Transform "expansion" rule.

        Actual expansion happens in `start` when the complete expression with
        all potential expansions can be seen.

        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        expr : Expr
        """
        return Expr(rule="expansion", children=tuple(tree.children))

    def _expand_expression(self, expr):
        """Join combination of all expansions in a new union.

        Parameters
        ----------
        expr : Expr

        Returns
        -------
        expanded : Expr
        """
        expansions = expr.filter(rule="expansion")
        if not expansions:
            return expr

        # Create Cartesian product of all expansions where each
        # value is prefixed by the expansion it will replace
        expansions = [
            [(expansion, value) for value in expansion.children]
            for expansion in expansions
        ]
        combinations = list(product(*expansions))

        # Create a new expression for each combination
        interpolated = []
        for combination in combinations:
            new_expr = expr
            for expansion, value in combination:
                new_expr = new_expr.replace(expansion, value)
            interpolated.append(new_expr)

        # Join new expressions as union
        expanded = self.union(lark.Tree("union", children=interpolated))
        return expanded


@hookimpl
def docstub_load_doctype_grammar():
    return my_grammar


@hookimpl
def docstub_load_doctype_transformer():
    return ExpansionTransformer()
```

The enable the plugin in the configuration:

```toml
[tool.docstub]
plugin_paths = ["path/to/expansion_plugin.py"]
```

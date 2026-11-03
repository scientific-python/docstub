# Writing a plugin for docstub

Docstub has experimental support for plugins.
A plugin is a simple Python file that implements a subset of supported hooks.
Plugins are loaded via the configuration field `plugin_files`.


## Example: Implement custom array expression

```python
# 
from docstub.plugins import hookimpl

my_grammar = """
%import doctype (start, WS_INLINE, natlang_array, shape, array_name)

%extend natlang_array: shape array_name

%ignore WS_INLINE
"""

@hookimpl
def docstub_load_doctype_grammar():
    return my_grammar
```

"""Docstub's plugin interface.

The functions prefixed with ``docstub_`` declare hooks that can be implemented
by plugins. To create a hook, create a function with the same signature and
decorate it with ``hookimpl``:

>>> from docstub.plugins import hookimpl
...
>>> @hookimpl
... def docstub_load_doctype_grammar():
...     return "my grammar..."

Attributes
----------
hookimpl : Final[pluggy.HookimplMarker]
"""

import pluggy

_hookspec: pluggy.HookspecMarker = pluggy.HookspecMarker("docstub")

hookimpl = pluggy.HookimplMarker("docstub")


@_hookspec(firstresult=True)
def docstub_load_doctype_grammar():
    """Override the default doctype grammar.

    You can import from doctype's default grammar with::

        %import doctype (start, WS_INLINE, ...)
        %ignore WS_INLINE

    Returns
    -------
    grammar : str
        The custom grammar to use for parsing doctypes.
    """


@_hookspec(firstresult=True)
def docstub_load_doctype_transformer():
    """Override the default transformer for the doctype grammar.

    Returns
    -------
    transformer : ~.DoctypeTransformer
        Rules must return :class:`~.Expr`, and :class:`~.Term` objects.
        Must be pickle-able.
    """

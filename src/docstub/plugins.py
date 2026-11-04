"""Docstub's plugin interface.

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

        %import doctype (start, ...)

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

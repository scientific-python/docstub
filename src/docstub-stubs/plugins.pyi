# File generated with docstub

from typing import Final

import pluggy

from .doctype import DoctypeTransformer

_hookspec: pluggy.HookspecMarker

hookimpl: Final[pluggy.HookimplMarker]

def docstub_load_doctype_grammar() -> str: ...
def docstub_load_doctype_transformer() -> DoctypeTransformer: ...

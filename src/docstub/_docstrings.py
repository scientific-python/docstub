"""Transform types defined in docstrings to Python parsable types.

"""

import logging
from dataclasses import dataclass
from pathlib import Path

import lark
import lark.visitors
from numpydoc.docscrape import NumpyDocString

from ._analysis import DocName

logger = logging.getLogger(__name__)


here = Path(__file__).parent
grammar_path = here / "doctype.lark"


def _find_one_token(tree, token_name):
    tokens = [child for child in tree.children if child.type == token_name]
    if len(tokens) != 1:
        raise ValueError(
            f"expected exactly one Token of type {token_name}, found {len(tokens)}"
        )
    return tokens[0]


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):
    """Transform docstring type descriptions (doctypes)."""

    def __init__(self, docnames, **kwargs):
        self.docnames = docnames
        self._collected_imports = None
        super().__init__(**kwargs)

    def __default__(self, data, children, meta):
        if isinstance(children, list) and len(children) == 1:
            out = lark.Token(type=data.upper(), value=children[0])
        else:
            out = children
        return out

    def transform(self, tree):
        try:
            self._collected_imports = set()
            result = super().transform(tree=tree)
            return result, self._collected_imports
        finally:
            self._collected_imports = None

    def doctype(self, tree):
        out = " | ".join(tree.children)
        return out

    def qualname(self, tree):
        out = []
        for i, child in enumerate(tree.children):
            if i != 0 and not child.startswith("["):
                out.append(".")
            out.append(child)
        out = "".join(out)
        return out

    def NAME(self, token):
        new_token = self._match_n_record_name(token)
        return new_token

    def ARRAY_NAME(self, token):
        new_token = self._match_n_record_name(token)
        new_token = lark.Token(type="ARRAY_NAME", value=new_token)
        return new_token

    def shape(self, tree):
        logger.debug("dropping shape information")
        return lark.Discard

    def shape_n_dtype(self, tree):
        name = _find_one_token(tree, "ARRAY_NAME")
        children = [child for child in tree.children if child != name]
        if children:
            name = f"{name}[{', '.join(children)}]"
        return name

    def contains(self, tree):
        out = ", ".join(tree.children)
        out = f"[{out}]"
        return out

    def optional(self, tree):
        return "None"

    def extra_info(self, tree):
        logger.debug("dropping extra info")
        return lark.Discard

    def _match_n_record_name(self, token):
        """Match type names to known imports."""
        assert "." not in token
        if token in self.docnames:
            docname = self.docnames[token]
            if docname.import_alias:
                token = docname.import_alias
            elif docname.import_name:
                token = docname.import_name
            if not docname.is_builtin:
                self._collected_imports.add(docname)
        else:
            logger.warning("type with unknown origin: %s", token)
        return token


with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar)


def parse_type(description, docnames, import_map):
    try:
        transformer = DoctypeTransformer(replace_map=docnames, import_map=import_map)
        tree = _lark.parse(description)
        stub_type, imports = transformer.transform(tree)
        return stub_type, imports
    except Exception as e:
        logger.error("couldn't parse docstring type:\n\n%s", e)
        return "", set()


def transform_docstring(text, docnames):
    """

    Parameters
    ----------
    text : str

    Returns
    -------

    """
    docstring = NumpyDocString(text)
    params = {p.use_name: p for p in docstring["Parameters"]}
    other_params = {p.use_name: p for p in docstring["Other Parameters"]}
    return_params = {i: p for i, p in enumerate(docstring["Returns"])}

    duplicate_params = params.keys() & other_params.keys()
    if duplicate_params:
        raise ValueError(f"{duplicate_params=}")
    params.update(other_params)

    param_pytypes = {
        name: parse_type(param.type, docnames=docnames)
        for name, param in params.items() if param.type
    }
    return_pytypes = {
        name: parse_type(param.type, docnames=docnames)
        for name, param in return_params.items() if param.type
    }

    out = PyTypeList(params=param_pytypes, return_params=return_pytypes)
    return param_pytypes, re


"""Transform types defined in docstrings to Python types.

"""

import logging
from dataclasses import dataclass
from pathlib import Path

import lark
import lark.visitors
from numpydoc.docscrape import NumpyDocString

logger = logging.getLogger(__name__)


here = Path(__file__).parent
grammar_path = here / "docstring_types.lark"


@dataclass(slots=True, frozen=True)
class ImportableName:
    name: str
    path: str
    alias: str

    @classmethod
    def from_cfg(cls, value):
        path, tail = value.split("::", maxsplit=1)
        name, *alias = tail.split("::", maxsplit=1)
        assert name
        if not path:
            path = None
        if not alias:
            alias = None
        else:
            assert len(alias) == 1
            alias = alias[0]
        return cls(name=name, path=path, alias=alias)

    def __str__(self):
        out = f"import {self.name}"
        if self.path:
            out = f"from {self.path} {out}"
        if self.alias:
            out = f"{out} as {self.alias}"
        return out


def _find_one_token(tree, token_name):
    tokens = [child for child in tree.children if child.type == token_name]
    if len(tokens) != 1:
        raise ValueError(
            f"expected exactly one Token of type {token_name}, found {len(tokens)}"
        )
    return tokens[0]


@lark.visitors.v_args(tree=True)
class DocTransformer(lark.visitors.Transformer):
    """Transformer using the docstring type grammar to return types."""

    def __init__(self, replace_map, import_map, **kwargs):
        self.replace_map = replace_map
        self.import_map = import_map
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

    def type_description(self, tree):
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
        """Match type names to known imports."""
        if token in self.replace_map:
            token = self.replace_map[token]
        if token in self.import_map:
            imp = self.import_map[token]
            if imp.alias:
                token = imp.alias
            elif imp.name:
                token = imp.name
            self._collected_imports.add(imp)
        return token

    def ARRAY_NAME(self, token):
        new_token = self.NAME(token)
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


with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar)


def parse_type(description, replace_map, import_map):
    transformer = DocTransformer(replace_map=replace_map, import_map=import_map)
    tree = _lark.parse(description)
    stub_type, imports = transformer.transform(tree)
    return stub_type, imports


@dataclass(frozen=True, slots=True)
class ParamTypeList:
    """Parameter types collected from a single docstring."""

    params: dict[str, tuple[str, ImportableName]]
    return_params: dict[str, tuple[str, ImportableName]]


def transform_docstring(text, replace_map, import_map):
    """

    Parameters
    ----------
    text : str

    Returns
    -------

    """
    docstring = NumpyDocString(text)

    params = {p.name: p for p in docstring["Parameters"]}
    other_params = {p.name: p for p in docstring["Other Parameters"]}
    return_params = {p.name: p for p in docstring["Returns"]}

    duplicate_params = params.keys() & other_params.keys()
    if duplicate_params:
        raise ValueError(f"{duplicate_params=}")
    params.update(other_params)

    param_types = {
        name: parse_type(param.type, replace_map=replace_map, import_map=import_map)
        for name, param in params.items() if param.type
    }
    return_param_types = {
        name: parse_type(param.type, replace_map=replace_map, import_map=import_map)
        for name, param in return_params.items() if param.type
    }

    out = ParamTypeList(params=param_types, return_params=return_param_types)
    return out

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
class Import:
    name: str
    path: str


@dataclass(slots=True, frozen=True)
class DocTransform:
    """Information on how to transform a single rule."""

    type_name: str
    import_: Import

    @classmethod
    def from_cfg(cls, spec):
        path, name = spec.split("::")
        return cls(type_name=name, import_=Import(name=name, path=path))


@lark.visitors.v_args(tree=True)
class DocTransformer(lark.visitors.Transformer):
    """Transformer using the docstring type grammar to return types."""

    def __init__(self, doc_transforms, **kwargs):
        self.doc_transforms = doc_transforms
        self._imports = None
        super().__init__(**kwargs)

    def __default__(self, data, children, meta):
        if data in self.doc_transforms:
            type_info = self.doc_transforms[data]
            out = type_info.type_name
            if type_info.import_:
                self._imports.add(type_info.import_)
            if children:
                out = f"{out}[{', '.join(children)}]"
            return out
        else:
            logger.warning("don't know how to deal with %r, dropping node", data)
            return lark.Discard

    def transform(self, tree):
        try:
            self._imports = set()
            result = super().transform(tree=tree)
            return result, self._imports
        finally:
            self._imports = None

    def type_description(self, tree):
        return " | ".join(tree.children)


with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar)


def _parse_type(description, transformer: DocTransformer):
    tree = _lark.parse(description)
    # TODO return imports as well
    stub_type, import_paths = transformer.transform(tree)
    return stub_type, import_paths


@dataclass(frozen=True, slots=True)
class ParamTypeList:
    """Parameter types collected from a single docstring."""

    params: dict[str, str]
    return_params: dict[str, str]


def transform_docstring(text, doc_transforms):
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

    transformer = DocTransformer(doc_transforms)
    param_types = {
        name: _parse_type(param.type, transformer=transformer)
        for name, param in params.items()
    }
    return_param_types = {
        name: _parse_type(param.type, transformer=transformer)
        for name, param in return_params.items()
    }

    return ParamTypeList(params=param_types, return_params=return_param_types)

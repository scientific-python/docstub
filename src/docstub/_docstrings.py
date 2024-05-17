"""Transform types defined in docstrings to Python types.

"""


import logging
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass

import lark
import lark.visitors
from numpydoc.docscrape import NumpyDocString


logger = logging.getLogger(__name__)


here = Path(__file__).parent
grammar_path = here / "docstring_types.lark"


@dataclass(slots=True, frozen=True)
class DocTransform:
    """Information on how to transform a single rule."""
    type_name: str
    import_path: str

    @classmethod
    def from_str(cls, s):
        import_path, type_name = s.split("::")
        return cls(type_name=type_name, import_path=import_path)


@lark.visitors.v_args(meta=True)
class DocTransformer(lark.visitors.Transformer):
    """Transformer using the docstring type grammar to return types."""

    def __init__(self, doc_transforms, **kwargs):
        self.doc_transforms = doc_transforms
        super().__init__(**kwargs)

    def __default__(self, data, children, meta):
        if
        logger.warning("don't know how to deal with %r, dropping node", data)
        return lark.Discard

    def transform(self, tree):
        result = super().transform(tree=tree)
        return result

    def type_description(self, children):
        return " | ".join(children)

    def numpy_ndarray(self, children):
        type_str = "NDArray"
        if children:
            assert len(children) == 1
            type_str = f"{type_str}[{children[0]}]"
        return type_str

    def array_like(self, children):
        return children

    def numpy_dtype(self, children):
        assert len(children) == 1
        type_str = children[0]
        return type_str


with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar)


def _parse_type(description, transformer: DocTransformer):
    tree = _lark.parse(description)
    # TODO return imports as well
    stub_type = transformer.transform(tree)
    return stub_type


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

    return ParamTypeList(
        params=param_types,
        return_params=return_param_types
    )

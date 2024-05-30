"""Transform types defined in docstrings to Python parsable types.

"""

import logging
from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class PyType:
    value: str
    imports: set[DocName] = field(default_factory=set)

    def __str__(self):
        return self.value


class MatchedName(lark.Token):
    pass


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
        """

        Parameters
        ----------
        tree :

        Returns
        -------
        pytype : PyType
            The doctype formatted as a stub-file compatible string with
            necessary imports attached.
        """
        try:
            self._collected_imports = set()
            value = super().transform(tree=tree)
            pytype = PyType(value=value, imports=self._collected_imports)
            return pytype
        finally:
            self._collected_imports = None

    def doctype(self, tree):
        out = " | ".join(tree.children)
        return out

    def type_or(self, tree):
        out = " | ".join(tree.children)
        return out

    def qualname(self, tree):
        matched = False
        out = []
        for i, child in enumerate(tree.children):
            if i != 0 and not child.startswith("["):
                out.append(".")
            if isinstance(child, MatchedName):
                matched = True
            out.append(child)
        out = "".join(out)
        if matched is False:
            logger.warning("unmatched name %r", out)
        return out

    def NAME(self, token):
        new_token = self._match_n_record_name(token)
        return new_token

    def ARRAY_NAME(self, token):
        new_token = self._match_n_record_name(token)
        new_token.type = "ARRAY_NAME"
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

    def container_of(self, tree):
        assert len(tree.children) == 2
        out = f"{tree.children[0]}[{tree.children[1]}, ...]"
        return out

    def contains(self, tree):
        out = ", ".join(tree.children)
        out = f"[{out}]"
        return out

    def optional(self, tree):
        return "None"

    def extra_info(self, tree):
        logger.debug("dropping extra info")
        return lark.Discard

    def literals(self, tree):
        out = " | ".join(tree.children)
        return out

    def literal(self, tree):
        assert len(tree.children) == 1
        out = f"Literal[{tree.children[0]}]"
        self._collected_imports.add(
            DocName.from_cfg("Literal", spec={"from": "typing"})
        )
        return out

    def _match_n_record_name(self, token):
        """Match type names to known imports."""
        assert "." not in token
        if token in self.docnames:
            docname = self.docnames[token]
            token = MatchedName(token.type, value=docname.use_name)
            if docname.has_import:
                self._collected_imports.add(docname)
        return token


with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar)


def doc2pytype(description, docnames):
    try:
        transformer = DoctypeTransformer(docnames=docnames)
        tree = _lark.parse(description)
        pytype = transformer.transform(tree)
        return pytype
    except Exception:
        logger.exception("couldn't parse docstring %r:", description)
        return PyType(
            value="Any", imports={DocName.from_cfg("Any", {"from": "typing"})}
        )


@dataclass(frozen=True, slots=True)
class CollectedPyTypes:
    params: dict[str, PyType]
    returns: dict[str, PyType]

    @classmethod
    def from_docstring(cls, docstring, *, docnames):
        """

        Parameters
        ----------
        docstring : str

        Returns
        -------

        """
        np_docstring = NumpyDocString(docstring)

        params = {p.name: p for p in np_docstring["Parameters"]}
        other = {p.name: p for p in np_docstring["Other Parameters"]}
        duplicate_params = params.keys() & other.keys()
        if duplicate_params:
            raise ValueError(f"{duplicate_params=}")
        params.update(other)

        pytypes_param = {
            name: doc2pytype(param.type, docnames=docnames)
            for name, param in params.items()
            if param.type
        }
        pytypes_return = {
            name: doc2pytype(param.type, docnames=docnames)
            for name, param in enumerate(np_docstring["Returns"])
            if param.type
        }

        collected = CollectedPyTypes(params=pytypes_param, returns=pytypes_return)
        return collected

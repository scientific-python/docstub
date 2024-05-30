"""Transform types defined in docstrings to Python parsable types.

"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from itertools import chain

import lark
import lark.visitors
from numpydoc.docscrape import NumpyDocString

from ._analysis import DocName

logger = logging.getLogger(__name__)


here = Path(__file__).parent
grammar_path = here / "doctype.lark"


def _find_one_token(tree: lark.Tree, *, name: str) -> lark.Token:
    """Find token with a specific type name in tree."""
    tokens = [child for child in tree.children if child.type == name]
    if len(tokens) != 1:
        raise ValueError(
            f"expected exactly one Token of type {name}, found {len(tokens)}"
        )
    return tokens[0]


@dataclass(frozen=True, slots=True)
class PyType:
    """Python-ready type with attached import information."""

    value: str
    imports: set[DocName] | frozenset[DocName] = field(default_factory=frozenset)

    def __post_init__(self):
        object.__setattr__(self, "imports", frozenset(self.imports))

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_joined(cls, pytypes):
        """Join multiple PyType instances into a single one.

        Parameters
        ----------
        pytypes : Iterable[PyType]
            The types to combine.

        Returns
        -------
        joined : PyType
            The combined types.
        """
        values = set()
        imports = set()
        for p in pytypes:
            values.add(p.value)
            imports.update(p.imports)
        joined = cls(value=" | ".join(values), imports=imports)
        return joined


class MatchedName(lark.Token):
    pass


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):
    """Transformer for docstring type descriptions (doctypes).

    Parameters
    ----------
    docnames : dict[str, DocName]
        A dictionary mapping atomic names used in doctypes to information such
        as where to import from or how to replace the name itself.
    kwargs : dict[Any, Any]
        Keyword arguments passed to the init of the parent class.
    """

    def __init__(self, *, docnames, **kwargs):
        self.docnames = docnames
        self._collected_imports = None
        super().__init__(**kwargs)

    def __default__(self, data, children, meta):
        """Unpack children of rule nodes by default.

        Parameters
        ----------
        data : lark.Token
            The rule-token of the current node.
        children : list[lark.Token, ...]
            The children of the current node.
        meta : lark.tree.Meta
            Meta information for the current node.

        Returns
        -------
        out : lark.Token or list[lark.Token, ...]
            Either a token or list of tokens.
        """
        if isinstance(children, list) and len(children) == 1:
            out = children[0]
            out.type = data.upper()  # Turn rule into "token"
        else:
            out = children
        return out

    def transform(self, tree):
        """

        Parameters
        ----------
        tree : lark.Tree
            The

        Returns
        -------
        pytype : PyType
            The doctype formatted as a stub-file compatible string with
            necessary imports attached.
        """
        try:
            self._collected_imports = set()
            value = super().transform(tree=tree)
            pytype = PyType(value=value, imports=frozenset(self._collected_imports))
            return pytype
        finally:
            self._collected_imports = None

    def doctype(self, tree):
        out = " | ".join(tree.children)
        return out

    def type_or(self, tree):
        out = " | ".join(tree.children)
        return out

    def optional(self, tree):
        return "None"

    def extra_info(self, tree):
        logger.debug("dropping extra info")
        return lark.Discard

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
        name = _find_one_token(tree, name="ARRAY_NAME")
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


def doc2pytype(doctype, *, docnames):
    """Convert a type description to a Python-ready type.

    Parameters
    ----------
    doctype : str
        The type description of a parameter or return value, as extracted from
        a docstring.
    docnames : dict[str, DocName]
        A dictionary mapping atomic names used in doctypes to information such
        as where to import from or how to replace the name itself.

    Returns
    -------
    pytype : PyType
        The transformed type, ready to be inserted into a stub file, with
        necessary imports attached.
    """
    try:
        transformer = DoctypeTransformer(docnames=docnames)
        tree = _lark.parse(doctype)
        pytype = transformer.transform(tree)
        return pytype
    except Exception:
        logger.exception("couldn't parse docstring %r:", doctype)
        return PyType(
            value="Any", imports={DocName.from_cfg("Any", {"from": "typing"})}
        )


class ReturnKey:
    """Simple "singleton" key to access the return PyType in a dictionary.

    See :func:`collect_pytypes` for more.
    """


ReturnKey = ReturnKey()


def collect_pytypes(docstring, *, docnames):
    """Collect PyTypes from a docstring.

    Parameters
    ----------
    docstring : str
        The docstring to collect from.
    docnames : dict[str, DocName]
        A dictionary mapping atomic names used in doctypes to information such
        as where to import from or how to replace the name itself.

    Returns
    -------
    pytypes : dict[str | Literal[ReturnKey], PyType]
        The collected PyType for each parameter. If a return type is documented
        it's saved under the special key :class:`ReturnKey`.
    """
    np_docstring = NumpyDocString(docstring)

    params = {p.name: p for p in np_docstring["Parameters"]}
    other = {p.name: p for p in np_docstring["Other Parameters"]}
    duplicate_params = params.keys() & other.keys()
    if duplicate_params:
        raise ValueError(f"{duplicate_params=}")
    params.update(other)

    pytypes = {
        name: doc2pytype(param.type, docnames=docnames)
        for name, param in params.items()
        if param.type
    }

    returns = {
        doc2pytype(param.type, docnames=docnames)
        for param in np_docstring["Returns"]
        if param.type
    }
    if returns:
        pytypes[ReturnKey] = PyType.from_joined(returns)

    return pytypes

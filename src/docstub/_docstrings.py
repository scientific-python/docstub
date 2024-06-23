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


def _find_one_token(tree: lark.Tree, *, name: str) -> lark.Token:
    """Find token with a specific type name in tree."""
    tokens = [child for child in tree.children if child.type == name]
    if len(tokens) != 1:
        msg = f"expected exactly one Token of type {name}, found {len(tokens)}"
        raise ValueError(msg)
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
    def as_return_tuple(cls, return_types):
        """Concatenate multiple PyTypes and wrap in tuple if more than one.

        Useful to combine multiple returned types for a function into a single
        PyType.

        Parameters
        ----------
        return_types : Iterable[PyType]
            The types to combine.

        Returns
        -------
        concatenated : PyType
            The concatenated types.
        """
        values, imports = cls._aggregate_pytypes(*return_types)
        value = " , ".join(values)
        if len(values) > 1:
            value = f"tuple[{value}]"
        concatenated = cls(value=value, imports=imports)
        return concatenated

    @classmethod
    def as_yields_generator(cls, yield_types, receive_types=()):
        """Create new iterator type from yield and receive types.

        Parameters
        ----------
        yield_types : Iterable[PyType]
            The types to yield.
        receive_types : Iterable[PyType], optional
            The types the generator receives.

        Returns
        -------
        iterator : PyType
            The yielded and received types wrapped in a generator.
        """
        # TODO
        raise NotImplementedError()

    @staticmethod
    def _aggregate_pytypes(*types):
        """Aggregate values and imports of given PyTypes.

        Parameters
        ----------
        types : Iterable[PyType]

        Returns
        -------
        values : list[str]
        imports : set[~.DocName]
        """
        values = []
        imports = set()
        for p in types:
            values.append(p.value)
            imports.update(p.imports)
        return values, imports


class MatchedName(lark.Token):
    pass


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):
    """Transformer for docstring type descriptions (doctypes)."""

    def __init__(self, *, inspector, **kwargs):
        """
        Parameters
        ----------
        inspector : ~.StaticInspector
            A dictionary mapping atomic names used in doctypes to information such
            as where to import from or how to replace the name itself.
        kwargs : dict[Any, Any]
            Keyword arguments passed to the init of the parent class.
        """
        self.inspector = inspector
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

    def annotation(self, tree):
        out = " | ".join(tree.children)
        return out

    def types_or(self, tree):
        out = " | ".join(tree.children)
        return out

    def optional(self, tree):
        out = "None"
        literal = [child for child in tree.children if child.type == "LITERAL"]
        assert len(literal) <= 1
        if literal:
            out = lark.Discard  # Type should cover the default
        return out

    def extra_info(self, tree):
        logger.debug("dropping extra info")
        return lark.Discard

    def sphinx_ref(self, tree):
        qualname = _find_one_token(tree, name="QUALNAME")
        return qualname

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
            docname = self.inspector.query(out)
            if docname:
                out = docname.use_name
                self._collected_imports.add(docname)
            else:
                logger.warning(
                    "unmatched name %r in %s", out, self.inspector.current_source
                )
        out = lark.Token("QUALNAME", out)
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

    def contains(self, tree):
        out = ", ".join(tree.children)
        out = f"[{out}]"
        return out

    def literals(self, tree):
        out = " , ".join(tree.children)
        out = f"Literal[{out}]"
        self._collected_imports.add(self.inspector.query("Literal"))
        return out

    def _match_n_record_name(self, token):
        """Match type names to known imports."""
        assert "." not in token
        docname = self.inspector.query(token)
        if docname:
            token = MatchedName(token.type, value=docname.use_name)
            if docname.has_import:
                self._collected_imports.add(docname)
        return token


with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar)


def doc2pytype(doctype, *, inspector):
    """Convert a type description to a Python-ready type.

    Parameters
    ----------
    doctype : str
        The type description of a parameter or return value, as extracted from
        a docstring.
    inspector : docstub._analysis.StaticInspector

    Returns
    -------
    pytype : PyType
        The transformed type, ready to be inserted into a stub file, with
        necessary imports attached.
    """
    try:
        transformer = DoctypeTransformer(inspector=inspector)
        tree = _lark.parse(doctype)
        pytype = transformer.transform(tree)
        return pytype
    except Exception:
        logger.exception("couldn't parse docstring %r:", doctype)
        return PyType(
            value="Any",
            imports={DocName.one_from_config("Any", info={"from": "typing"})},
        )


@dataclass(frozen=True, slots=True)
class DocstringPyTypes:
    """Groups Pytypes in a docstring."""

    parameters: dict[str, PyType]
    attributes: dict[str, PyType]
    returns: PyType | None
    yields: PyType | None


def collect_pytypes(docstring, *, inspector):
    """Collect PyTypes from a docstring.

    Parameters
    ----------
    docstring : str
        The docstring to collect from.
    inspector : docstub._analysis.StaticInspector

    Returns
    -------
    pytypes : DocstringPyTypes
        The collected PyTypes grouped by parameters, attributes, returns, and
        yields.
    """
    np_docstring = NumpyDocString(docstring)

    params = {p.name: p for p in np_docstring["Parameters"]}
    other = {p.name: p for p in np_docstring["Other Parameters"]}

    duplicate_params = params.keys() & other.keys()
    if duplicate_params:
        raise ValueError(f"{duplicate_params=}")
    params.update(other)

    parameters = {
        name: doc2pytype(param.type, inspector=inspector)
        for name, param in params.items()
        if param.type
    }

    returns = [
        doc2pytype(param.type, inspector=inspector)
        for param in np_docstring["Returns"]
        if param.type
    ]
    returns = PyType.as_return_tuple(returns) if returns else None

    yields = [
        doc2pytype(param.type, inspector=inspector)
        for param in np_docstring["Yields"]
        if param.type
    ]
    receives = [
        doc2pytype(param.type, inspector=inspector)
        for param in np_docstring["Receives"]
        if param.type
    ]
    attributes = [
        doc2pytype(param.type, inspector=inspector)
        for param in np_docstring["Attributes"]
        if param.type
    ]
    if returns and yields:
        logger.warning(
            "found 'Returns' and 'Yields' section in docstring, ignoring 'Yields'"
        )
    if receives and not yields:
        logger.warning("found 'Receives' section in docstring without 'Yields' section")
    if yields:
        logger.warning("yields is not supported yet")

    ds_pytypes = DocstringPyTypes(
        parameters=parameters, attributes=attributes, returns=returns, yields=None
    )
    return ds_pytypes

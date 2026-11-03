"""Parsing & transformation of doctypes into Python-compatible syntax."""

import enum
import keyword
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path
from textwrap import indent
from typing import Final, Self

import lark
import lark.visitors

from ._report import ContextReporter
from ._utils import DocstubError

logger: Final[logging.Logger] = logging.getLogger(__name__)


DOCTYPE_GRAMMAR_PATH: Final[Path] = Path(__file__).parent / "doctype.lark"
DOCTYPE_GRAMMAR: Final[str] = DOCTYPE_GRAMMAR_PATH.read_text()


def flatten_recursive(iterable):
    """Flatten nested iterables yield the contained strings.

    Parameters
    ----------
    iterable : Iterable[Iterable or str]
        An iterable containing nested iterables or strings. Only strings are
        supported as "leafs" for now.

    Yields
    ------
    item : str

    Examples
    --------
    >>> nested = ["only", ["strings", ("and", "iterables"), "are", ["allowed"]]]
    >>> list(flatten_recursive(nested))
    ['only', 'strings', 'and', 'iterables', 'are', 'allowed']
    """
    for item in iterable:
        if isinstance(item, str):
            yield item
        elif isinstance(item, Iterable):
            yield from flatten_recursive(item)
        else:
            raise ValueError(f"unexpected type: {item!r}")


def insert_between(iterable, *, sep):
    """Insert `sep` inbetween elements of `iterable`.

    Parameters
    ----------
    iterable : Iterable
    sep : Any

    Returns
    -------
    out : list[Any]

    Examples
    --------
    >>> code = ["a", "b", "c", ]
    >>> list(insert_between(code, sep=" | "))
    ['a', ' | ', 'b', ' | ', 'c']
    """
    out = []
    for item in iterable:
        out.append(item)
        out.append(sep)
    return out[:-1]


class TermKind(enum.StrEnum):
    """Encodes the different kinds of :class:`Term`."""

    # docstub: off
    NAME = enum.auto()
    LITERAL = enum.auto()
    SYNTAX = enum.auto()
    # docstub: on


class Term(str):
    """A terminal / symbol representing an atomic part in an annotation expression.

    Attributes
    ----------
    kind : TermKind
    pos : tuple of (int, int) or None
    __slots__ : Final[tuple[str, ...]]

    Examples
    --------
    >>> ''.join(
    ...     [
    ...         Term("int", kind="name"),
    ...         Term(" | ", kind="syntax"),
    ...         Term("float", kind="name")
    ...     ]
    ... )
    'int | float'
    """

    __slots__ = ("kind", "pos")

    def __new__(cls, value, *, kind, pos=None):
        """
        Parameters
        ----------
        value : str
        kind : TermKind or str
        pos : tuple of (int, int), optional

        Returns
        -------
        cls : Self
        """
        self = super().__new__(cls, value)
        self.kind = TermKind(kind)
        self.pos = pos
        return self

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self}', kind='{self.kind}')"

    def __getnewargs_ex__(self):
        """
        Returns
        -------
        args : tuple of (Any, ...)
        kwargs : dict of {str: Any}
        """
        kwargs = {"value": str(self), "kind": self.kind, "pos": self.pos}
        return (), kwargs


@dataclass(slots=True, frozen=True)
class Expr:
    """An annotation expression.

    Parameters
    ----------
    rule :
        The name of the (grammar) rule corresponding to this expression.
    children : list of (Expr or Term)
        Sub-expressions or terms that make up this expression.
    """

    rule: str
    children: tuple[Self | Term]

    def __post_init__(self):
        assert isinstance(self.rule, str) and self.rule
        assert isinstance(self.children, tuple)

    @property
    def terms(self):
        """All terms in the expression.

        Returns
        -------
        terms : list of Term
        """
        return list(flatten_recursive(self))

    @property
    def names(self):
        """Name terms in the expression.

        Returns
        -------
        names : list of Term
        """
        return [term for term in self.terms if term.kind == TermKind.NAME]

    @property
    def sub_expressions(self):
        """Iterate expressions inside the current one.

        Returns
        -------
        names : list of Self
        """
        cls = type(self)
        for child in self.children:
            if isinstance(child, cls):
                yield child
                yield from child.sub_expressions

    def __iter__(self):
        """Iterate over children of this expression.

        Yields
        ------
        child : Expr or Term
        """
        yield from self.children

    def format_tree(self):
        """Format full hierarchy as a tree.

        Returns
        -------
        formatted : str
        """
        formatted_children = (
            c.format_tree() if hasattr(c, "format_tree") else repr(c)
            for c in self.children
        )
        formatted_children = ",\n".join(formatted_children)
        formatted_children = indent(formatted_children, prefix="  ")
        return (
            f"{type(self).__name__}({self.rule!r}, children=[\n{formatted_children}])"
        )

    def print_tree(self):
        """Print full hierarchy as a tree."""
        print(self.format_tree())  # noqa: T201

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: '{self.as_code()}' rule='{self.rule}'>"

    def __str__(self) -> str:
        return "".join(self.terms)

    def as_code(self) -> str:
        return str(self)


BLACKLISTED_QUALNAMES: Final[set[str]] = set(keyword.kwlist) - {"None", "True", "False"}


class BlacklistedQualname(DocstubError):
    """Raised when a qualname is a forbidden keyword."""


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):
    """Transform parsed doctypes into Python-compatible syntax.

    Examples
    --------
    >>> import lark
    >>> parser = lark.Lark(DOCTYPE_GRAMMAR, propagate_positions=True)
    >>> tree = parser.parse("int or tuple of (int, ...)")
    >>> transformer = DoctypeTransformer()
    >>> str(transformer.transform(tree=tree))
    'int | tuple[int, ...]'
    """

    def __init__(self, *, reporter=None):
        """
        Parameters
        ----------
        reporter : ~.ContextReporter
        """
        reporter = reporter or ContextReporter(logger=logger)
        self.reporter = reporter.copy_with(logger=logger)

    def start(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        return Expr(rule="start", children=tuple(tree.children))

    def qualname(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Term
        """
        children = tree.children
        _qualname = ".".join(children)

        if _qualname in BLACKLISTED_QUALNAMES:
            raise BlacklistedQualname(_qualname)

        _qualname = Term(
            _qualname,
            kind=TermKind.NAME,
            pos=(tree.meta.start_pos, tree.meta.end_pos),
        )
        return _qualname

    def rst_role(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        # Drop rst_prefix
        children = [c for c in tree.children if isinstance(c, Term)]
        expr = Expr(rule="rst_role", children=tuple(children))
        return expr

    def ELLIPSES(self, token):
        """
        Parameters
        ----------
        token : lark.Token

        Returns
        -------
        out : Term
        """
        return Term(token, kind=TermKind.LITERAL)

    def union(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        sep = Term(" | ", kind=TermKind.SYNTAX)
        children = insert_between(tree.children, sep=sep)
        expr = Expr(rule="union", children=tuple(children))
        return expr

    def subscription(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        assert len(tree.children) > 1
        return self._format_subscription(tree.children, rule="subscription")

    def param_spec(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        sep = Term(", ", kind=TermKind.SYNTAX)
        children = [
            Term("[", kind=TermKind.SYNTAX),
            *insert_between(tree.children, sep=sep),
            Term("]", kind=TermKind.SYNTAX),
        ]
        expr = Expr(rule="param_spec", children=tuple(children))
        return expr

    def callable(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        assert len(tree.children) > 1
        return self._format_subscription(tree.children, rule="callable")

    def literal(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        assert len(tree.children) > 1
        out = self._format_subscription(tree.children, rule="literal")
        return out

    def natlang_literal(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        items = [
            Term("Literal", kind=TermKind.NAME),
            *tree.children,
        ]
        out = self._format_subscription(items, rule="natlang_literal")

        assert len(tree.children) >= 1
        if len(tree.children) == 1:
            details = ("Consider using `%s` to improve readability", "".join(out))
            self.reporter.warn(
                "Natural language literal with one item: `{%s}`",
                tree.children[0],
                details=details,
            )
        return out

    def literal_item(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Term
        """
        item, *other = tree.children
        assert not other
        kind = TermKind.LITERAL
        if isinstance(item, Term):
            # Preserve kind=Name for qualnames in literal expressions
            kind = item.kind
        out = Term(item, kind=kind, pos=(tree.meta.start_pos, tree.meta.end_pos))
        return out

    def natlang_container(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        assert len(tree.children) >= 1
        return self._format_subscription(tree.children, rule="natlang_container")

    def natlang_array(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        return self._format_subscription(tree.children, rule="natlang_array")

    def array_name(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Term
        """
        # This currently relies on a hack that only allows specific names
        # in `array_expression` (see `ARRAY_NAME` terminal in gramar)
        qualname = self.qualname(tree)
        return qualname

    def dtype(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        return Expr(rule="dtype", children=tuple(tree.children))

    def shape(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.visitors._DiscardType
        """
        logger.debug("dropping shape information")
        return lark.Discard

    def optional_info(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.visitors._DiscardType
        """
        logger.debug("dropping optional / default info")
        return lark.Discard

    def extra_info(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.visitors._DiscardType
        """
        logger.debug("dropping extra info")
        return lark.Discard

    @staticmethod
    def _format_subscription(sequence, *, rule):
        """Format a `name[...]` style expression.

        Parameters
        ----------
        sequence : Sequence[str]
        rule : str, optional

        Returns
        -------
        out : Expr
        """
        sep = Term(", ", kind=TermKind.SYNTAX)
        container, *content = sequence
        assert container

        if content:
            content = insert_between(content, sep=sep)
            children = [
                container,
                Term("[", kind=TermKind.SYNTAX),
                *content,
                Term("]", kind=TermKind.SYNTAX),
            ]
        else:
            children = [container]

        expr = Expr(rule=rule, children=tuple(children))
        return expr


class DoctypeTranspiler:
    """Transpile a :term:`doctype` into a structured expression.

    This is could be a simple function, but as a class dependency injection with
    custom grammars or transformers is made easier.

    Parameters
    ----------
    grammar : str, optional
        Use custom grammar to parse doctypes. You can reuse parts of the
        default grammar (see ``DOCTYPE_GRAMMAR_PATH`) with
        ``%import doctype (start, ...)``.
    grammar_import_paths : tuple of (Path, ...)
        Additional paths to directories with grammars that are imported in
        `grammar`.
    transformer : lark.visitors.Transformer, optional
        Use a custom transformer to transform the parsed tree.
    reporter : ~.ContextReporter, optional
        Pass file and line context for logging.

    Examples
    --------
    >>> transpile = DoctypeTranspiler()
    >>> transpile("tuple of (int, ...)")
    <Expr: 'tuple[int, ...]' rule='start'>
    >>> transpile("ndarray of dtype (float or int)")
    <Expr: 'ndarray[float | int]' rule='start'>
    """

    def __init__(
        self,
        *,
        grammar=DOCTYPE_GRAMMAR,
        grammar_import_paths=(DOCTYPE_GRAMMAR_PATH.parent,),
        transformer=None,
        reporter=None,
    ):
        default_transformer = DoctypeTransformer(reporter=reporter)

        if transformer is None:
            transformer = default_transformer

        if grammar != DOCTYPE_GRAMMAR:
            # A custom grammar may import the existing doctype grammar. In that
            # case Lark will put imported rules into their own "doctype__" prefixed
            # namespace. By providing `DoctypeTransformer` for that namespace we
            # make it work.
            transformer = lark.visitors.merge_transformers(
                transformer, doctype=default_transformer
            )

        self.reporter = reporter or ContextReporter(logger=logger)
        self._grammar = grammar
        self._grammar_import_paths = grammar_import_paths
        self._transformer = transformer

    @lru_cache(maxsize=1000)  # TODO find a way to report hits & misses
    def __call__(self, doctype):
        """Transpile single doctype into a structured expression.

        Parameters
        ----------
        doctype : str

        Returns
        -------
        parsed : Expr

        Raises
        ------
        lark.exceptions.VisitError
            Raised when the transformation is interrupted by an exception.
            See :cls:`lark.exceptions.VisitError`.
        BlacklistedQualname
            Raised when a qualname is a forbidden keyword.
        """
        tree = self._parser.parse(doctype)
        expression = self._transformer.transform(tree=tree)
        assert isinstance(expression, Expr)
        return expression

    @cached_property
    def _parser(self):
        """Initialize Lark parser.

        Use a cached property to construct the lark parser as few times as
        possible just before use. Doing that in the ``__init__`` doesn't work
        because :class:`lark.Lark` is not pickle-able; and we want to pickle
        this class for dependency injection before forking.

        Returns
        -------
        parser : lark.Lark
        """
        # TODO If we used an LARL conforming grammar we could pass the `transformer`
        #  directly here which should be faster [1]
        # [1] https://lark-parser.readthedocs.io/en/latest/classes.html#lark:~:text=faster
        parser = lark.Lark(
            grammar=self._grammar,
            propagate_positions=True,
            import_paths=list(self._grammar_import_paths),
        )
        return parser

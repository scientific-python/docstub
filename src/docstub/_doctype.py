"""Parsing of doctypes."""

import enum
import logging
import keyword
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from textwrap import indent
from typing import Final

import lark
import lark.visitors

from ._utils import DocstubError


logger: Final = logging.getLogger(__name__)


grammar_path: Final = Path(__file__).parent / "doctype.lark"

with grammar_path.open() as file:
    _grammar: Final = file.read()

_lark: Final = lark.Lark(_grammar, propagate_positions=True, strict=True)


def flatten_recursive(iterable):
    """Flatten nested iterables yield the contained strings.

    Parameters
    ----------
    iterable : Iterable[Iterable or str]

    Yields
    ------
    item : str
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
    """
    out = []
    for item in iterable:
        out.append(item)
        out.append(sep)
    return out[:-1]


class TokenKind(enum.StrEnum):
    # docstub: off
    NAME = enum.auto()
    LITERAL = enum.auto()
    SYNTAX = enum.auto()
    # docstub: on


class Token(str):
    """A token representing an atomic part of a doctype.

    Attributes
    ----------
    __slots__ : Final
    """

    __slots__ = ("value", "kind", "pos")

    def __new__(cls, value, *, kind, pos=None):
        """
        Parameters
        ----------
        value : str
        kind : TokenKind or str
        pos : tuple of (int, int), optional
        """
        self = super().__new__(cls, value)
        self.kind = TokenKind(kind)
        self.pos = pos
        return self

    def __repr__(self):
        return f"{type(self).__name__}('{self}', kind='{self.kind}')"

    def __getnewargs_ex__(self):
        """"""
        kwargs = {"value": str(self), "kind": self.kind, "pos": self.pos}
        return tuple(), kwargs


@dataclass(slots=True)
class Expression:
    """A named expression made up of sub expressions and tokens."""

    rule: str
    children: list[Expression | Token]

    @property
    def tokens(self):
        """All tokens in the expression."""
        return list(flatten_recursive(self))

    @property
    def names(self):
        """Name tokens in the expression."""
        return [token for token in self.tokens if token.kind == TokenKind.NAME]

    def __iter__(self):
        yield from self.children

    def format_tree(self):
        formatted_children = (
            c.format_tree() if hasattr(c, "format_tree") else repr(c)
            for c in self.children
        )
        formatted_children = ",\n".join(formatted_children)
        formatted_children = indent(formatted_children, prefix="  ")
        return (
            f"{type(self).__name__}({self.rule!r}, children=[\n{formatted_children}])"
        )

    def __repr__(self):
        return f"<{type(self).__name__}: '{self.as_code()}' rule='{self.rule}'>"

    def __str__(self):
        return "".join(self.tokens)

    def as_code(self):
        return str(self)


BLACKLISTED_QUALNAMES: Final = set(keyword.kwlist) - {"None", "True", "False"}


class BlacklistedQualname(DocstubError):
    """Raised when a qualname is a forbidden keyword."""


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):

    def start(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expression
        """
        return Expression(rule="start", children=tree.children)

    def qualname(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Token
        """
        children = tree.children
        _qualname = ".".join(children)

        if _qualname in BLACKLISTED_QUALNAMES:
            raise BlacklistedQualname(_qualname)

        _qualname = Token(
            _qualname,
            kind=TokenKind.NAME,
            pos=(tree.meta.start_pos, tree.meta.end_pos),
        )
        return _qualname

    def ELLIPSES(self, token):
        """
        Parameters
        ----------
        token : lark.Token

        Returns
        -------
        out : Token
        """
        return Token(token, kind=TokenKind.LITERAL)

    def union(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expression
        """
        sep = Token(" | ", kind=TokenKind.SYNTAX)
        expr = Expression(rule="union", children=insert_between(tree.children, sep=sep))
        return expr

    def subscription(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expression
        """
        return self._format_subscription(tree.children)

    def natlang_literal(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expression
        """
        items = [
            Token("Literal", kind=TokenKind.SYNTAX),
            *tree.children,
        ]
        out = self._format_subscription(items, rule="natlang_literal")

        if len(tree.children) == 1:
            logger.warning(
                "natural language literal with one item `%s`, "
                "consider using `%s` to improve readability",
                tree.children[0],
                "".join(out),
            )
        return out

    def literal_item(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Token
        """
        item, *other = tree.children
        assert not other
        kind = TokenKind.LITERAL
        if isinstance(item, Token):
            kind = item.kind
        return Token(item, kind=kind, pos=(tree.meta.start_pos, tree.meta.end_pos))

    def natlang_container(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expression
        """
        return self._format_subscription(tree.children, rule="natlang_container")

    def natlang_array(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expression
        """
        return self._format_subscription(tree.children, rule="natlang_array")

    def array_name(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Token
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
        out : Expression
        """
        return Expression(rule="dtype", children=tree.children)

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

    def _format_subscription(self, sequence, rule="subscription"):
        """
        Parameters
        ----------
        sequence : Sequence[str]
        rule : str, optional

        Returns
        -------
        out : Expression
        """
        sep = Token(", ", kind=TokenKind.SYNTAX)
        container, *content = sequence
        content = insert_between(content, sep=sep)
        assert content
        expr = Expression(
            rule=rule,
            children=[
                container,
                Token("[", kind=TokenKind.SYNTAX),
                *content,
                Token("]", kind=TokenKind.SYNTAX),
            ],
        )
        return expr


def parse_doctype(doctype):
    """Turn a type description in a docstring into a type annotation.

    Parameters
    ----------
    doctype : str
        The doctype to parse.

    Returns
    -------
    parsed : Expression

    Raises
    ------
    lark.exceptions.VisitError
        Raised when the transformation is interrupted by an exception.
        See :cls:`lark.exceptions.VisitError`.

    Examples
    --------
    >>> parse_doctype("tuple of (int, ...)")
    <Expression: 'tuple[int, ...]' rule='start'>
    >>> parse_doctype("ndarray of dtype (float or int)")
    <Expression: 'ndarray[float | int]' rule='start'>
    """
    tree = _lark.parse(doctype)
    expression = DoctypeTransformer().transform(tree=tree)
    return expression

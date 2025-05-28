"""Parsing of doctypes"""

import enum
import itertools
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import lark
import lark.visitors

logger = logging.getLogger(__name__)


grammar_path = Path(__file__).parent / "doctype.lark"

with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar, propagate_positions=True, strict=True)


def flatten_recursive(iterable):
    for item in iterable:
        if not isinstance(item, str) and isinstance(item, Iterable):
            yield from flatten_recursive(item)
        else:
            yield item


def insert_between(iterable, *, sep):
    out = []
    for item in iterable:
        out.append(item)
        out.append(sep)
    return out[:-1]


class TokenFlag(enum.Flag):
    # docstub: off
    NAME = enum.auto()
    NATLANG = enum.auto()
    SUBSCRIPT = enum.auto()
    LITERAL = enum.auto()
    GENERATOR = enum.auto()
    ARRAY = enum.auto()
    UNION = enum.auto()
    START = enum.auto()
    STOP = enum.auto()
    SEP = enum.auto()
    # docstub: on

    @classmethod
    def _missing_(cls, value):
        forbidden = {
            *itertools.combinations([cls.START, cls.STOP, cls.SEP, cls.NAME], 2)
        }
        for pair in forbidden:
            if value is (pair[0].value | pair[1].value):
                raise ValueError(f"{pair[0].name}|{pair[1].name} not allowed")
        return super()._missing_(value)


class Token(str):
    """A token representing an atomic part of a doctype."""

    flag = TokenFlag

    __slots__ = ("value", "kind", "pos")

    def __new__(cls, value, *, kind, pos=None):
        self = super().__new__(cls, value)
        self.kind = TokenFlag(kind)
        self.pos = pos
        return self

    def __repr__(self):
        return f"{type(self).__name__}('{self}', kind={self.kind!r})"

    @classmethod
    def find_iter(cls, iterable, *, kind):
        kind = TokenFlag(kind)
        for item in flatten_recursive(iterable):
            if isinstance(item, cls) and all(k & item.kind for k in kind):
                yield item

    @classmethod
    def find_one(cls, iterable, *, kind):
        matching = list(cls.find_iter(iterable, kind=kind))
        if len(matching) != 1:
            msg = (
                f"expected exactly one {cls.__name__} with {kind=}, "
                f"got {len(matching)}: {matching}"
            )
            raise ValueError(msg)
        return matching[0]


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):
    def qualname(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.Token
        """
        children = tree.children
        _qualname = ".".join(children)
        _qualname = Token(
            _qualname,
            kind=Token.flag.NAME,
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
        out : lark.Token
        """
        qualname = Token.find_one(tree.children, kind=Token.flag.NAME)
        return qualname

    def union(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : list[str]
        """
        sep = Token(" | ", kind=Token.flag.UNION | Token.flag.SEP)
        out = insert_between(tree.children, sep=sep)
        return out

    def subscription(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        return self._format_subscription(tree.children)

    def natlang_literal(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        items = [
            Token("Literal", kind=Token.flag.LITERAL | Token.flag.NAME),
            *tree.children,
        ]
        out = self._format_subscription(
            items, kind=Token.flag.LITERAL | Token.flag.NATLANG
        )

        if len(tree.children) == 1:
            logger.warning(
                "natural language literal with one item `%s`, "
                "consider using `%s` to improve readability",
                tree.children[0],
                "".join(out),
            )
        return out

    def literal_item(self, tree):
        item, *other = tree.children
        assert not other
        kind = Token.flag.LITERAL
        if isinstance(item, Token):
            kind |= item.kind
        return Token(item, kind=kind, pos=(tree.meta.start_pos, tree.meta.end_pos))

    def natlang_container(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        return self._format_subscription(tree.children, kind=Token.flag.NATLANG)

    def natlang_array(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        array_name = Token.find_one(
            tree.children, kind=Token.flag.ARRAY | Token.flag.NAME
        )
        items = tree.children.copy()
        items.remove(array_name)
        items.insert(0, array_name)
        return self._format_subscription(
            items, kind=Token.flag.ARRAY | Token.flag.NATLANG
        )

    def array_name(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.Token
        """
        # Treat `array_name` as `qualname`, but mark it as an array name,
        # so we know which one to treat as the container in `array_expression`
        # This currently relies on a hack that only allows specific names
        # in `array_expression` (see `ARRAY_NAME` terminal in gramar)
        qualname = self.qualname(tree)
        qualname = Token(qualname, kind=Token.flag.NAME | Token.flag.ARRAY)
        return qualname

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

    def optional(self, tree):
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

    def _format_subscription(self, sequence, kind=None):
        if kind is None:
            kind = Token.flag.SUBSCRIPT
        else:
            kind |= Token.flag.SUBSCRIPT

        sep = Token(", ", kind=kind | Token.flag.SEP)
        container, *content = sequence
        content = insert_between(content, sep=sep)
        assert content
        out = [
            container,
            Token("[", kind=kind | Token.flag.START),
            *content,
            Token("]", kind=kind | Token.flag.STOP),
        ]
        return out


@dataclass(frozen=True, slots=True)
class ParsedDoctype:
    tokens: tuple[Token, ...]
    raw_doctype: str

    @classmethod
    def parse(cls, doctype):
        """Turn a type description in a docstring into a type annotation.

        Parameters
        ----------
        doctype : str
            The doctype to parse.

        Returns
        -------
        annotation_list : list of Token

        Examples
        --------
        >>> doctype = ParsedDoctype.parse(
        ...     "tuple of int or ndarray of dtype (float or int)"
        ... )
        >>> doctype
        <ParsedDoctype: 'tuple[int] | ndarray[float | int]'>
        >>> doctype.qualnames
        (Token('tuple', kind='qualname'),
         Token('int', kind='qualname'),
         Token('ndarray', kind='qualname'),
         Token('float', kind='qualname'),
         Token('int', kind='qualname'))
        """
        tree = _lark.parse(doctype)
        tokens = DoctypeTransformer().transform(tree=tree)
        tokens = tuple(flatten_recursive(tokens))
        return cls(tokens, raw_doctype=doctype)

    def __str__(self):
        return "".join(self.tokens)

    def __repr__(self):
        return f"<{type(self).__name__} '{self}'>"

    @property
    def qualnames(self):
        return tuple(Token.find_iter(self.tokens, kind=Token.flag.NAME))

    def print_map_tokens_to_raw(self):
        for token in self.tokens:
            if token.pos is not None:
                start, stop = token.pos
                print(self.raw_doctype)
                print(" " * start + "^" * (stop - start))
                print(" " * start + token)
                print()

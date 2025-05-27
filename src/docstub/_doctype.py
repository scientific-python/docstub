"""Parsing of doctypes"""

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


class Token(str):
    """A token representing an atomic part of a doctype."""

    __slots__ = ("value", "kind")

    def __new__(cls, value, *, kind):
        self = super().__new__(cls, value)
        self.kind = kind
        return self

    def __repr__(self):
        return f"{type(self).__name__}('{self}', kind={self.kind!r})"

    @classmethod
    def find_iter(cls, iterable, *, kind):
        for item in flatten_recursive(iterable):
            if isinstance(item, cls) and item.kind == kind:
                yield item

    @classmethod
    def find_one(cls, iterable, *, kind):
        matching = list(cls.find_iter(iterable, kind=kind))
        if len(matching) != 1:
            msg = (
                f"expected exactly one {cls.__name__} with {kind=}, got {len(matching)}"
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
        _qualname = Token(_qualname, kind="qualname")
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
        qualname = Token.find_one(tree.children, kind="qualname")
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
        sep = Token(" | ", kind="union_sep")
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
        return self._format_subscription(tree.children, name="subscription")

    def natlang_literal(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        items = [Token("Literal", kind="qualname"), *tree.children]
        out = self._format_subscription(items, "nl_literal")

        if len(tree.children) == 1:
            logger.warning(
                "natural language literal with one item `%s`, "
                "consider using `%s` to improve readability",
                tree.children[0],
                "".join(out),
            )
        return out

    def natlang_container(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        return self._format_subscription(tree.children, name="nl_container")

    def natlang_array(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        array_name = Token.find_one(tree.children, kind="array_name")
        items = tree.children.copy()
        items.remove(array_name)
        items.insert(0, Token(array_name, kind="qualname"))
        return self._format_subscription(items, name="nl_array")

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
        qualname = Token(qualname, kind="array_name")
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

    def _format_subscription(self, sequence, name):
        sep = Token(", ", kind=f"{name}_sep")
        container, *content = sequence
        content = insert_between(content, sep=sep)
        assert content
        out = [
            container,
            Token("[", kind=f"{name}_start"),
            *content,
            Token("]", kind=f"{name}_stop"),
        ]
        return out

    def __default_token__(self, token):
        return Token(token.value, kind=token.type.lower())


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
        >>> ParsedDoctype.parse("tuple of int or ndarray of dtype (float or int)")
        <ParsedDoctype: 'tuple[int] | ndarray[float | int]'>
        """
        tree = _lark.parse(doctype)
        result = DoctypeTransformer().transform(tree=tree)
        result = tuple(flatten_recursive(result))
        return cls(result, raw_doctype=doctype)

    def __str__(self):
        return "".join(self.tokens)

    def __repr__(self):
        return f"<{type(self).__name__}: '{self}'>"

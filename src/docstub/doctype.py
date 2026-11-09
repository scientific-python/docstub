"""Doctype transpiling.

Attributes
----------
grammar_path :
    Path to the grammar.
"""

import enum
import keyword
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from itertools import product
from pathlib import Path
from textwrap import indent
from typing import ClassVar, Final, Self

import lark
import lark.visitors

from ._cache import LRUMemoryCache
from ._report import ContextReporter, Stats
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


def expand_expression(expr, *, expand_rule):
    """Create union of `expr` form a combination of all matching children.

    Parameters
    ----------
    expr : Expr
        The expression to expand into multiple ones.
    expand_rule : str

    Returns
    -------
    expanded : Expr
    """
    expansions = expr.find_all(rule=expand_rule)
    if not expansions:
        return expr

    # Create Cartesian product of all expansions where each
    # value is prefixed by the expansion it will replace
    expansions = [
        [(expansion, value) for value in expansion.children] for expansion in expansions
    ]
    combinations = list(product(*expansions))

    # Create a new expression for each combination
    expanded = []
    for combination in combinations:
        new_expr = expr
        for expansion, value in combination:
            new_expr = new_expr.replace(expansion, value)
        expanded.append(new_expr)

    # Join new expressions as union
    sep = Term(" | ", kind=TermKind.SYNTAX)
    expanded = insert_between(expanded, sep=sep)
    expanded = Expr(rule="union", children=tuple(expanded))
    return expanded


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
    """An expression that groups a logical part of an annotation expression.

    Parameters
    ----------
    rule : str
        The name of the (grammar) rule corresponding to this expression.
    children : Iterable of (Expr or Term)
        Sub-expressions or terms that make up this expression.
    """

    rule: str
    children: tuple[Self | Term, ...]

    def __post_init__(self):
        assert isinstance(self.rule, str)
        assert self.rule
        assert isinstance(self.children, tuple)

    @property
    def terms(self):
        """All terms in the expression.

        Returns
        -------
        terms : list of Term
        """
        return list(flatten_recursive(self))

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
            f"{type(self).__name__}({self.rule!r}, children=(\n{formatted_children}))"
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

    # TODO Candidate for optimization, benchmark
    #  Introduce `count` parameter, break iteration earlier?
    def replace(self, old, new):
        """Replace children in current expression and return new one.

        Parameters
        ----------
        old : Expr or Term
        new : Expr or Term

        Returns
        -------
        replaced : Expr
        """
        cls = type(self)
        new_children = []
        for child in self.children:
            new_child = None
            if child == old:
                new_child = new
            elif isinstance(child, cls):
                # Potentially replace in child's children
                new_child = child.replace(old, new)
            new_children.append(new_child or child)
        replaced = cls(rule=self.rule, children=tuple(new_children))
        return replaced

    def _filter_iter(self, func=None, /, **attrs):
        """Find matching children in the expression recursively.

        Parameters
        ----------
        func : Callable, optional
            Only return children for which ``func(child)`` is true.
        attrs : Any, optional
            Only return children for which have an attribute with a matching
            value.

        Yields
        ------
        match : Expr or Term
        """
        for child in self.children:
            matches = True
            if func:
                matches = func(child)
            for name, value in attrs.items():
                if not hasattr(child, name) or getattr(child, name) != value:
                    matches = False
                    break
            if matches:
                yield child
            if hasattr(child, "_filter_iter"):
                yield from child._filter_iter(func, **attrs)

    def find_all(self, func=None, /, **attrs):
        """Find all matching children in the expression recursively.

        Parameters
        ----------
        func : Callable, optional
            Only return children for which ``func(child)`` is true.
        attrs : Any, optional
            Only return children for which have an attribute with a matching
            value.

        Returns
        -------
        matches : list of (Expr or Term)
        """
        return list(self._filter_iter(func, **attrs))

    def try_find_one(self, func=None, /, **attrs):
        """Try to find one matching child in expression or return None

        Parameters
        ----------
        func : Callable, optional
            Only return children for which ``func(child)`` is true.
        attrs : Any, optional
            Only return children for which have an attribute with a matching
            value.

        Returns
        -------
        match : Expr or Term or None
        """
        matches = self.find_all(func, **attrs)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError(f"found multiple matches: {matches}")
        return None

    def find_one(self, func=None, /, **attrs):
        """Find exactly one matching child in expression.

        Parameters
        ----------
        func : Callable, optional
            Only return children for which ``func(child)`` is true.
        attrs : Any, optional
            Only return children for which have an attribute with a matching
            value.

        Returns
        -------
        match : Expr or Term
        """
        one = self.try_find_one(func, **attrs)
        if one is None:
            raise RuntimeError("found no match")
        return one


FORBIDDEN_KEYWORDS: Final[set[str]] = set(keyword.kwlist) - {"None", "True", "False"}


class QualnameIsForbidden(DocstubError):
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

    any_shape_expr: ClassVar[Expr] = Expr(
        rule="shape",
        children=(
            Expr(
                "subscription",
                children=(
                    Term("tuple", kind="name"),
                    Term("[", kind="syntax"),
                    Term("Any", kind="name"),
                    Term(", ", kind="syntax"),
                    Term("...", kind="literal"),
                    Term("]", kind="syntax"),
                ),
            ),
        ),
    )

    def __init__(self, *, reporter=None):
        """
        Parameters
        ----------
        reporter : ~.ContextReporter
        """
        reporter = reporter or ContextReporter(logger=logger)
        self.reporter = reporter.copy_with(logger=logger)

    def __default__(self, data, children, meta):
        """Create expression from rule which has no explicit method.

        Parameters
        ----------
        data : str
            Name of the rule/expression.
        children : list[Expr | Term]
            Children of the rule/expression.
        meta : lark.tree.Meta
            Meta data like position.

        Returns
        -------
        expr : Expr
        """
        if "__" in data:
            _prefix, data = data.split("__")
        return Expr(rule=data, children=tuple(children))

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

        if _qualname in FORBIDDEN_KEYWORDS:
            raise QualnameIsForbidden(_qualname)

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
        return self._create_subscription_expr(tree.children, rule="subscription")

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
        return self._create_subscription_expr(tree.children, rule="callable")

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
        out = self._create_subscription_expr(tree.children, rule="literal")
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
        items = [Term("Literal", kind=TermKind.NAME), *tree.children]
        out = self._create_subscription_expr(items, rule="natlang_literal")

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
        return self._create_subscription_expr(tree.children, rule="natlang_container")

    def natlang_array(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        match tree.children:
            # Array without dtype or shape
            case [Expr(rule="array_name") as array_name]:
                children = (array_name,)

            # Only dtype
            case [Expr(rule="array_name") as array_name, Expr(rule="dtype") as dtype]:
                # Insert missing shape before dtype
                children = (array_name, self.any_shape_expr, dtype)

            # Only shape
            case [Expr(rule="array_name") as array_name, Expr(rule="shape") as shape]:
                children = (array_name, shape)

            # Shape and dtype in any order
            case [
                Expr(rule="array_name") as array_name,
                Expr(rule="shape") as shape,
                Expr(rule="dtype") as dtype,
            ] | [
                Expr(rule="array_name") as array_name,
                Expr(rule="dtype") as dtype,
                Expr(rule="shape") as shape,
            ]:
                children = (array_name, shape, dtype)

            case _:
                raise ValueError(f"{tree.children=} did not match a case")

        if str(array_name) in ["array-like", "array_like"]:
            # `numpy.ArrayLike` is a union and doesn't support subscription.
            # So return expression without shape and dtype
            return Expr(rule="natlang_array", children=(array_name,))

        expr = self._create_subscription_expr(children, rule="natlang_array")

        # Expand shapes with optional dimensions and dtype unions
        expr = expand_expression(expr, expand_rule="to_expand")
        return expr

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
        # in `array_expression` (see `ARRAY_NAME` terminal in grammar)
        qualname = self.qualname(tree)
        array_name = Expr(rule="array_name", children=(qualname,))
        return array_name

    def dtype(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        children = [Term("np.dtype", kind=TermKind.NAME), *tree.children]
        expr = self._create_subscription_expr(children, rule="dtype")
        return expr

    def dtype_union(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        return self.union(tree)

    def dtype_to_expand(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        # Remap to rule=to_expand
        return Expr(rule="to_expand", children=tuple(tree.children))

    def shape(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : Expr
        """
        if len(tree.children) == 0:
            # 0-D shape
            children = self._create_subscription_expr(
                [Term("tuple", kind=TermKind.NAME), Term("()", kind=TermKind.SYNTAX)],
                rule="subscription",
            )
            shape = Expr(rule="shape", children=(children,))
            return shape

        expr = Expr(rule="shape", children=tuple(tree.children))

        if expr.find_all(lambda x: x == "...", kind=TermKind.LITERAL):
            # "..." effectively allows any shape
            return self.any_shape_expr

        # Count required and optional dimensions
        required_count = len(expr.find_all(rule="dim"))
        optional_count = 0
        for optional in expr.find_all(rule="optional_dimensions"):
            optional_count += len(optional.find_all(rule="dim"))
        required_count -= optional_count

        tuple_ = Term("tuple", kind=TermKind.NAME)
        dim = Term("int", kind=TermKind.NAME)

        # Construct a "shape tuple" for each of the possible dimension lengths
        shape_tuples = (
            (tuple_,) + (dim,) * length
            for length in range(required_count, required_count + optional_count + 1)
        )
        shape_tuples = tuple(
            self._create_subscription_expr(tuple_, rule="subscription")
            for tuple_ in shape_tuples
        )

        if len(shape_tuples) > 1:
            # Mark for expansion later
            shape_tuples = Expr(rule="to_expand", children=shape_tuples)
        elif len(shape_tuples) == 1:
            # Otherwise unpack single tuple
            shape_tuples = shape_tuples[0]

        shape = Expr(rule="shape", children=(shape_tuples,))
        return shape

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
    def _create_subscription_expr(children, *, rule):
        """Create a `name[...]` style expression.

        Parameters
        ----------
        children : Sequence[str]
            Children for the created expression, including the name before the square
            brackets.
        rule : str, optional
            The `rule` for the created expression.

        Returns
        -------
        out : Expr
        """
        sep = Term(", ", kind=TermKind.SYNTAX)
        container, *content = children
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
        ``%import doctype (start, ...)``. Defaults to ``DOCTYPE_GRAMMAR``.
    grammar_import_paths : tuple of (Path, ...)
        Additional paths to directories with grammars that are imported in
        `grammar`.
    transformer : lark.visitors.Transformer, optional
        Use a custom transformer to transform the parsed tree.
    reporter : ~.ContextReporter, optional
        Pass file and line context for logging.
    max_cache_size : int, optional
        Size of the LRU cache used to cache transpiled doctypes. Setting it
        to 0, disables the cache.

    Examples
    --------
    >>> transpile = DoctypeTranspiler()
    >>> transpile("tuple of (int, ...)")
    <Expr: 'tuple[int, ...]' rule='start'>
    >>> transpile("ndarray of dtype int and shape (M, N)")
    <Expr: 'ndarray[tuple[int, int], np.dtype[int]]' rule='start'>
    """

    def __init__(
        self,
        *,
        grammar=None,
        grammar_import_paths=(DOCTYPE_GRAMMAR_PATH.parent,),
        transformer=None,
        reporter=None,
        max_cache_size=1000,
    ):
        if grammar is None:
            grammar = DOCTYPE_GRAMMAR

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

        self.max_cache_size = max_cache_size
        self.reporter = reporter or ContextReporter(logger=logger)
        self._stats = Stats()
        self._grammar = grammar
        self._grammar_import_paths = grammar_import_paths
        self._transformer = transformer

        # Can't easily use `lru_cache` here because it should not be applied to
        # methods (B19, https://docs.astral.sh/ruff/rules/cached-instance-method).
        # An awkward workaround, assigning the LRU wrapper to the instance
        # instead of class, wouldn't be pickle-able.
        self._lru_cache = LRUMemoryCache(maxsize=max_cache_size)

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
        if doctype in self._lru_cache:
            self._stats.inc_counter("doctype_transpiler_cache_hits")
            expression = self._lru_cache[doctype]
            return expression

        # TODO Cache exceptions raised in this block?
        tree = self._parser.parse(doctype)
        try:
            expression = self._transformer.transform(tree=tree)
        except lark.visitors.VisitError as e:
            raise e.orig_exc from None  # Unwrap original error
        assert isinstance(expression, Expr)

        self._lru_cache[doctype] = expression
        self._stats.inc_counter("doctype_transpiler_cache_misses")
        return expression

    @property
    def stats(self):
        self._stats.append_to_list(
            "doctype_transpiler_curr_cache_size", len(self._lru_cache)
        )
        return self._stats

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

# File generated with docstub

import logging
import traceback
import warnings
from collections.abc import Generator, Iterable
from dataclasses import dataclass, field
from functools import cached_property

import click
import lark
import lark.visitors
import numpydoc.docscrape as npds

from ._analysis import PyImport, TypeMatcher
from ._doctype import BlacklistedQualname, Expr, Term, TermKind, parse_doctype
from ._report import ContextReporter, Stats
from ._utils import escape_qualname

logger: logging.Logger

def _update_qualnames(
    expr: Expr, *, _parents: tuple[Expr, ...] = ...
) -> Generator[tuple[tuple[Expr, ...], Term], str]: ...
@dataclass(frozen=True, slots=True, kw_only=True)
class Annotation:

    value: str
    imports: frozenset[PyImport] = ...

    def __post_init__(self) -> None: ...
    def __str__(self) -> str: ...
    @classmethod
    def many_as_tuple(cls, types: Iterable[Annotation]) -> Annotation: ...
    @classmethod
    def as_generator(
        cls,
        *,
        yield_types: Iterable[Annotation],
        receive_types: Iterable[Annotation] = ...,
        return_types: Iterable[Annotation] = ...,
    ) -> Annotation: ...
    def as_union_with_none(self) -> Annotation: ...
    @staticmethod
    def _aggregate_annotations(
        *types: Iterable[Annotation],
    ) -> tuple[list[str], set[PyImport]]: ...

FallbackAnnotation: Annotation

def _uncombine_numpydoc_params(
    params: list[npds.Parameter],
) -> Generator[npds.Parameter]: ...
def _red_partial_underline(doctype: str, *, start: int, stop: int) -> str: ...
def doctype_to_annotation(
    doctype: str,
    *,
    matcher: TypeMatcher | None = ...,
    reporter: ContextReporter | None = ...,
    stats: Stats | None = ...,
) -> Annotation: ...

class DocstringAnnotations:
    docstring: str
    matcher: TypeMatcher
    reporter: ContextReporter

    def __init__(
        self,
        docstring: str,
        *,
        matcher: TypeMatcher | None = ...,
        reporter: ContextReporter | None = ...,
        stats: Stats | None = ...,
    ) -> None: ...
    @cached_property
    def attributes(self) -> dict[str, Annotation]: ...
    @cached_property
    def parameters(self) -> dict[str, Annotation]: ...
    @cached_property
    def returns(self) -> Annotation | None: ...
    @cached_property
    def _returns(self) -> Annotation | None: ...
    @cached_property
    def _yields(self) -> Annotation | None: ...
    def _handle_missing_whitespace(self, param: npds.Parameter) -> npds.Parameter: ...
    def _section_annotations(self, name: str) -> dict[str, Annotation]: ...
    def _find_docstring_line(self, *substrings: str) -> int: ...

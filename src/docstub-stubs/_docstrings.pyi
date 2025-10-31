# File generated with docstub

import logging
import traceback
from collections.abc import Generator, Iterable
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar

import click
import lark
import lark.visitors
import numpydoc.docscrape as npds

from ._analysis import PyImport, TypeMatcher
from ._report import ContextReporter
from ._utils import DocstubError, escape_qualname

logger: logging.Logger

here: Path
grammar_path: Path

with grammar_path.open() as file:
    _grammar: str

_lark: lark.Lark

def _find_one_token(tree: lark.Tree, *, name: str) -> lark.Token: ...
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

class QualnameIsKeyword(DocstubError):
    pass

class DoctypeTransformer(lark.visitors.Transformer):
    matcher: TypeMatcher
    stats: dict[str, Any]

    blacklisted_qualnames: ClassVar[frozenset[str]]

    def __init__(
        self, *, matcher: TypeMatcher | None = ..., **kwargs: dict[Any, Any]
    ) -> None: ...
    def doctype_to_annotation(
        self, doctype: str, *, reporter: ContextReporter | None = ...
    ) -> tuple[Annotation, list[tuple[str, int, int]]]: ...
    def qualname(self, tree: lark.Tree) -> lark.Token: ...
    def rst_role(self, tree: lark.Tree) -> lark.Token: ...
    def union(self, tree: lark.Tree) -> str: ...
    def subscription(self, tree: lark.Tree) -> str: ...
    def natlang_literal(self, tree: lark.Tree) -> str: ...
    def natlang_container(self, tree: lark.Tree) -> str: ...
    def natlang_array(self, tree: lark.Tree) -> str: ...
    def array_name(self, tree: lark.Tree) -> lark.Token: ...
    def shape(self, tree: lark.Tree) -> lark.visitors._DiscardType: ...
    def optional_info(self, tree: lark.Tree) -> lark.visitors._DiscardType: ...
    def __default__(
        self, data: lark.Token, children: list[lark.Token], meta: lark.tree.Meta
    ) -> lark.Token | list[lark.Token]: ...
    def _match_import(self, qualname: str, *, meta: lark.tree.Meta) -> str: ...

def _uncombine_numpydoc_params(
    params: list[npds.Parameter],
) -> Generator[npds.Parameter]: ...

class DocstringAnnotations:
    docstring: str
    transformer: DoctypeTransformer
    reporter: ContextReporter

    def __init__(
        self,
        docstring: str,
        *,
        transformer: DoctypeTransformer,
        reporter: ContextReporter | None = ...,
    ) -> None: ...
    def _doctype_to_annotation(
        self, doctype: str, ds_line: int = ...
    ) -> Annotation: ...
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

# File generated with docstub

import enum
import logging
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import ClassVar, Literal

import libcst as cst
import libcst.matchers as cstm
from _typeshed import Incomplete

from ._analysis import PyImport, TypeMatcher
from ._docstrings import (
    Annotation,
    DocstringAnnotations,
    DoctypeTransformer,
    FallbackAnnotation,
)
from ._report import ContextReporter
from ._utils import module_name_from_path

logger: logging.Logger

def try_format_stub(stub: str) -> str: ...

class ScopeType(enum.StrEnum):

    MODULE = "module"
    CLASS = "class"
    FUNC = "func"
    METHOD = "method"
    CLASSMETHOD = "classmethod"
    STATICMETHOD = "staticmethod"

@dataclass(slots=True, frozen=True)
class _Scope:

    type: ScopeType
    node: cst.CSTNode | None = ...

    @property
    def has_self_or_cls(self) -> bool: ...
    @property
    def is_method(self) -> bool: ...
    @property
    def is_class_init(self) -> bool: ...
    @property
    def is_dataclass(self) -> bool: ...

def _get_docstring_node(
    node: cst.FunctionDef | cst.ClassDef | cst.Module,
) -> cst.SimpleString | cst.ConcatenatedString | None: ...
def _log_error_with_line_context(cls: Py2StubTransformer) -> Py2StubTransformer: ...
def _docstub_comment_directives(cls: Py2StubTransformer) -> Py2StubTransformer: ...
def _inline_node_as_code(node: cst.CSTNode) -> str: ...

class Py2StubTransformer(cst.CSTTransformer):
    transformer: DoctypeTransformer

    METADATA_DEPENDENCIES: ClassVar[tuple]

    _body_replacement: ClassVar[cst.SimpleStatementSuite]
    _Annotation_Incomplete: ClassVar[cst.Annotation]
    _Annotation_None: ClassVar[cst.Annotation]

    def __init__(self, *, matcher: TypeMatcher | None = ...) -> None: ...
    @property
    def current_source(self) -> Path: ...
    @current_source.setter
    def current_source(self, value: Path) -> None: ...
    @property
    def is_inside_function_def(self) -> bool: ...
    def python_to_stub(self, source: str, *, module_path: Path | None = ...) -> str: ...
    def visit_ClassDef(self, node: cst.ClassDef) -> Literal[True]: ...
    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef: ...
    def visit_FunctionDef(self, node: cst.FunctionDef) -> Literal[True]: ...
    def visit_IndentedBlock(self, node: cst.IndentedBlock) -> bool: ...
    def visit_SimpleStatementSuite(self, node: cst.SimpleStatementSuite) -> bool: ...
    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef: ...
    def leave_Param(
        self, original_node: cst.Param, updated_node: cst.Param
    ) -> cst.Param: ...
    def leave_Expr(
        self, original_node: cst.Expr, updated_node: cst.Expr
    ) -> cst.RemovalSentinel: ...
    def leave_Comment(
        self, original_node: cst.Comment, updated_node: cst.Comment
    ) -> cst.Comment: ...
    def leave_Assign(
        self, original_node: cst.Assign, updated_node: cst.Assign
    ) -> cst.Assign | cst.FlattenSentinel: ...
    def leave_AnnAssign(
        self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign
    ) -> cst.AnnAssign: ...
    def visit_Module(self, node: cst.Module) -> Literal[True]: ...
    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module: ...
    def visit_Lambda(self, node: cst.Lambda) -> Literal[False]: ...
    def leave_Decorator(
        self, original_node: cst.Decorator, updated_node: cst.Decorator
    ) -> cst.Decorator | cst.RemovalSentinel: ...
    @staticmethod
    def _parse_imports(
        imports: set[PyImport], *, current_module: str | None = ...
    ) -> tuple[cst.SimpleStatementLine, ...]: ...
    def _function_type(self, func_def: cst.FunctionDef) -> ScopeType: ...
    def _annotations_from_node(
        self, node: cst.FunctionDef | cst.ClassDef | cst.Module
    ) -> DocstringAnnotations: ...
    def _create_annotated_assign(
        self,
        *,
        name: str,
        trailing_semicolon: bool = ...,
        reporter: ContextReporter | None = ...
    ) -> cst.AnnAssign: ...
    def _insert_instance_attributes(
        self, updated_node: cst.ClassDef, attributes: dict[str, Annotation]
    ) -> cst.ClassDef: ...
    def _reporter_with_ctx(self, node: cst.CSTNode) -> ContextReporter: ...

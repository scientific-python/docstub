# File generated with docstub

import logging
from collections.abc import Sequence
from configparser import ConfigParser
from configparser import ConfigParser as Cfg
from typing import Any, Literal, Self, Union

from _typeshed import Incomplete

from . import AnotherType, CustomException

logger: logging.Logger

__all__ = [
    "ExampleClass",
    "func_empty",
]

def func_empty(a1: Incomplete, a2: Incomplete, a3: Incomplete) -> None: ...
def func_contains(
    a1: list[float],
    a2: dict[str, Union[int, str]],
    a3: Sequence[int | float],
    a4: frozenset[bytes],
    a5: tuple[int],
    a6: list[int, str],
    a7: dict[str, int],
) -> None: ...
def func_literals(
    a1: Literal[1, 3, "foo"], a2: Literal["uno", 2, "drei", "four"] = ...
) -> None: ...
def override_docstring_param(
    d1: dict[str, float], d2: dict[Literal["a", "b", "c"], int]
) -> None: ...
def override_docstring_return() -> list[Literal[-1, 0, 1] | float]: ...
def func_use_from_elsewhere(
    a1: CustomException,
    a2: ExampleClass,
    a3: ExampleClass.NestedClass,
    a4: ExampleClass.NestedClass,
) -> tuple[CustomException, ExampleClass.NestedClass]: ...
def func_use_from_import(a1: AnotherType, a2: Cfg) -> None: ...

class ExampleClass:

    b1: int

    class NestedClass:
        def method_in_nested_class(self, a1: complex) -> None: ...

    def __init__(self, a1: str, a2: float = ...) -> None: ...
    def method(
        self, a1: float, a2: float = ..., a3: float | None = ...
    ) -> list[float]: ...
    @staticmethod
    def some_staticmethod(a1: float, a2: str = ...) -> dict[str, Any]: ...
    @property
    def some_property(self) -> str: ...
    @some_property.setter
    def some_property(self, value: str) -> None: ...
    @classmethod
    def method_returning_cls(cls, config: ConfigParser) -> Self: ...
    @classmethod
    def method_returning_cls2(cls, config: ConfigParser) -> Self: ...

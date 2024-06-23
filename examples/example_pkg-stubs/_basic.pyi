import configparser
import logging
from collections.abc import Sequence
from typing import Any, Literal, Self, Union

from . import CustomException

logger = ...

__all__ = [
    "func_empty",
    "ExampleClass",
]

def func_empty(a1, a2, a3) -> None: ...
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
def func_use_from_elsewhere(
    a1: CustomException, a2: ExampleClass
) -> CustomException: ...

class ExampleClass:
    def __init__(self, a1: str, a2: float = ...) -> None: ...
    def method(self, a1: float, a2: float | None) -> list[float]: ...
    @staticmethod
    def some_staticmethod(a1: float, a2: float | None = ...) -> dict[str, Any]: ...
    @property
    def some_property(self) -> str: ...
    @some_property.setter
    def some_property(self, value: str) -> None: ...
    @classmethod
    def method_returning_cls(cls, config: configparser.ConfigParser) -> Self: ...
    @classmethod()
    def method_returning_cls2(cls, config: configparser.ConfigParser) -> Self: ...

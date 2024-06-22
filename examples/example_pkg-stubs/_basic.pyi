import configparser
import logging
from collections.abc import Sequence
from typing import Any, Literal, Self, Union

logger = logging.getLogger(__name__)

__all__ = [
    "func_empty",
    "ExampleClass",
]

def func_empty(a1: Any, a2: Any, a3: Any) -> None: ...
def func_contains(
    self,
    a1: list[float],
    a2: sequence[int] | float,
    a3: Sequence[int | float],
    a4: frozenset[bytes],
) -> tuple[tuple[int, ...], list[int]]: ...
def func_contains_dict(
    self,
    a1: dict[["str", "int | str"]],
    a2: dict[str, Union[int, str]],
    a3: mapping[["int", "str"]],
) -> dict[["int | str", "float"]]: ...
def func_literals(
    self, a1: Literal["A", "B", "C"], a2: Literal[0, "index", 1, "columns", None]
) -> None: ...
def func_literals(
    a1: Literal[1, 3, "foo"], a2: Literal["uno", 2, "drei", "four"] = ...
) -> None: ...

class ExampleClass:
    def __init__(self, a1: int, a2: float | None = ...) -> None: ...
    def method(self, a1: float, a2: float | None) -> list[float]: ...
    @staticmethod
    def some_staticmethod(a1: float, a2: float | None = ...) -> dict[str, Any]: ...
    @property
    def some_property(self) -> str: ...
    @classmethod
    def method_returning_cls(cls, config: configparser.ConfigParser) -> Self: ...

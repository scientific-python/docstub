import logging
from typing import Any, Literal, Sequence, Union

import numpy as np

logger = logging.getLogger(__name__)


def func_empty(a1: Any, a2: Any, a3: Any) -> None: ...


def func_object_with_path(
    a1: np.np.int8, a2: np.np.int16, a3: np.typing.DTypeLike, a4: np.typing.DTypeLike
) -> None: ...


def func_contains(
    a1: list[float],
    a2: dict[str, Union[int, str]],
    a3: Sequence[int | float, ...],
    a4: np.typing.DTypeLike,
) -> tuple[int, ...]: ...


def func_literals(
    a1: Literal[1] | Literal[3] | Literal["foo"] | None, a2: Any
) -> None: ...

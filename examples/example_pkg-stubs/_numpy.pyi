# File generated with docstub

from typing import Any

import numpy
import numpy as np
from numpy.typing import ArrayLike, NDArray

def func_object_with_numpy_objects(
    a1: numpy.int8, a2: np.int16, a3: numpy.typing.DTypeLike, a4: np.typing.DTypeLike
) -> None: ...
def func_ndarray(
    a1: NDArray,
    a2: np.NDArray,
    a3: NDArray[tuple[int, int], np.dtype[float]],
    a4: NDArray[tuple[int], np.dtype[np.uint8]] | None = ...,
) -> tuple[
    NDArray[tuple[Any, ...], np.dtype[np.uint8]],
    NDArray[tuple[Any, ...], np.dtype[complex]],
]: ...
def func_array_like(
    a1: ArrayLike, a2: ArrayLike, a3: ArrayLike, a4: ArrayLike
) -> tuple[ArrayLike, ArrayLike]: ...

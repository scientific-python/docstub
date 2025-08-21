"""NumPy and array specific docstring examples."""


def func_object_with_numpy_objects(a1, a2, a3, a4):
    """Dummy.

    Parameters
    ----------
    a1 : numpy.int8
    a2 : np.int16
    a3 : numpy.typing.DTypeLike
    a4 : np.typing.DTypeLike
    """


def func_ndarray(a1, a2, a3, a4=None):
    """Dummy.

    Parameters
    ----------
    a1 : ndarray
    a2 : np.NDArray
    a3 : ndarray of dtype float and shape (N, 3)
    a4 : ndarray of shape (1,) and dtype uint8

    Returns
    -------
    r1 : array of dtype uint8
    r2 : array of dtype complex and shape (1, ..., 3)
    """


def func_array_like(a1, a2, a3, a4):
    """Dummy.

    Parameters
    ----------
    a1 : array-like
    a2 : array_like
    a3 : array-like of dtype float and shape (N, 3)
    a4 : array-like of shape (1,) and dtype uint8

    Returns
    -------
    r1 : array-like of dtype uint8
    r2 : array_like of dtype complex and shape (1, ..., 3)
    """

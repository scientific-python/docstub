"""Docstring examples.

"""

from pprint import pprint


# Ensure multi-line
# comments are stripped
def func_empty(a1, a2, a3) -> None:
    """Dummy.

    Parameters
    ----------
    a1 :
    a2

    Returns
    -------
    list
    """
    pprint([a1, a2, a3])


def func_ndarray(a1, a2, a3, a4=None):
    """Dummy.

    Parameters
    ----------
    a1 : ndarray
    a2 : np.ndarray
    a3 : (N, 3) ndarray of float
    a4 : ndarray of shape (1,) and dtype uint8

    Returns
    -------
    r1 : uint8 array
    r2 : array of dtype complex and shape (1, ..., 3)
    """
    pprint([a1, a2, a3, a4])


def func_array_like(a1, a2, a3, a4):
    """Dummy.

    Parameters
    ----------
    a1 : array-like
    a2 : array_like
    a3 : (N, 3) array-like of float
    a4 : array-like of shape (1,) and dtype uint8

    Returns
    -------
    r1 : uint8 array-like
    r2 : array_like of dtype complex and shape (1, ..., 3)
    """
    pprint([a1, a2, a3, a4])


def func_object_with_path(a1, a2, a3, a4):
    """Dummy.

    Parameters
    ----------
    a1 : numpy.int8
    a2 : np.int16
    a3 : numpy.typing.DTypeLike
    a4 : np.typing.DTypeLike
    """
    pprint([a1, a2, a3, a4])


def func_contains(a1, a2, a3, a4):
    """Dummy.

    Parameters
    ----------
    a1 : list[float]
    a2 : dict[str, Union[int, str]]
    a3 : Sequence[int | float, ...]
    a4 : np.typing.DTypeLike

    Returns
    -------
    r1 : tuple of int
    """
    pprint([a1, a2, a3, a4])


def func_literals(a1, a2):
    """Dummy

    Parameters
    ----------
    a1 : {1, 3, "foo"}, optional
    """
    print([a1, a2])

"""Docstring examples.

"""

from pprint import pprint


def func_ndarray(a1, a2, a3, a4):
    """Dummy.

    Parameters
    ----------
    a1 : ndarray
    a2 : (N, 3) ndarray of float
    a3 : ndarray of shape (1,) and dtype uint8
    a4 : ndarray of dtype complex and shape (1, ..., 3)
    """
    pprint([a1, a2, a3, a4])

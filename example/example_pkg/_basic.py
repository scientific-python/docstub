"""Basic docstring examples.

Docstrings, including module-level ones, are stripped.
"""

# Existing imports are preserved
import logging

# Assign-statements are preserved
logger = logging.getLogger(__name__)  # Inline comments are stripped


def func_empty(a1, a2, a3):
    """Empty type descriptions will be replaced with "Any".

    Parameters
    ----------
    a1 :
    a2
    """
    pass


def func_object_with_path(a1, a2, a3, a4):
    """Dummy.

    Parameters
    ----------
    a1 : numpy.int8
    a2 : np.int16
    a3 : numpy.typing.DTypeLike
    a4 : np.typing.DTypeLike
    """
    pass


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
    pass


def func_literals(a1, a2):
    """Dummy

    Parameters
    ----------
    a1 : {1, 3, "foo"}, optional
    """
    pass

"""Basic docstring examples.

Docstrings, including module-level ones, are stripped.

Attributes
----------
logger : logging.Logger
"""

# Existing imports are preserved
import logging
from configparser import ConfigParser as Cfg  # noqa: F401
from typing import Literal

from . import AnotherType  # noqa: F401

# Assign-statements are preserved
logger = logging.getLogger(__name__)  # Inline comments are stripped


__all__ = [
    "ExampleClass",
    "func_empty",
]


def func_empty(a1, a2, a3):
    """Empty type descriptions will be replaced with "Any".

    Parameters
    ----------
    a1 :
    a2
    """


def func_contains(a1, a2, a3, a4, a5, a6, a7):
    """Dummy.

    Parameters
    ----------
    a1 : list[float]
    a2 : dict[str, Union[int, str]]
    a3 : collections.abc.Sequence[int | float]
    a4 : frozenset[bytes]
    a5 : tuple of int
    a6 : list of (int, str)
    a7 : dict of {str: int}
    """


def func_literals(a1, a2="uno"):
    """Dummy

    Parameters
    ----------
    a1 : {1, 3, "foo"}
    a2 : {"uno", 2, "drei", "four"}, default: "uno"
    """


def override_docstring_param(d1, d2: dict[Literal["a", "b", "c"], int]):
    """Check type hint is kept and overrides docstring.

    Parameters
    ----------
    d1 : dict of {str : float}
    d2 : dict of {str : int}
    """


def override_docstring_return() -> list[Literal[-1, 0, 1] | float]:
    """Check type hint is kept and overrides docstring.

    Returns
    -------
    {"-inf", 0, 1, "inf"}
    """


def func_use_from_elsewhere(a1, a2, a3, a4):
    """Check if types with full import names are matched.

    Parameters
    ----------
    a1 : example_pkg.CustomException
    a2 : ExampleClass
    a3 : example_pkg._basic.ExampleClass.NestedClass
    a4 : ExampleClass.NestedClass

    Returns
    -------
    r1 : ~.CustomException
    r2 : ~.NestedClass
    """


def func_use_from_import(a1, a2):
    """Check using symbols made available in this module with from imports.

    Parameters
    ----------
    a1 : AnotherType
    a2 : Cfg
    """


class ExampleClass:
    """Dummy.

    Parameters
    ----------
    a1 : str
    a2 : float, default 0

    Attributes
    ----------
    b1 : Sized
    """

    b1: int

    class NestedClass:
        def method_in_nested_class(self, a1):
            """

            Parameters
            ----------
            a1 : complex
            """

    def __init__(self, a1, a2=0):
        pass

    def method(self, a1, a2=0, a3=None):
        """Dummy.

        Parameters
        ----------
        a1 : float
        a2 : float, optional
        a3 : float, optional

        Returns
        -------
        r1 : list of float
        """

    @staticmethod
    def some_staticmethod(a1, a2="uno"):
        """Dummy

        Parameters
        ----------
        a1 : float
        a2 : str, optional

        Returns
        -------
        r1 : dict[str, Any]
        """

    @property
    def some_property(self):
        """Dummy

        Returns
        -------
        name : str
        """
        return str(self)

    @some_property.setter
    def some_property(self, value):
        """Dummy

        Parameters
        ----------
        value : str
        """

    @classmethod
    def method_returning_cls(cls, config):
        """Using `Self` in context of classmethods is supported.

        Parameters
        ----------
        config : configparser.ConfigParser
            Configuation.

        Returns
        -------
        out : Self
            New class.
        """

    @classmethod
    def method_returning_cls2(cls, config):
        """Using `Self` in context of classmethods is supported.

        Parameters
        ----------
        config : configparser.ConfigParser
            Configuation.

        Returns
        -------
        out : Self
            New class.
        """

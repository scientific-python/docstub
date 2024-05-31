"""Basic docstring examples.

Docstrings, including module-level ones, are stripped.
"""

# Existing imports are preserved
import logging

# Assign-statements are preserved
logger = logging.getLogger(__name__)  # Inline comments are stripped


__all__ = [
    "func_empty",
    "ExampleClass",
]


def func_empty(a1, a2, a3):
    """Empty type descriptions will be replaced with "Any".

    Parameters
    ----------
    a1 :
    a2
    """
    pass


def func_contains(self, a1, a2, a3, a4):
    """Dummy.

    Parameters
    ----------
    a1 : list[float]
    a2 : dict[str, Union[int, str]]
    a3 : Sequence[int | float]
    a4 : frozenset[bytes]

    Returns
    -------
    r1 : tuple of int
    r2 : list of int
    """
    pass


def func_literals(a1, a2="uno"):
    """Dummy

    Parameters
    ----------
    a1 : {1, 3, "foo"}
    a2 : {"uno", 2, "drei", "four"}, default: "uno"
    """
    pass


class ExampleClass:
    # TODO also take into account class level docstring

    def __init__(self, a1, a2=None):
        """
        Parameters
        ----------
        a1 : int
        a2 : float, optional
        """

    def method(self, a1, a2):
        """Dummy.

        Parameters
        ----------
        a1 : float
        a2 : float, optional

        Returns
        -------
        r1 : list of float
        """
        pass

    @staticmethod
    def some_staticmethod(a1, a2="uno"):
        """Dummy

        Parameters
        ----------
        a1 : float
        a2 : float, optional

        Returns
        -------
        r1 : dict[str, Any]
        """
        pass

    @property
    def some_property(self):
        """Dummy

        Returns
        -------
        name : str
        """
        return str(self)

    @classmethod
    def from_config(cls, config):
        """Create ExampleClass from configuration.

        Parameters
        ----------
        config : configparser.ConfigParser
            Configuation.

        Returns
        -------
        out : ExampleClass
            New class.
        """
        pass

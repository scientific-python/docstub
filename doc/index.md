# docstub's documentation

**Version**:

Welcome! [docstub]{.title-ref} is a command-line tool to generate
[Python](https://www.python.org) stub files (i.e., PYI files) from type
descriptions found in [numpydoc](https://numpydoc.readthedocs.io)-style
docstrings.

[numpy](https://numpy.org), [scipy](https://docs.scipy.org),
[scikit-image](https://scikit-image.org/), and others
follow a common convention for docstrings that provides for
consistency, while also allowing toolchains such as
[numpydoc](https://numpydoc.readthedocs.io) to produce well-formatted
reference guides.

Our project follows the [SciPy code of
conduct](https://github.com/scipy/scipy/blob/master/doc/source/dev/conduct/code_of_conduct.rst).

## Basics

Consider a function written as follows:

```py
def example_metric(image0, image1, sigma=1.0, method='standard'):
    """Pretend to calculate a local metric between two images.

    Parameters
    ----------
    image0 : array-like
        First image.
    image1 : array_like
        Second image.
    sigma : float
        Sigma parameter.
    method : {'standard', 'modified'}, optional, default = 'standard'
        The method to use for calculating the metric.

    Returns
    -------
    met : ndarray of dtype float
    """
    pass
```

Feeding this input to docstub results in the following output:

```py
def example_metric(
    image0: ArrayLike,
    image1: ArrayLike,
    sigma: float = ...,
    method: Literal["standard", "modified"] = ...,
) -> NDArray[float]
```

As you can see, it is a typed function signature, where types are read from
the well-enough written docstring.

In practice, you run the docstub command on a .py file and get a corresponding
.pyi file containing the same imports, the same variables, with classes and
functions replaced with their respective typed signatures.

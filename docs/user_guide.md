# User guide

> [!NOTE]
> **In early development!**
> Expect bugs, missing features, and incomplete documentation.
> Docstub is still evaluating which features it needs to support as the community gives feedback.
> Several features are experimental and included to make adoption of docstub easier.
> Long-term, some of these might be discouraged or removed as docstub matures.


## Installation

Docstub is available as a [package on PyPI](https://pypi.org/project/docstub/) and can be installed from there with your favorite package manager. E.g.:

```shell
pip install docstub
```

In case you want to check out an unreleased version you can install directly from the repository with:

```shell
pip install docstub @ git+https://github.com/scientific-python/docstub'
```

To pin to a specific commit you can append `@COMMIT_SHA` to the repository URL above.


## Getting started

Consider a simple example with the following documented function

<!--- The following block is checked by the test suite --->
<!--- begin example.py --->

```python
# example.py

def example_metric(image, *, mask=None, sigma=1.0, method='standard'):
    """Pretend to calculate a local metric between two images.

    Parameters
    ----------
    image : array-like
        First image.
    mask : array of dtype uint8, optional
        Second image.
    sigma : float or Iterable of float, default: 1.0
        Sigma value for each dimension in `image`. A single value is broadcast
        to all dimensions.
    method : {'standard', 'modified'}, default: 'standard'
        The method to use for calculating the metric.

    Returns
    -------
    metric : ndarray of dtype float
    """
    pass
```

<!--- end example.py --->

Feeding this input to docstub with

```shell
docstub run example.py
```

will create `example.pyi` in the same directory

<!--- The following block is checked by the test suite --->
<!--- begin example.pyi --->

```python
# File generated with docstub

from collections.abc import Iterable
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

def example_metric(
    image: ArrayLike,
    *,
    mask: NDArray[np.uint8] | None = ...,
    sigma: float | Iterable[float] = ...,
    method: Literal["standard", "modified"] = ...
) -> NDArray[float]: ...
```

<!--- end example.pyi --->

There are several interesting things to note here:

- Many existing conventions that the scientific Python ecosystem uses, will work out of the box.
  In this case, docstub knew how to translate `array-like`, `array of dtype uint8` into a valid Python type for the stub file.
  In a similar manner, `or` can be used as a "natural language" alternative to `|` to form unions.
  You can find more details in [Typing syntax in docstrings](typing_syntax.md).

- Optional arguments that default to `None` are recognized and a `| None` is appended automatically.
  The `optional` or `default = ...` part don't influence the annotation.

- Referencing the `float` and `Iterable` types worked out of the box.
  All builtin types as well as types from the standard libraries `typing` and `collections.abc` module can be used like this.
  Necessary imports will be added automatically to the stub file.


## Referencing types & nicknames

To translate a type from a docstring into a valid type annotation, docstub needs to know where names in that type are defined from where to import them.
Out of the box, docstub will know about builtin types such as `int` or `bool` that don't need an import, and types in `typing`, `collections.abc` from Python's standard library.
It will source these from the Python environment it is installed in.
In addition to that, docstub will collect all types in the package directory you are running it on.
This also includes imported types, which you can then use within the scope of the module that imports them.

However, you can also tell docstub directly about external types in a configuration file.
Docstub will look for a `pyproject.toml` or `docstub.toml` in the current working directory.
Or, you can point docstub at TOML file(s) explicitly using the `--config` option.
In these configuration file(s) you can declare external types directly with

```toml
[tool.docstub.types]
Path = "pathlib"
Figure = "matplotlib.pyplot"
```

This will enable using `Path` and `Figure` anywhere in docstrings.
Alternatively, you can declare an entire prefix with

```toml
[tool.docstub.type_prefixes]
ski = "skimage"
"sklearn.tree" = "sklearn.tree"
```

which will enable any type that is prefixed with `ski.` or `sklearn.tree.`, e.g. `ski.transform.AffineTransform` or `sklearn.tree.DecisionTreeClassifier`.

> [!IMPORTANT]
> Docstub doesn't check that types actually exist or if a symbol is a valid type.
> We always recommend validating the generated stubs with a full type checker!

> [!TIP]
> Docstub currently collects types statically.
> So it won't see compiled modules and won't be able to generate stubs for them.
> For now, you can add stubs for compiled modules yourself and docstub will include these in the generated output.
> Support for dynamic type collection is on the roadmap.


The codebase docstub is running on may already use existing conventions to refer to common types (or you may want to do so).
Docstub refers to these alternatives as "type nicknames".
You can declare type nicknames in a configuration file with
```toml
[tool.docstub.type_nicknames]
func = "Callable"
```


## Adopting docstub gradually

Adopting docstub on a large codebase may initially generate many errors.
Two command line options can help addressing these errors gradually:

* `--group-errors` will group identical errors together.
  This helps identifying common groups of errors that may be addressed in one go.

* `--allow-errors` puts an upper limit (["ratchet"](https://qntm.org/ratchet)) on the number of allowed errors.
  This way you can adjust the upper bound of allowed errors as they are addressed.
  Useful, if you are running in docstub in continuous integration.

> [!TIP]
> If you are trying out docstub and have feedback or problems, we'd love to hear from you!
> Feel welcome to [open an issue](https://github.com/scientific-python/docstub/issues/new/choose). 🚀


## Dealing with typing problems

For various reasons – missing features in docstub, or limitations of Python's typing system – it may not always be possible to correctly type something in a docstring.
In those cases, you docstub provides a few approaches to dealing with this.


### Use inline type annotation

Docstub will always preserve inline type annotations, regardless of what the docstring contains.
This is useful for example, if you want to express something that isn't yet supported by Python's type system.

E.g., consider the docstring type of `ord` parameter in [`numpy.linalg.matrix_norm`](https://numpy.org/doc/stable/reference/generated/numpy.linalg.matrix_norm.html)
```rst
ord : {1, -1, 2, -2, inf, -inf, ‘fro’, ‘nuc’}, optional
```
[Python's type system currently can't express floats as literal types](https://typing.python.org/en/latest/spec/literal.html#:~:text=Floats%3A%20e.g.%20Literal%5B3.14%5D) – such as `inf`.
We don't want to make the type description here less specific to users, so instead, you could handle this with a less constrained inline type annotation like
```python
ord: Literal[1, -1, 2, -2, 'fro', 'nuc'] | float
```
Docstub will include the latter less constrained type in the stubs.
This allows you to keep the information in the docstring while still having valid – if a bit less constrained – stubs.


### Preserve code with comment directive

At its heart, docstub transforms Python source files into stub files.
You can tell docstub to temporarily stop that transformation for a specific area with a comment directive.
Wrapping lines of code with `docstub: off` and `docstub: on` comments will preserve these lines completely.

E.g., consider the following example:
```python
class Foo:
    # docstub: off
    a: int = None
    b: str = ""
    # docstub: on
    c: int = None
    d: str = ""
```
will leave the guarded parameters untouched in the resulting stub file:
```python
class Foo:
    a: int = None
    b: str = ""
    c: int
    d: str
```

### Write a manual stub file

If all of the above does not solve your issue, you can fall back to writing a correct stub file by hand.
Docstub will preserve this file and integrated it with other automatically generated stubs.

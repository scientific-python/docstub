# User guide

> [!NOTE] In early development!
> Expect bugs, missing features, and incomplete documentation.
> Docstub is still evaluating which features it needs to support as the community gives feedback.
> Several features are experimental and included to make adoption of docstub easier.
> Long-term, some of these might be discouraged or removed as docstub matures.


## Installation

While a docstub package is already available on PyPI, we recommend trying out docstub by installing directly from GitHub with

```shell
pip install 'docstub [optional] @ git+https://github.com/scientific-python/docstub'
```

If you want to pin to a certain commit you can append `@COMMIT_SHA` to the repo URL above.


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
    sigma : float or Iterable of float, optional
        Sigma value for each dimension in `image`. A single value is broadcast
        to all dimensions.
    method : {'standard', 'modified'}, optional, default = 'standard'
        The method to use for calculating the metric.

    Returns
    -------
    met : ndarray of dtype float
    """
    pass
```

<!--- end example.py --->

Feeding this input to docstub with

```shell
docstub simple_script.py
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
  In this case, docstub knew how to translate `array-like`, `array of dtype uint8` into a valid type annotation in the stub file.
  In a similar manner, `or` can be used as a "natural language" alternative to `|`.
  You can find more details in [Typing syntax in docstrings](typing_syntax.md).

- Optional arguments that default to `None` are recognized and a `| None` is appended automatically if the type doesn't include it already.
  The `optional` or `default = ...` part don't influence the annotation.

- Common container types from Python's standard library such as `Iterable` can be used and a necessary import will be added automatically.


## Using types & nicknames

To translate a type from a docstring into a valid type annotation, docstub needs to know where that type originates from and how to import it.
Out of the box, docstub will know about builtin types such as `int` or `bool` that don't need an import, and types in `typing`, `collections.abc` from Python's standard library.
It will source these from the Python environment it is installed in.
In addition to that, docstub will collect all types in the package directory you are running it on.

However, if you want to use types from third-party libraries you can tell docstub about them in a configuration file.
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

In both of these cases, docstub doesn't check that these types actually exist.
Testing the generated stubs with a type checker is recommended.

> [!TIP] Limitations & roadmap
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

> [!TIP] Get in touch!
> If you are trying out docstub and have feedback or problems, we'd love to hear from you!
> Feel welcome to [open an issue](https://github.com/scientific-python/docstub/issues/new/choose) 🚀.

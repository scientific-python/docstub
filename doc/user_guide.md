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

- Common container types from Pythons standard library such as `Iterable` can be used and a necessary import will be added automatically.


## Importing types

TBD


## Adding your own aliases for docstring descriptions

TBD


## Adopting docstub gradually

TBD

`--group-errors`

`--allow-errors`

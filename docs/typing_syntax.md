# Extended typing syntax

Any valid Python {term}`annotation expression` can be used in a docstrings as is.
However, Docstub extends [Python's conventional typing syntax](https://typing.python.org/en/latest/index.html) with several "natural language" expressions that are commonly used in the scientific Python ecosystem.
This extended syntax is defined in its own [grammar](#appendix-grammar).

Docstrings should follow a form that is inspired by the [NumPyDoc style](https://numpydoc.readthedocs.io/en/latest/format.html):
```none
Section name
------------
name : doctype, optional_info
  Description.
```

- `name` might be the name of a parameter, attribute or similar.
- `doctype` contains the actual type information that will be transformed into an {term}`annotation expression`.
  Here you can use the "natural language" expressions that are documented below.
- `optional_info` is optional and captures anything after the first (top-level) comma.
  It is useful to provide additional information for readers.
  Its presence and content doesn't affect the generated {term}`annotation expression`.

Combining multiple names that share a doctype and description is supported.
  For example `a, b : int` is equivalent to defining both separately.


## Unions

In addition to Python's conventional shorthand `|` syntax for [union types](https://typing.python.org/en/latest/spec/concepts.html#union-types), you can use `or` to join types.

| doctype        | Python annotation |
|----------------|-------------------|
| `X or Y`       | `X \| Y`          |
| `int or float` | `int \| float`    |


## Containers

The content of containers can be typed using a `CONTAINER of X` like form.
This extends the basic subscription syntax for [generics](https://typing.python.org/en/latest/spec/generics.html#generics).

| doctype                 | Python annotation   |
|-------------------------|---------------------|
| `CONTAINER of X`        | `CONTAINER[X]`      |
| `CONTAINER of (X or Y)` | `CONTAINER[X \| Y]` |

For the simple case `CONTAINER of X`, where `X` is a name, you can append `(s)` to indicate the plural form.
For example, `list of float(s)`.

Variants of for [**tuples**](https://typing.python.org/en/latest/spec/tuples.html)

| doctype             | Python annotation |
|---------------------|-------------------|
| `tuple of (X, Y)`   | `tuple[X, Y]`     |
| `tuple of (X, ...)` | `tuple[X, ...]`   |

and **mappings** exist.

| doctype              | Python annotation |
|----------------------|-------------------|
| `MAPPING of {X: Y}`  | `MAPPING[X, Y]`   |
| `dict of {str: int}` | `dict[str, int]`  |


:::{tip}
While it is possible to nest these variants, it decreases the readability.
For complex nested annotations with nested containers, consider using Python's conventional syntax.
In the future, docstub may warn against or disallow nesting these natural language variants.
:::


(natlang-array)=
## NDArrays with shape and dtype

This "natural language" expression describes shape and dtype information for [NumPy arrays](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.html).
The basic form is as follows:

| doctype                                | Python annotation                         |
|----------------------------------------|-------------------------------------------|
| `ARRAY of shape SHAPE`                 | `ARRAY[SHAPE]`                            |
| `ARRAY of dtype DTYPE`                 | `ARRAY[tuple[Any, ...], np.dtype[DTYPE]]` |
| `ARRAY of dtype DTYPE and shape SHAPE` | `ARRAY[SHAPE, np.dtype[DTYPE]]`           |
| `ARRAY of shape SHAPE and dtype DTYPE` | `ARRAY[SHAPE, np.dtype[DTYPE]]`           |

Only `array`, `ndarray`, `array-like` and `array_like` can be used in place of `ARRAY` above.
`array-like` and `array_like` map to {obj}`numpy.typing.ArrayLike` which does not support adding shape and dtype information.
In this case, Docstub omits the dtype and shape automatically.

`SHAPE` can be given in forms like `(n,)`, `(M, N)`, `(x, y, 4)`, or `(..., 2)`.
Optional dimensions are supported by enclosing them in square brackets like `(x, y[, z])`.

`DTYPE` can be any valid name or a union of names.

For example:

| doctype                                  | Python annotation                          |
|------------------------------------------|--------------------------------------------|
| `array of dtype int`                     | `NDArray[tuple[Any, ...], np.dtype[int]]`  |
| `array of shape (..., 2)`                | `NDArray[tuple[Any, ...]]`                 |
| `array of shape (x, y[, z])`             | `NDArray[tuple[int, int]]`<br>`\| NDArray[tuple[int, int, int]]`                 |
| `ndarray of dtype bool and shape (4, 4)` | `NDArray[tuple[int, int], np.dtype[bool]]` |
| `array-like of dtype float`              | `ArrayLike`                                |
| `array_like of shape (M, 2)`             | `ArrayLike`                                |


## Literals

[Literals](https://typing.python.org/en/latest/spec/literal.html#literals) indicate a concrete value instead of type.
Instead of using [`typing.Literal`](https://docs.python.org/3/library/typing.html#typing.Literal), you can enclose literal values in `{...}` in docstrings.

| doctype                   | Python annotation                |
|---------------------------|----------------------------------|
| `{-1, 0, 3, True, False}` | `Literal[-1, 0, 3, True, False]` |
| `{"red", "blue", None}`   | `Literal["red", "blue", None]`   |

:::{tip}
Enclosing a single value `{X}` is allowed.
However, `Literal[X]` is more explicit.
:::

:::{warning}
Python's `typing.Literal` only supports a restricted set of parameters.
For example, `float` literals are not yet supported by the type system but are allowed by docstub.
Use a broader inlined type such as `Literal[0, 1] | float` if you want to use something like `{0, .5, 1}` in the docstring.
:::

## reStructuredText role

Since docstrings are also used to generate documentation with Sphinx, you may want to use [restructuredText roles](https://docutils.sourceforge.io/docs/ref/rst/roles.html).
This is supported anywhere in where a {term}`type name` used in a {term}`doctype`.

| doctype                 | Python annotation |
|-------------------------|-------------------|
| `` `X` ``               | `X`               |
| ``:ref:`X` ``           | `X`               |
| ``:class:`X`[Y, ...] `` | `X[Y, ...]`       |
| ``:class:`Y.X` ``       | `Y.X`             |
| ``:py:class:`Y.X` ``    | `Y.X`             |


---

## Appendix: Grammar

:::{literalinclude} ../src/docstub/doctype.lark
:caption: doctype.lark
:::

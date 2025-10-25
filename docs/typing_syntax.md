# Typing syntax in docstrings

Docstub defines its own [grammar](../src/docstub/doctype.lark) to parse and transform type information in docstrings into valid Python type expressions.
This grammar fully supports [Python's conventional typing syntax](https://typing.python.org/en/latest/index.html).
So any {term}`annotation expression` that is valid in Python, can be used in a docstrings as is.
In addition, docstub extends this syntax with several "natural language" expressions that are commonly used in the scientific Python ecosystem.

Docstrings should follow a form that is inspired by the [NumPyDoc style](https://numpydoc.readthedocs.io/en/latest/format.html):
```none
Section namew
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

| Docstring type | Python type annotation |
|----------------|------------------------|
| `X or Y`       | `X \| Y`               |
| `int or float` | `int \| float`         |


## Containers

The content of containers can be typed using a `CONTAINER of X` like form.
This extends the basic subscription syntax for [generics](https://typing.python.org/en/latest/spec/generics.html#generics).

| Docstring type          | Python type annotation |
|-------------------------|------------------------|
| `CONTAINER of X`        | `CONTAINER[X]`         |
| `CONTAINER of (X or Y)` | `CONTAINER[X \| Y]`    |

For the simple case `CONTAINER of X`, where `X` is a name, you can append `(s)` to indicate the plural form.
For example, `list of float(s)`.

Variants of for [**tuples**](https://typing.python.org/en/latest/spec/tuples.html)

| Docstring type      | Python type annotation |
|---------------------|------------------------|
| `tuple of (X, Y)`   | `tuple[X, Y]`          |
| `tuple of (X, ...)` | `tuple[X, ...]`        |

and **mappings** exist.

| Docstring type       | Python type annotation |
|----------------------|------------------------|
| `MAPPING of {X: Y}`  | `MAPPING[X, Y]`        |
| `dict of {str: int}` | `dict[str, int]`       |


:::{tip}
While it is possible to nest these variants repeatedly, it decreases the readability.
For complex nested annotations with nested containers, consider using Python's conventional syntax.
In the future, docstub may warn against or disallow nesting these natural language variants.
:::


## Shape and dtype syntax for arrays

This expression allows adding shape and datatype information for data structures like [NumPy arrays](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.html).

`array` and `ndarray`, and `array-like` and `array_like` can be used interchange-ably for the variable `ARRAY` below.

| Docstring type                         | Python type annotation |
|----------------------------------------|------------------------|
| `ARRAY of dtype DTYPE`                 | `ARRAY[DTYPE]`         |
| `ARRAY of dtype DTYPE and shape SHAPE` | `ARRAY[DTYPE]`         |
| `ARRAY of shape SHAPE`                 | `ARRAY[DTYPE]`         |
| `ARRAY of shape SHAPE and dtype DTYPE` | `ARRAY[DTYPE]`         |

For example

| Docstring type                           | Python type annotation |
|------------------------------------------|------------------------|
| `array of dtype int`                     | `ndarray[int]`         |
| `ndarray of dtype bool and shape (4, 4)` | `ndarray[bool]`        |
| `array-like of dtype float`              | `ArrayLike[float]`     |
| `array_like of shape (M, 2)`             | `ArrayLike`            |


:::{note}
Noting the **shape** of an array in the docstring is supported.
However, [support for including shapes in generated stubs](https://github.com/scientific-python/docstub/issues/76) is not yet included in docstub.
:::


## Literals

[Literals](https://typing.python.org/en/latest/spec/literal.html#literals) indicate a concrete value instead of type.
Instead of using [`typing.Literal`](https://docs.python.org/3/library/typing.html#typing.Literal), you can enclose literal values in `{...}` in docstrings.

| Docstring type            | Python type annotation           |
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
Addressing this use case is on the roadmap.
See [issue 47](https://github.com/scientific-python/docstub/issues/47) for more details.
:::

## reStructuredText role

Since docstrings are also used to generate documentation with Sphinx, you may want to use [restructuredText roles](https://docutils.sourceforge.io/docs/ref/rst/roles.html).
This is supported anywhere in where a {term}`type name` is used in a {term}`doctype`.

| Docstring type          | Python type annotation |
|-------------------------|------------------------|
| `` `X` ``               | `X`                    |
| ``:ref:`X` ``           | `X`                    |
| ``:class:`X`[Y, ...] `` | `X[Y, ...]`            |
| ``:class:`Y.X` ``       | `Y.X`                  |
| ``:py:class:`Y.X` ``    | `Y.X`                  |

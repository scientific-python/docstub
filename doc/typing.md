# Typing with docstub

> [!NOTE]
> This document is work in progress and might be incomplete.


## Docstring annotation syntax

To extract type information in docstrings, docstub expects these to follow the NumPyDoc style:

```
Section name
------------
name : type_description (, optional) (, extra_info)
  Verbose
```

- `name` might be the name of a parameter or attribute.
  But typing names in other sections like "Returns" or "Yields" is also supported.
- `type_description`
- `optional`
- `extra_info`


[Grammar reference](../src/docstub/doctype.lark)


### Or expression

| Docstring type | Python type annotation |
|----------------|------------------------|
| `X or Y`       | `X \| Y`               |
| `int or float` | `int \| float`         |


### Containers

| Docstring type             | Python type annotation |
|----------------------------|------------------------|
| `CONTAINER of X`           | `CONTAINER[X]`         |
| `CONTAINER of (X \| Y)`    | `CONTAINER[X \| Y]`    |
| `CONTAINER of (X, Y, ...)` | `CONTAINER[X, Y, ...]` |


### Shape and dtype syntax for arrays

`array` and `ndarray`, and `array-like` and `array_like` can be used interchange-ably.

| Docstring type              | Python type annotation |
|-----------------------------|------------------------|
| `array of DTYPE`            | `ndarray[DTYPE]`       |
| `ndarray of dtype DTYPE`    | `ndarray[DTYPE]`       |
| `array-like of DTYPE`       | `ArrayLike[DTYPE]`     |
| `array_like of dtype DTYPE` | `ArrayLike[DTYPE]`     |

> [!NOTE]
> Noting the **shape** of an array in the docstring is supported.
> However, typing is not yet possible and the shape doesn't impact the resulting annotation.

| Docstring type           | Python type annotation |
|--------------------------|------------------------|
| `(3,) array of DTYPE`    | `ndarray[DTYPE]`       |
| `(X, Y) array of DTYPE`  | `ndarray[DTYPE]`       |
| `([P,] M, N) array-like` | `ArrayLike`            |
| `(M, ...) ndarray`       | `ArrayLike`            |


### Literals

| Docstring type      | Python type annotation     |
|---------------------|----------------------------|
| `{1, "string", .2}` | `Literal[1, "string", .2]` |
| `{X}`               | `Literal[X]`               |


### reStructuredText role

| Docstring type    | Python type annotation |
|-------------------|------------------------|
| ``:ref:`X` ``     | `X`                    |
| ``:class:`Y.X` `` | `Y.X`                  |

Can be used in any context where a qualified name can be used.


## Special cases

### Disable docstub with comment directive

```python
class Foo:
    """Docstring."""

    # docstub: off
    a: int = None
    b: str = ""
    c: int = None
    b: str = ""
    # docstub: on
```

# Typing syntax in docstrings

> [!NOTE] In early development!
> Expect bugs, missing features, and incomplete documentation.
> Docstub is still evaluating which features it needs to support as the community gives feedback.
> Several features are experimental and included to make adoption of docstub easier.
> Long-term, some of these might be discouraged or removed as docstub matures.

Docstub defines its own [grammar](../src/docstub/doctype.lark) to parse and transform type information in docstrings into valid type annotations.
This grammar fully supports [Python's conventional typing syntax](https://typing.python.org/en/latest/index.html).
So any type annotation that is valid in Python, can be used in a docstrings as is.
In addition, docstub extends this syntax with several "natural language" expressions that are commonly used in the scientific Python ecosystem.

Docstrings are expected to follow the NumPyDoc style:
```
Section name
------------
name : annotation, optional, extra_info
  Description.
```

- `name` might be the name of a parameter or attribute.
  Other sections like "Returns" or "Yields" are supported.
- `annotation` the actual type information that will be transformed into the type annotation.
- `optional` and `extra_info` can be appended to provide additional information.
  Their presence and content doesn't currently affect the resulting type annotation.


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
E.g., `list of float(s)`.

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


> [!TIP]
> While it is possible to nest these variants repeatedly, it is discouraged to do so to keep type descriptions readable.
> For complex annotations with nested containers, consider using Python's conventional syntax.
> In the future, docstub may warn against or disallow nesting these natural language variants.


## Shape and dtype syntax for arrays

This expression allows adding shape and datatype information for data structures like [NumPy arrays](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.html).

`array` and `ndarray`, and `array-like` and `array_like` can be used interchange-ably.

| Docstring type              | Python type annotation |
|-----------------------------|------------------------|
| `array of DTYPE`            | `ndarray[DTYPE]`       |
| `ndarray of dtype DTYPE`    | `ndarray[DTYPE]`       |
| `array-like of DTYPE`       | `ArrayLike[DTYPE]`     |
| `array_like of dtype DTYPE` | `ArrayLike[DTYPE]`     |

> [!NOTE]
> Noting the **shape** of an array in the docstring is supported.
> However, Python's typing system is not yet able to express this information.
> It is therefore not included in the resulting type annotation.

| Docstring type           | Python type annotation |
|--------------------------|------------------------|
| `(3,) array of DTYPE`    | `ndarray[DTYPE]`       |
| `(X, Y) array of DTYPE`  | `ndarray[DTYPE]`       |
| `([P,] M, N) array-like` | `ArrayLike`            |
| `(M, ...) ndarray`       | `ArrayLike`            |


## Literals

[Literals](https://typing.python.org/en/latest/spec/literal.html#literals) indicate a concrete value instead of type.
Instead of using [`typing.Literal`](https://docs.python.org/3/library/typing.html#typing.Literal), you can enclose literal values in `{...}` in docstrings.

| Docstring type | Python type annotation |
|----------------|------------------------|
| `{1, 2, 3}`    | `Literal[1, 2, 3]`     |
| `{1, 2, 3}`    | `Literal[1, 2, 3]`     |

> [!TIP]
> Enclosing a single value `{X}` is currently allowed but discouraged.
> Instead consider the more explicit `Literal[X]`.


## reStructuredText role

Since docstrings are also used to generate documentation with Sphinx, you may want to use [restructuredText roles](https://docutils.sourceforge.io/docs/ref/rst/roles.html) in your type annotations.
Docstub allows for this anywhere where a qualified name can be used.

| Docstring type       | Python type annotation |
|----------------------|------------------------|
| `` `X` ``            | `X`                    |
| ``:ref:`X` ``        | `X`                    |
| ``:class:`Y.X` ``    | `Y.X`                  |
| ``:py:class:`Y.X` `` | `Y.X`                  |

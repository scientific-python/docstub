# Glossary

This section defines central terms used in this documentation.

:::{glossary}
:sorted:

doctype
    A type description of a type in a docstring, such as of a parameter, return value, or attribute.
    Any {term}`annotation expression` is valid as a doctype, but doctypes support an [extended syntax](typing_syntax.md) with natural language variants.

type name
    The name of a single (atomic) type.
    A type name can include a {term}`type prefix`.
    An {term}`annotation expression` can contain multiple type names.
    For example, the annotation expression `collections.abc.Iterable[int or float]` consists of the three names `collections.abc.Iterable`, `int` and `float`.

type prefix
    A dot-delimited prefix that is part of a {term}`type name`.
    The prefix can describe the full path of a type or consist of an alias.
    For example, `collections.abc.Iterable` has the type prefix `collections.abc`.
    `np.int` has the prefix `np` which may be an alias for `numpy`.
    [Type prefixes can be defined in the configuration](configuration.md#type_prefixes) or are inferred by docstub from import statements it can see.
:::
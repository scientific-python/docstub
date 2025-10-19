# docstub documentation

:::{admonition} In early development!
:class: tip

Expect bugs, missing features, and incomplete documentation.
Docstub is still evaluating which features it needs to support as the community gives feedback.
Several features are experimental and included to make adoption of docstub easier.
Long-term, some of these might be discouraged or removed as docstub matures.
:::

docstub is a command-line tool to generate [Python stub files](https://typing.python.org/en/latest/guides/writing_stubs.html) from type descriptions found in [numpydoc](https://numpydoc.readthedocs.io)-style docstrings.

Many packages in the scientific Python ecosystem already describe expected parameter and return types in their docstrings.
Docstub aims to take advantage of these and help with the adoption of type annotations.
It does so by supporting widely used readable conventions such as `array of dtype` or `iterable of int(s)` which it translates into valid type annotations.


:::{toctree}
:caption: User guides
:maxdepth: 1
:hidden:

introduction
:::

:::{toctree}
:caption: Reference
:maxdepth: 1
:hidden:

command_line
configuration
typing_syntax
glossary
release_notes/index
:::

# docstub documentation

:::{admonition} In early development!
:class: important

Docstub is not feature-complete or thoroughly tested yet.
Its behavior, configuration or command line interface may change significantly between releases.
:::

docstub is a command-line tool to generate [Python stub files](https://typing.python.org/en/latest/spec/distributing.html#stub-files).
It extracts necessary type information from [NumPyDoc style](https://numpydoc.readthedocs.io) docstrings.

Many packages in the scientific Python ecosystem already describe expected parameter and return types in their docstrings.
Docstub aims to take advantage of these and help with the adoption of type annotations.
It does so by supporting widely used readable conventions such as `array of dtype` or `iterable of int(s)` which are translated into valid type annotations.

---

:::{toctree}
:caption: Guides
:maxdepth: 1

installation
introduction
:::

:::{toctree}
:caption: Reference
:maxdepth: 1

command_line
configuration
typing_syntax
glossary
release_notes/index
:::

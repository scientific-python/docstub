# docstub

> [!NOTE]
> **In early development!**
> Docstub is not feature-complete or thoroughly tested yet.
> Its behavior, configuration or command line interface may change significantly between releases.

docstub is a command-line tool to generate [Python stub files](https://typing.python.org/en/latest/guides/writing_stubs.html).
It extracts necessary type information from [NumPyDoc style](https://numpydoc.readthedocs.io) docstrings.

Many packages in the scientific Python ecosystem already describe expected parameter and return types in their docstrings.
Docstub aims to take advantage of these and help with the adoption of type annotations.
It does so by supporting widely used readable conventions such as `array of dtype` or `iterable of int(s)` which are translated into valid type annotations.


## Getting started & quick links

- [Documentation](https://docstub.readthedocs.io/) (see also [docs/](docs/))

Specific guides:

- [Installation (stable)](https://docstub.readthedocs.io/stable/installation.html)
- [Introduction (stable)](https://docstub.readthedocs.io/stable/introduction.html)
- [Contributing (latest)](https://docstub.readthedocs.io/latest/development/contributing.html)

Our [release notes (latest)](https://docstub.readthedocs.io/latest/release_notes/index.html) are in [docs/release_notes/](docs/release_notes).

Our project follows [Scientific Python's Code of Conduct](https://scientific-python.org/code_of_conduct/).


## Acknowledgements

Thanks to [docs2stubs](https://github.com/gramster/docs2stubs) by which this
project was heavily inspired and influenced.

And thanks to CZI for supporting this work with an [EOSS grant](https://chanzuckerberg.com/eoss/proposals/from-library-to-protocol-scikit-image-as-an-api-reference/).

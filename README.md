# docstub

> [!NOTE]
> In early development!
> Expect to encounter bugs, missing features, and fatal errors.

docstub is a command-line tool to generate [Python](https://www.python.org) stub files (i.e., PYI files) from type descriptions found in [numpydoc](https://numpydoc.readthedocs.io)-style docstrings.

Many packages in the scientific Python ecosystem already describe expected parameter and return types in their docstrings.
Docstub aims to take advantage of these and help with the adoption of type annotations.
It does so by supporting widely used readable conventions such as `array of dtype` or `iterable of int` which it translates into valid type annotations.


## Installation & getting started

Please refer to the [user guide](doc/user_guide.md) to get started with docstub.


## Contributing

The best way you can help and contribute right now is by trying docstub out!
Feedback to what features might still be missing or where it breaks for you would be greatly appreciated.
Pointers to where the documentation is confusing and unclear.

Since docstub is still in early development there isn't an official contribution guide yet.
Docstubs features and API is still being heavily extended and the internal structure is still somewhat in flux.
That said, if that only entices you, feel free to open a PR.
But please do check in with an issue before you do so.

Our project follows the [Scientific Python's Code of Conduct](https://scientific-python.org/code_of_conduct/).


## Acknowledgements

Thanks to [docs2stubs](https://github.com/gramster/docs2stubs) by which this
project was heavily inspired and influenced.

And thanks to CZI for supporting this work with an [EOSS grant](https://chanzuckerberg.com/eoss/proposals/from-library-to-protocol-scikit-image-as-an-api-reference/).

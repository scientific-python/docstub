# docstub

> [!NOTE]
> **In early development!**
> Expect bugs, missing features, and incomplete documentation.
> Docstub is still evaluating which features it needs to support as the community gives feedback.
> Several features are experimental and included to make adoption of docstub easier.
> Long-term, some of these might be discouraged or removed as docstub matures.

docstub is a command-line tool to generate [Python stub files](https://typing.python.org/en/latest/guides/writing_stubs.html) (i.e., PYI files) from type descriptions found in [numpydoc](https://numpydoc.readthedocs.io)-style docstrings.

Many packages in the scientific Python ecosystem already describe expected parameter and return types in their docstrings.
Docstub aims to take advantage of these and help with the adoption of type annotations.
It does so by supporting widely used readable conventions such as `array of dtype` or `iterable of int(s)` which it translates into valid type annotations.


## Installation & getting started

Please refer to the [user guide](https://github.com/scientific-python/docstub/blob/main/docs/user_guide.md) to get started with docstub.


## Contributing

The best way you can help and contribute right now is by trying docstub out!
Feedback to what features might still be missing or where it breaks for you would be greatly appreciated.
As well as pointers to where the documentation is confusing and unclear.
Feel welcome to [open an issue](https://github.com/scientific-python/docstub/issues/new/choose)! 🚀

Since docstub is still in early development there isn't an official contribution guide yet.
Features and API are still being heavily extended and the internal structure is still somewhat in flux.
The development is, in part, motivated by an effort to add type annotations to the [scikit-image project](https://scikit-image.org).
This may inform some short-term priorities and the roadmap.

That said, docstub is a project for the community and welcomes contributions in any form!
Please do check in with an issue if you are interested in working on something.

Our project follows the [Scientific Python's Code of Conduct](https://scientific-python.org/code_of_conduct/).


## Acknowledgements

Thanks to [docs2stubs](https://github.com/gramster/docs2stubs) by which this
project was heavily inspired and influenced.

And thanks to CZI for supporting this work with an [EOSS grant](https://chanzuckerberg.com/eoss/proposals/from-library-to-protocol-scikit-image-as-an-api-reference/).

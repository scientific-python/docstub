# Command line reference

## Command `docstub`

<!--- The following block is checked by the test suite --->
<!--- begin cli-docstub --->

```plain
Usage: docstub [OPTIONS] COMMAND [ARGS]...

  Generate Python stub files from docstrings.

Options:
  --version   Show the version and exit.
  -h, --help  Show this message and exit.

Commands:
  run  Generate Python stub files.
```

<!--- end cli-docstub --->


## Command `docstub run`

<!--- The following block is checked by the test suite --->
<!--- begin cli-docstub-run --->

```plain
Usage: docstub run [OPTIONS] PACKAGE_PATH

  Generate Python stub files.

  Given a `PACKAGE_PATH` to a Python package, generate stub files for it. Type
  descriptions in docstrings will be used to fill in missing inline type
  annotations or to override them.

Options:
  -o, --out-dir PATH  Set output directory explicitly. Stubs will be directly
                      written into that directory while preserving the
                      directory structure under `PACKAGE_PATH`. Otherwise,
                      stubs are generated inplace.
  --config PATH       Set one or more configuration file(s) explicitly.
                      Otherwise, it will look for a `pyproject.toml` or
                      `docstub.toml` in the current directory.
  --group-errors      Group identical errors together and list where they
                      occurred. Will delay showing errors until all files have
                      been processed. Otherwise, simply report errors as the
                      occur.
  --allow-errors INT  Allow this many or fewer errors. If docstub reports
                      more, exit with error code '1'. This is useful to adopt
                      docstub gradually.  [default: 0; x>=0]
  -v, --verbose       Print more details (repeatable).
  -h, --help          Show this message and exit.
```

<!--- end cli-docstub-run --->

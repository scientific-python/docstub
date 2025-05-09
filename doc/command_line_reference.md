# Command line reference

Running
```
docstub --help
```
will print

<!--- The following block is checked by the test suite --->
<!--- begin command-line-help --->

```plain
Usage: docstub [OPTIONS] PACKAGE_PATH

  Generate Python stub files with type annotations from docstrings.

  Given a path `PACKAGE_PATH` to a Python package, generate stub files for it.
  Type descriptions in docstrings will be used to fill in missing inline type
  annotations or to override them.

Options:
  --version           Show the version and exit.
  -o, --out-dir PATH  Set output directory explicitly. Otherwise, stubs are
                      generated inplace.
  --config PATH       Set configuration file explicitly.
  --group-errors      Group identical errors together and list where they
                      occured. Will delay showing errors until all files have
                      been processed. Otherwise, simply report errors as the
                      occur.
  --allow-errors INT  Allow this many or fewer errors. If docstub reports
                      more, exit with error code '1'.  [default: 0; x>=0]
  -v, --verbose       Print more details (repeatable).
  -h, --help          Show this message and exit.
```

<!--- end command-line-help --->

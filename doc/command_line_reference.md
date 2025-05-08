# Command line reference

Running
```
docstub --help
```
will print

<!--- The following block is checked by the test suite --->
<!--- begin command-line-help --->

```plain
Usage: docstub [OPTIONS] ROOT_PATH

  Generate Python stub files from docstrings.

Options:
  --version                Show the version and exit.
  -o, --out-dir DIRECTORY  Set output directory explicitly.
  --config FILE            Set configuration file explicitly.
  --group-errors           Group errors by type and content. Will delay
                           showing errors until all files have been processed.
  -v, --verbose            Log more details.
  -h, --help               Show this message and exit.
```

<!--- end command-line-help --->

# Command line

The reference for docstub's command line interface.
It uses [Click](https://click.palletsprojects.com/en/stable/), so [shell completion](https://click.palletsprojects.com/en/stable/shell-completion/) can be enabled.

Colored command line output can be disabled by [setting the environment variable `NO_COLOR=1`](https://no-color.org).


## `docstub`

<!--- The following block is checked by the test suite --->
<!--- begin cli-docstub --->

```none
Usage: docstub [OPTIONS] COMMAND [ARGS]...

  Generate Python stub files from docstrings.

Options:
      --version
          Show the version and exit.
  -h, --help
          Show this message and exit.

Commands:
  clean  Clean the cache.
  run    Generate Python stub files.
```

<!--- end cli-docstub --->


## `docstub run`

<!--- The following block is checked by the test suite --->
<!--- begin cli-docstub-run --->

```none
Usage: docstub run [OPTIONS] PACKAGE_PATH

  Generate Python stub files.

  Given a PACKAGE_PATH to a Python package, generate stub files for it. Type
  descriptions in docstrings will be used to fill in missing inline type
  annotations or to override them.

Options:
  -o, --out-dir PATH
          Set output directory explicitly. Stubs will be directly written into
          that directory while preserving the directory structure under
          PACKAGE_PATH. Otherwise, stubs are generated inplace.
      --ignore GLOB
          Ignore files matching this glob-style pattern. Can be used multiple
          times.
  -g, --group-errors
          Group identical errors together and list where they occurred. Will
          delay showing errors until all files have been processed. Otherwise,
          simply report errors as the occur.
      --allow-errors INT
          Allow this many or fewer errors. If docstub reports more, exit with
          error code 1. This is useful to adopt docstub gradually.   [default:
          0; x>=0]
  -W, --fail-on-warning
          Return non-zero exit code when a warning is raised. Will add to
          --allow-errors.
      --workers INT
          Experimental: Process files in parallel with the desired number of
          workers. By default, no multiprocessing is used.  [default: 1]
      --no-cache
          Ignore pre-existing cache and don't create a new one.
      --config PATH
          Set one or more configuration file(s) explicitly. Otherwise, it will
          look for a `pyproject.toml` or `docstub.toml` in the current
          directory.
  -v, --verbose
          Print more details. Use once to show information messages. Use -vv to
          print debug messages.
  -q, --quiet
          Print less details. Use once to hide warnings. Use -qq to completely
          silence output.
  -h, --help
          Show this message and exit.
```

<!--- end cli-docstub-run --->


## `docstub clean`

<!--- The following block is checked by the test suite --->
<!--- begin cli-docstub-clean --->

```none
Usage: docstub clean [OPTIONS]

  Clean the cache.

  Looks for a cache directory relative to the current working directory. If
  one exists, remove it.

Options:
  -v, --verbose
          Print more details. Use once to show information messages. Use -vv to
          print debug messages.
  -q, --quiet
          Print less details. Use once to hide warnings. Use -qq to completely
          silence output.
  -h, --help
          Show this message and exit.
```

<!--- end cli-docstub-clean --->

"""Command line interface of docstub.

The imports of this file should be structured such, that displaying help text
for the command line is as fast as possible. As such optional imports that may
not be used all the time should be delegated to the function scope.
"""

import logging
import sys

import click

from ._cli_help import HelpFormatter
from ._version import __version__

logger: logging.Logger = logging.getLogger(__name__)


# Overwrite click's default formatter class (stubtest balks at this)
# docstub: off
click.Context.formatter_class = HelpFormatter


@click.group()
# docstub: on
@click.version_option(__version__)
@click.help_option("-h", "--help")
def cli():
    """Generate Python stub files from docstrings."""


def _calc_verbosity(*, verbose, quiet):
    """Calculate the verbosity from the "--verbose" or "--quiet" flags.

    Parameters
    ----------
    verbose : {0, 1, 3}
    quiet : {0, 1, 2}

    Returns
    -------
    verbosity : {-2, -1, 0, 1, 2, 3}
    """
    if verbose and quiet:
        raise click.UsageError(
            "Options '-v/--verbose' and '-q/--quiet' cannot be used together"
        )
    verbose -= quiet
    verbose = min(3, max(-2, verbose))  # Limit to range [-2, 3]
    return verbose


def _add_verbosity_options(func):
    """Add verbose and quiet command line options.

    Parameters
    ----------
    func : Callable

    Returns
    -------
    decorated : Callable
    """
    func = click.option(
        "-q",
        "--quiet",
        count=True,
        help="Print less details. Use once to hide warnings. "
        "Use -qq to completely silence output.",
    )(func)
    func = click.option(
        "-v",
        "--verbose",
        count=True,
        help="Print more details. Use once to show information messages. "
        "Use -vv to print debug messages.",
    )(func)
    return func


# Preserve click.command below to keep type checker happy
# docstub: off
@cli.command()
# docstub: on
@click.argument("root_path", type=click.Path(exists=True), metavar="PACKAGE_PATH")
@click.option(
    "-o",
    "--out-dir",
    type=click.Path(file_okay=False),
    metavar="PATH",
    help="Set output directory explicitly. "
    "Stubs will be directly written into that directory while preserving the directory "
    "structure under PACKAGE_PATH. "
    "Otherwise, stubs are generated inplace.",
)
@click.option(
    "--ignore",
    type=str,
    multiple=True,
    metavar="GLOB",
    help="Ignore files matching this glob-style pattern. Can be used multiple times.",
)
@click.option(
    "-g",
    "--group-errors",
    is_flag=True,
    help="Group identical errors together and list where they occurred. "
    "Will delay showing errors until all files have been processed. "
    "Otherwise, simply report errors as the occur.",
)
@click.option(
    "--allow-errors",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    metavar="INT",
    help="Allow this many or fewer errors. "
    "If docstub reports more, exit with error code 1. "
    "This is useful to adopt docstub gradually. ",
)
@click.option(
    "-W",
    "--fail-on-warning",
    is_flag=True,
    help="Return non-zero exit code when a warning is raised. "
    "Will add to --allow-errors.",
)
@click.option(
    "--workers",
    "desired_worker_count",
    type=int,
    default=1,
    metavar="INT",
    help="Experimental: Process files in parallel with the desired number of workers. "
    "By default, no multiprocessing is used.",
    show_default=True,
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Ignore pre-existing cache and don't create a new one.",
)
@click.option(
    "--config",
    "config_paths",
    type=click.Path(exists=True, dir_okay=False),
    metavar="PATH",
    multiple=True,
    help="Set one or more configuration file(s) explicitly. "
    "Otherwise, it will look for a `pyproject.toml` or `docstub.toml` in the "
    "current directory.",
)
@_add_verbosity_options
@click.help_option("-h", "--help")
def run(
    *,
    root_path,
    out_dir,
    config_paths,
    ignore,
    group_errors,
    allow_errors,
    fail_on_warning,
    desired_worker_count,
    no_cache,
    verbose,
    quiet,
):
    """Generate Python stub files.

    Given a PACKAGE_PATH to a Python package, generate stub files for it.
    Type descriptions in docstrings will be used to fill in missing inline type
    annotations or to override them.
    \f

    Parameters
    ----------
    root_path : Path
    out_dir : Path
    config_paths : Sequence[Path]
    ignore : Sequence[str]
    group_errors : bool
    allow_errors : int
    fail_on_warning : bool
    desired_worker_count : int
    no_cache : bool
    verbose : int
    quiet : int
    """
    from ._app_generate_stubs import generate_stubs

    verbosity = _calc_verbosity(verbose=verbose, quiet=quiet)
    exit_code = generate_stubs(
        root_path=root_path,
        out_dir=out_dir,
        config_paths=config_paths,
        ignore=ignore,
        group_errors=group_errors,
        allow_errors=allow_errors,
        fail_on_warning=fail_on_warning,
        desired_worker_count=desired_worker_count,
        no_cache=no_cache,
        verbosity=verbosity,
    )
    sys.exit(exit_code)


# docstub: off
@cli.command()
# docstub: on
@_add_verbosity_options
@click.help_option("-h", "--help")
def clean(verbose, quiet):
    """Clean the cache.

    Looks for a cache directory relative to the current working directory.
    If one exists, remove it.
    \f

    Parameters
    ----------
    verbose : int
    quiet : int
    """
    import shutil

    from . import _app_generate_stubs as app
    from . import _cache

    verbosity = _calc_verbosity(verbose=verbose, quiet=quiet)
    app.setup_logging(verbosity=verbosity, group_errors=False)

    path = app.cache_dir_in_cwd()
    if path.exists():
        try:
            _cache.validate_cache(path)
        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "'%s' might not be a valid cache or might be corrupted. Not "
                "removing it out of caution. Manually remove it after checking "
                "if it is safe to do so.\n\nDetails: %s",
                path,
                "\n".join(e.args),
            )
            sys.exit(1)
        else:
            shutil.rmtree(app.cache_dir_in_cwd())
            logger.info("Cleaned %s", path)
    else:
        logger.info("No cache to clean")

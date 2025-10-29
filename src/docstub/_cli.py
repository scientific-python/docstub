import logging
import shutil
import sys
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import click

from ._analysis import (
    PyImport,
    TypeCollector,
    TypeMatcher,
    common_known_types,
)
from ._cache import CACHE_DIR_NAME, FileCache, validate_cache
from ._config import Config
from ._path_utils import (
    STUB_HEADER_COMMENT,
    find_package_root,
    walk_source_and_targets,
    walk_source_package,
)
from ._report import setup_logging
from ._stubs import Py2StubTransformer, try_format_stub
from ._version import __version__

logger: logging.Logger = logging.getLogger(__name__)


def _cache_dir_in_cwd():
    """Return cache directory for and in current working directory.

    Returns
    -------
    cache_dir : Path
    """
    return Path.cwd() / CACHE_DIR_NAME


def _load_configuration(config_paths=None):
    """Load and merge configuration from CWD and optional files.

    Parameters
    ----------
    config_paths : list[Path]

    Returns
    -------
    config : ~.Config
    """
    config = Config.from_toml(Config.TEMPLATE_PATH)
    numpy_config = Config.from_toml(Config.NUMPY_PATH)
    config = config.merge(numpy_config)

    if config_paths:
        for path in config_paths:
            logger.info("Using %s", path)
            add_config = Config.from_toml(path)
            config = config.merge(add_config)

    else:
        pyproject_toml = Path.cwd() / "pyproject.toml"
        if pyproject_toml.is_file():
            logger.info("Using %s", pyproject_toml)
            add_config = Config.from_toml(pyproject_toml)
            config = config.merge(add_config)

        docstub_toml = Path.cwd() / "docstub.toml"
        if docstub_toml.is_file():
            logger.info("Using %s", docstub_toml)
            add_config = Config.from_toml(docstub_toml)
            config = config.merge(add_config)

    return config


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


def _collect_type_info(root_path, *, ignore=(), cache=False):
    """Collect types.

    Parameters
    ----------
    root_path : Path
    ignore : Sequence[str], optional
        Don't yield files matching these glob-like patterns. The pattern is
        interpreted relative to the root of the Python package unless it starts
        with "/". See :ref:`glob.translate(..., recursive=True, include_hidden=True)`
        for more details on the precise implementation.
    cache : bool, optional
        Cache collected types.

    Returns
    -------
    types : dict[str, PyImport]
    type_prefixes : dict[str, PyImport]
    """
    types = common_known_types()

    if cache:
        collect = FileCache(
            func=TypeCollector.collect,
            serializer=TypeCollector.ImportSerializer(),
            cache_dir=_cache_dir_in_cwd(),
        )
    else:
        collect = TypeCollector.collect

    collected_types = {}
    collected_type_prefixes = {}
    for source_path in walk_source_package(root_path, ignore=ignore):
        if cache:
            module = source_path.relative_to(root_path.parent)
            collect.sub_dir = f"{__version__}/{module}"

        types_in_file, prefixes_in_file = collect(source_path)
        collected_types.update(types_in_file)
        collected_type_prefixes.update(prefixes_in_file)

        logger.info(
            "Collected%s types in %s",
            " cached" if cache and collect.cached_last_call else "",
            source_path,
        )
        logger.debug(
            "%i types, %i type prefixes in %s",
            len(types_in_file),
            len(prefixes_in_file),
            source_path,
        )

    logger.debug("Collected %i types", len(collected_types))
    logger.debug("Collected %i type prefixes", len(collected_type_prefixes))
    types |= collected_types
    return types, collected_type_prefixes


def _format_unknown_names(names):
    """Format unknown type names as a list for printing.

    Parameters
    ----------
    names : Iterable[str]

    Returns
    -------
    formatted : str
        A multiline string.

    Examples
    --------
    >>> names = ["path-like", "values", "arrays", "values"] + ["string"] * 11
    >>> print(_format_unknown_names(names))
    11  string
     2  values
     1  arrays
     1  path-like
    """
    counter = Counter(names)
    sorted_alphabetical = sorted(counter.items(), key=lambda x: x[0])
    sorted_by_frequency = sorted(sorted_alphabetical, key=lambda x: x[1], reverse=True)

    lines = []
    pad_left = len(str(sorted_by_frequency[0][1]))
    for item, count in sorted_by_frequency:
        count_fmt = f"{count}".rjust(pad_left)
        lines.append(f"{count_fmt}  {item}")
    formatted = "\n".join(lines)
    return formatted


@contextmanager
def log_execution_time():
    start = time.time()
    try:
        yield
    except KeyboardInterrupt:
        logger.critical("Interrupt!")
    finally:
        stop = time.time()
        total_seconds = stop - start

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        formated_duration = f"{seconds:.3f} s"
        if minutes:
            formated_duration = f"{minutes} min {formated_duration}"
        if hours:
            formated_duration = f"{hours} h {formated_duration}"

        logger.info("Finished in %s", formated_duration)


# docstub: off
@click.group()
# docstub: on
@click.version_option(__version__)
@click.help_option("-h", "--help")
def cli():
    """Generate Python stub files from docstrings."""


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
    "structure under `PACKAGE_PATH`. "
    "Otherwise, stubs are generated inplace.",
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
@click.option(
    "--ignore",
    type=str,
    multiple=True,
    metavar="GLOB",
    help="Ignore files matching this glob-style pattern. Can be used multiple times.",
)
@click.option(
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
    "If docstub reports more, exit with error code '1'. "
    "This is useful to adopt docstub gradually. ",
)
@click.option(
    "-W",
    "--fail-on-warning",
    is_flag=True,
    help="Return non-zero exit code when a warning is raised. "
    "Will add to '--allow-errors'.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Ignore pre-existing cache and don't create a new one.",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Print more details. Use once to show information messages. "
    "Use '-vv' to print debug messages.",
)
@click.option(
    "-q",
    "--quiet",
    count=True,
    help="Print less details. Use once to hide warnings. "
    "Use '-qq' to completely silence output.",
)
@click.help_option("-h", "--help")
@log_execution_time()
def run(
    *,
    root_path,
    out_dir,
    config_paths,
    ignore,
    group_errors,
    allow_errors,
    fail_on_warning,
    no_cache,
    verbose,
    quiet,
):
    """Generate Python stub files.

    Given a `PACKAGE_PATH` to a Python package, generate stub files for it.
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
    no_cache : bool
    verbose : int
    quiet : int
    """

    # Setup -------------------------------------------------------------------

    verbosity = _calc_verbosity(verbose=verbose, quiet=quiet)
    error_handler = setup_logging(verbosity=verbosity, group_errors=group_errors)

    root_path = Path(root_path)
    if root_path.is_file():
        logger.warning(
            "Running docstub on a single module. Relative imports "
            "or type references pointing outside this module won't work."
        )
    elif find_package_root(root_path) != root_path.resolve():
        logger.warning(
            "Running docstub only on a subpackage. Relative imports "
            "or type references pointing outside this subpackage won't work."
        )

    config = _load_configuration(config_paths)
    config = config.merge(Config(ignore_files=list(ignore)))

    types, type_prefixes = _collect_type_info(
        root_path, ignore=config.ignore_files, cache=not no_cache
    )

    # Add declared types from configuration
    types |= {
        type_name: PyImport(from_=module, import_=type_name)
        for type_name, module in config.types.items()
    }

    # Add declared type prefixes from configuration
    type_prefixes |= {
        prefix: (
            PyImport(import_=module, as_=prefix)
            if module != prefix
            else PyImport(import_=prefix)
        )
        for prefix, module in config.type_prefixes.items()
    }

    matcher = TypeMatcher(
        types=types, type_prefixes=type_prefixes, type_nicknames=config.type_nicknames
    )
    stub_transformer = Py2StubTransformer(matcher=matcher)

    if not out_dir:
        if root_path.is_file():
            out_dir = root_path.parent
        else:
            out_dir = root_path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stub generation ---------------------------------------------------------

    for source_path, stub_path in walk_source_and_targets(
        root_path, out_dir, ignore=config.ignore_files
    ):
        if source_path.suffix.lower() == ".pyi":
            logger.debug("Using existing stub file %s", source_path)
            with source_path.open() as fo:
                stub_content = fo.read()
        else:
            with source_path.open() as fo:
                py_content = fo.read()
            logger.debug("Transforming %s", source_path)
            try:
                stub_content = stub_transformer.python_to_stub(
                    py_content, module_path=source_path
                )
                stub_content = f"{STUB_HEADER_COMMENT}\n\n{stub_content}"
                stub_content = try_format_stub(stub_content)
            except Exception:
                logger.exception("Failed creating stub for %s", source_path)
                continue
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        with stub_path.open("w") as fo:
            logger.info("Wrote %s", stub_path)
            fo.write(stub_content)

    py_typed_out = out_dir / "py.typed"
    if not py_typed_out.exists():
        py_typed_out.touch()
        logger.info("Created %s", py_typed_out)

    # Reporting --------------------------------------------------------------

    if group_errors:
        error_handler.emit_grouped()
        assert error_handler.group_errors is True
        error_handler.group_errors = False

    # Report basic statistics
    successful_queries = matcher.successful_queries
    transformed_doctypes = stub_transformer.transformer.stats["transformed"]
    syntax_error_count = stub_transformer.transformer.stats["syntax_errors"]
    unknown_type_names = matcher.unknown_qualnames
    total_warnings = error_handler.warning_count
    total_errors = error_handler.error_count

    logger.info("Recognized type names: %i", successful_queries)
    logger.info("Transformed doctypes: %i", transformed_doctypes)
    if total_warnings:
        logger.warning("Warnings: %i", total_warnings)
    if syntax_error_count:
        logger.warning("Syntax errors: %i", syntax_error_count)
    if unknown_type_names:
        logger.warning(
            "Unknown type names: %i",
            len(unknown_type_names),
            extra={"details": _format_unknown_names(unknown_type_names)},
        )
    if total_errors:
        logger.error("Total errors: %i", total_errors)

    total_fails = total_errors
    if fail_on_warning:
        total_fails += total_warnings
    if allow_errors < total_fails:
        sys.exit(1)


# docstub: off
@cli.command()
# docstub: on
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Print more details. Use once to show information messages. "
    "Use '-vv' to print debug messages.",
)
@click.option(
    "-q",
    "--quiet",
    count=True,
    help="Print less details. Use once to hide warnings. "
    "Use '-qq' to completely silence output.",
)
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
    verbosity = _calc_verbosity(verbose=verbose, quiet=quiet)
    setup_logging(verbosity=verbosity, group_errors=False)

    path = _cache_dir_in_cwd()
    if path.exists():
        try:
            validate_cache(path)
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
            shutil.rmtree(_cache_dir_in_cwd())
            logger.info("Cleaned %s", path)
    else:
        logger.info("No cache to clean")

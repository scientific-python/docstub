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
    walk_source_and_targets,
    walk_source_package,
)
from ._stubs import Py2StubTransformer, try_format_stub
from ._utils import ErrorReporter, GroupedErrorReporter
from ._version import __version__

logger = logging.getLogger(__name__)


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
            logger.info("using %s", path)
            add_config = Config.from_toml(path)
            config = config.merge(add_config)

    else:
        pyproject_toml = Path.cwd() / "pyproject.toml"
        if pyproject_toml.is_file():
            logger.info("using %s", pyproject_toml)
            add_config = Config.from_toml(pyproject_toml)
            config = config.merge(add_config)

        docstub_toml = Path.cwd() / "docstub.toml"
        if docstub_toml.is_file():
            logger.info("using %s", docstub_toml)
            add_config = Config.from_toml(docstub_toml)
            config = config.merge(add_config)

    return config


def _setup_logging(*, verbose):
    _VERBOSITY_LEVEL = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    verbose = min(2, max(0, verbose))  # Limit to range [0, 2]

    format_ = "%(levelname)s: %(message)s"
    if verbose >= 2:
        format_ += " py_source=%(filename)s#L%(lineno)d::%(funcName)s"

    logging.basicConfig(
        level=_VERBOSITY_LEVEL[verbose],
        format=format_,
        stream=sys.stderr,
    )


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
    type_prefixes = {}

    if cache:
        collect = FileCache(
            func=TypeCollector.collect,
            serializer=TypeCollector.ImportSerializer(),
            cache_dir=_cache_dir_in_cwd(),
        )
    else:
        collect = TypeCollector.collect

    for source_path in walk_source_package(root_path, ignore=ignore):

        if cache:
            module = source_path.relative_to(root_path.parent)
            collect.sub_dir = f"{__version__}/{module}"

        types_in_file, prefixes_in_file = collect(source_path)
        types.update(types_in_file)
        type_prefixes.update(prefixes_in_file)

        logger.info(
            "collected types in %s%s",
            source_path,
            " (cached)" if cache and collect.cached_last_call else "",
        )

    return types, type_prefixes


@contextmanager
def report_execution_time():
    start = time.time()
    try:
        yield
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

        # FIXME A hack to ensure that closing message is printed last, instead
        #   it would be got to use the same mechanism for all output
        for handler in logger.handlers:
            handler.flush()

        click.echo()
        click.echo(f"Finished in {formated_duration}")


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
    "This is useful to adopt docstub gradually.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Ignore pre-existing cache and don't create a new one.",
)
@click.option("-v", "--verbose", count=True, help="Print more details (repeatable).")
@click.help_option("-h", "--help")
@report_execution_time()
def run(
    *,
    root_path,
    out_dir,
    config_paths,
    ignore,
    group_errors,
    allow_errors,
    no_cache,
    verbose,
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
    no_cache : bool
    verbose : int
    """

    # Setup -------------------------------------------------------------------

    _setup_logging(verbose=verbose)

    root_path = Path(root_path)
    if root_path.is_file():
        logger.warning(
            "Running docstub on a single file. Relative imports "
            "or type references outside this file won't work."
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

    reporter = GroupedErrorReporter() if group_errors else ErrorReporter()
    matcher = TypeMatcher(
        types=types, type_prefixes=type_prefixes, type_nicknames=config.type_nicknames
    )
    stub_transformer = Py2StubTransformer(matcher=matcher, reporter=reporter)

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
            logger.debug("using existing stub file %s", source_path)
            with source_path.open() as fo:
                stub_content = fo.read()
        else:
            with source_path.open() as fo:
                py_content = fo.read()
            logger.debug("creating stub from %s", source_path)
            try:
                stub_content = stub_transformer.python_to_stub(
                    py_content, module_path=source_path
                )
                stub_content = f"{STUB_HEADER_COMMENT}\n\n{stub_content}"
                stub_content = try_format_stub(stub_content)
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as e:
                logger.exception("failed creating stub for %s:\n\n%s", source_path, e)
                continue
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        with stub_path.open("w") as fo:
            logger.info("wrote %s", stub_path)
            fo.write(stub_content)

    # Reporting --------------------------------------------------------------

    if group_errors:
        reporter.print_grouped()

    # Report basic statistics
    successful_queries = matcher.successful_queries
    click.secho(f"{successful_queries} matched annotations", fg="green")

    syntax_error_count = stub_transformer.transformer.stats["syntax_errors"]
    if syntax_error_count:
        click.secho(f"{syntax_error_count} syntax errors", fg="red")

    unknown_qualnames = matcher.unknown_qualnames
    if unknown_qualnames:
        click.secho(f"{len(unknown_qualnames)} unknown type names", fg="red")
        counter = Counter(unknown_qualnames)
        sorted_item_counts = sorted(counter.items(), key=lambda x: x[1], reverse=True)
        for item, count in sorted_item_counts:
            click.echo(f"  {item} (x{count})")

    total_errors = len(unknown_qualnames) + syntax_error_count
    total_msg = f"{total_errors} total errors"
    if allow_errors:
        total_msg = f"{total_msg} (allowed {allow_errors})"
    click.secho(total_msg, bold=True)

    if allow_errors < total_errors:
        logger.debug("number of allowed errors %i was exceeded")
        sys.exit(1)


# docstub: off
@cli.command()
# docstub: on
@click.option("-v", "--verbose", count=True, help="Print more details (repeatable).")
@click.help_option("-h", "--help")
def clean(verbose):
    """Clean the cache.

    Looks for a cache directory relative to the current working directory.
    If one exists, remove it.
    \f

    Parameters
    ----------
    verbose : int
    """
    _setup_logging(verbose=verbose)

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
            logger.info("cleaned %s", path)
    else:
        logger.info("no cache to clean")

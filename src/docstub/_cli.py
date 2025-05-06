import logging
import sys
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import click

from ._analysis import (
    KnownImport,
    TypeCollector,
    TypesDatabase,
    common_known_imports,
)
from ._cache import FileCache
from ._config import Config
from ._stubs import (
    Py2StubTransformer,
    try_format_stub,
    walk_source,
    walk_source_and_targets,
)
from ._utils import ErrorReporter, GroupedErrorReporter
from ._version import __version__

logger = logging.getLogger(__name__)


STUB_HEADER_COMMENT = "# File generated with docstub"


def _load_configuration(config_path=None):
    """Load and merge configuration from CWD and optional files.

    Parameters
    ----------
    config_path : Path

    Returns
    -------
    config : ~.Config
    """
    config = Config.from_toml(Config.DEFAULT_CONFIG_PATH)

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

    if config_path:
        logger.info("using %s", config_path)
        add_config = Config.from_toml(config_path)
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


def _build_import_map(config, source_dir):
    """Build a map of known imports.

    Parameters
    ----------
    config : ~.Config
    source_dir : Path

    Returns
    -------
    imports : dict[str, ~.KnownImport]
    """
    known_imports = common_known_imports()

    collect_cached_types = FileCache(
        func=TypeCollector.collect,
        serializer=TypeCollector.ImportSerializer(),
        cache_dir=Path.cwd() / ".docstub_cache",
        name=f"{__version__}/collected_types",
    )
    for source_path in walk_source(source_dir):
        logger.info("collecting types in %s", source_path)
        known_imports_in_source = collect_cached_types(source_path)
        known_imports.update(known_imports_in_source)

    known_imports.update(KnownImport.many_from_config(config.known_imports))

    return known_imports


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

        click.echo()
        click.echo(f"Finished in {formated_duration}")


@click.command()
@click.version_option(__version__)
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option(
    "-o",
    "--out-dir",
    type=click.Path(file_okay=False),
    help="Set output directory explicitly.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    help="Set configuration file explicitly.",
)
@click.option(
    "--group-errors",
    is_flag=True,
    help="Group errors by type and content. "
    "Will delay showing errors until all files have been processed.",
)
@click.option("-v", "--verbose", count=True, help="Log more details.")
@click.help_option("-h", "--help")
@report_execution_time()
def main(source_dir, out_dir, config_path, group_errors, verbose):
    """Generate Python stub files from docstrings.
    \f

    Parameters
    ----------
    source_dir : Path
    out_dir : Path
    config_path : Path
    verbose : str
    """

    # Setup -------------------------------------------------------------------

    _setup_logging(verbose=verbose)

    source_dir = Path(source_dir)
    config = _load_configuration(config_path)
    known_imports = _build_import_map(config, source_dir)

    reporter = GroupedErrorReporter() if group_errors else ErrorReporter()
    types_db = TypesDatabase(
        source_pkgs=[source_dir.parent.resolve()], known_imports=known_imports
    )
    stub_transformer = Py2StubTransformer(
        types_db=types_db, replace_doctypes=config.replace_doctypes, reporter=reporter
    )

    if not out_dir:
        out_dir = source_dir.parent / (source_dir.name + "-stubs")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stub generation ---------------------------------------------------------

    for source_path, stub_path in walk_source_and_targets(source_dir, out_dir):
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
    successful_queries = types_db.stats["successful_queries"]
    click.secho(f"{successful_queries} matched annotations", fg="green")

    syntax_error_count = stub_transformer.transformer.stats["syntax_errors"]
    if syntax_error_count:
        click.secho(f"{syntax_error_count} syntax errors", fg="red")

    unknown_doctypes = types_db.stats["unknown_doctypes"]
    if unknown_doctypes:
        click.secho(f"{len(unknown_doctypes)} unknown doctypes:", fg="red")
        counter = Counter(unknown_doctypes)
        for item, count in sorted(counter.items(), key=lambda x: x[1]):
            click.echo(f"  {item} (x{count})")

    if unknown_doctypes or syntax_error_count:
        sys.exit(1)

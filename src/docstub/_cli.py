import logging
import sys
from pathlib import Path

import click

from ._analysis import (
    KnownImport,
    KnownImportCollector,
    StaticInspector,
    common_known_imports,
)
from ._config import Config
from ._stubs import Py2StubTransformer, walk_source, walk_source_and_targets
from ._version import __version__

logger = logging.getLogger(__name__)


def _load_configuration(config_path=None):
    """Load and merge configuration from CWD and optional files.

    Parameters
    ----------
    config_path : Path

    Returns
    -------
    config : dict[str, Any]
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


@click.command()
@click.version_option(__version__)
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option(
    "-o",
    "--out-dir",
    type=click.Path(file_okay=False),
    help="Set explicit output directory.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    help="Set explicitly configuration file.",
)
@click.option("-v", "--verbose", count=True, help="Log more details.")
@click.help_option("-h", "--help")
def main(source_dir, out_dir, config_path, verbose):
    _setup_logging(verbose=verbose)

    source_dir = Path(source_dir)
    config = _load_configuration(config_path)

    # Build map of known imports
    known_imports = common_known_imports()
    for source_path in walk_source(source_dir):
        logger.info("collecting types in %s", source_path)
        known_imports_in_source = KnownImportCollector.collect(
            source_path, module_name=source_path.import_path
        )
        known_imports.update(known_imports_in_source)
    known_imports.update(KnownImport.many_from_config(config.known_imports))

    inspector = StaticInspector(
        source_pkgs=[source_dir.parent.resolve()], known_imports=known_imports
    )
    # and the stub transformer
    stub_transformer = Py2StubTransformer(
        inspector=inspector, replace_doctypes=config.replace_doctypes
    )

    if not out_dir:
        out_dir = source_dir.parent / (source_dir.name + "-stubs")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

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
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as e:
                logger.exception("failed creating stub for %s:\n\n%s", source_path, e)
                continue
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        with stub_path.open("w") as fo:
            logger.info("wrote %s", stub_path)
            fo.write(stub_content)

    # Report basic statistics
    successful_queries = inspector.stats["successful_queries"]
    click.secho(f"{successful_queries} matched annotations", fg="green")

    grammar_errors = stub_transformer.transformer.stats["grammar_errors"]
    if grammar_errors:
        click.secho(f"{grammar_errors} grammar violations", fg="red")

    unknown_doctypes = inspector.stats["unknown_doctypes"]
    if unknown_doctypes:
        click.secho(f"{len(unknown_doctypes)} unknown doctypes:", fg="red")
        click.echo("  " + "\n  ".join(set(unknown_doctypes)))

    if unknown_doctypes or grammar_errors:
        sys.exit(1)

import logging
import sys
from pathlib import Path

import click

from . import _config
from ._analysis import DocName, DocNameCollector, StaticInspector, common_docnames
from ._stubs import Py2StubTransformer, walk_source, walk_source_and_targets
from ._version import __version__

logger = logging.getLogger(__name__)


_VERBOSITY_LEVEL = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}


def _find_configuration(source_dir, config_path):
    """Find and load configuration from multiple possible sources.

    Parameters
    ----------
    source_dir : Path
    config_path : Path

    Returns
    -------
    config : dict[str, Any]
    """
    # Handle configuration
    config = _config.default_config()
    pyproject_toml = source_dir.parent / "pyproject.toml"
    docstub_toml = source_dir.parent / "docstub.toml"
    if pyproject_toml.is_file():
        logger.info("using %s", pyproject_toml)
        add_config = _config.load_config_file(pyproject_toml)
        config = _config.merge_config(config, add_config)
    if docstub_toml.is_file():
        logger.info("using %s", docstub_toml)
        add_config = _config.load_config_file(docstub_toml)
        config = _config.merge_config(config, add_config)
    if config_path:
        logger.info("using %s", config_path)
        add_config = _config.load_config_file(config_path)
        config = _config.merge_config(config, add_config)
    return config


@click.command()
@click.version_option(__version__)
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--out-dir", type=click.Path(file_okay=False))
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-v", "--verbose", count=True, help="Log more details")
@click.help_option("-h", "--help")
def main(source_dir, out_dir, config_path, verbose):
    verbose = min(2, max(0, verbose))  # Limit to range [0, 2]
    logging.basicConfig(
        level=_VERBOSITY_LEVEL[verbose],
        format="%(levelname)s: %(filename)s#L%(lineno)d::%(funcName)s: %(message)s",
        stream=sys.stderr,
    )

    source_dir = Path(source_dir)
    config = _find_configuration(source_dir, config_path)

    # Build docname map
    docnames = common_docnames()
    for source_path in walk_source(source_dir):
        logger.info("collecting types in %s", source_path)
        docnames_in_source = DocNameCollector.collect(
            source_path, module_name=source_path.import_path
        )
        docnames.update(docnames_in_source)
    docnames.update(DocName.many_from_config(config["docnames"]))

    inspector = StaticInspector(
        source_pkgs=[source_dir.parent.resolve()], docnames=docnames
    )
    # and the stub transformer
    stub_transformer = Py2StubTransformer(inspector=inspector)

    if not out_dir:
        out_dir = source_dir.parent
    out_dir = Path(out_dir) / (source_dir.name + "-stubs")
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
            except Exception as e:
                logger.exception("failed creating stub for %s:\n\n%s", source_path, e)
                continue
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        with stub_path.open("w") as fo:
            logger.info("wrote %s", stub_path)
            fo.write(stub_content)

import logging
import sys
from pathlib import Path

import click

from . import _config
from ._analysis import DocName, common_docnames
from ._stubs import Py2StubTransformer, walk_python_package
from ._version import __version__

logger = logging.getLogger(__name__)


_VERBOSITY_LEVEL = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}


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
        format="%(levelname)s: %(filename)s, line %(lineno)d, in %(funcName)s: %(message)s",
        stream=sys.stderr,
    )

    source_dir = Path(source_dir)

    # Handle configuration
    if config_path is None:
        config_path = source_dir.parent / "docstub.toml"
    else:
        config_path = Path(config_path)
    config = _config.default_config()
    if config_path.exists():
        _user_config = _config.load_config_file(config_path)
        config = _config.merge_config(config, _user_config)

    # Build docname map
    docnames = common_docnames()
    docnames.update(
        {
            name: DocName.from_cfg(docname=name, spec=spec)
            for name, spec in config["docnames"].items()
        }
    )
    # and the stub transformer
    stub_transformer = Py2StubTransformer(docnames=docnames)

    if not out_dir:
        out_dir = source_dir.parent
    out_dir = Path(out_dir) / (source_dir.name + "-stubs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for source_path, stub_path in walk_python_package(source_dir, out_dir):
        if source_path.suffix.lower() == ".pyi":
            logger.debug("using existing stub file %s", source_path)
            with source_path.open() as fo:
                stub_content = fo.read()
        else:
            with source_path.open() as fo:
                py_content = fo.read()
            logger.debug("creating stub from %s", source_path)
            try:
                stub_content = stub_transformer.python_to_stub(py_content)
            except Exception as e:
                logger.exception("failed creating stub for %s:\n\n%s", source_path, e)
                continue
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        with stub_path.open("w") as fo:
            logger.info("wrote %s", stub_path)
            fo.write(stub_content)

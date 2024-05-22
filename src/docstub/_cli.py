import logging
import sys
from functools import partial
from pathlib import Path

import click

from ._config import load_config
from ._docstrings import transform_docstring
from ._stubs import TreeTransformer, walk_python_package
from ._version import __version__
from ._static_analysis import KnownType, known_builtins


logger = logging.getLogger(__name__)


@click.command()
@click.version_option(__version__)
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--out-dir", type=click.Path(file_okay=False))
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-v", "--verbose", count=True, help="Log more details")
def main(source_dir, out_dir, config_path, verbose):
    logging.basicConfig(
        level=logging.DEBUG if verbose > 0 else logging.INFO,
        format="%(levelname)s: %(filename)s::%(funcName)s: %(message)s",
        stream=sys.stderr,
    )

    source_dir = Path(source_dir)

    if config_path is None:
        config_path = source_dir.parent / "docstub.toml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        config = load_config(config_path)
    else:
        raise ValueError("no config")

    replace_map = {
        name: replacement
        for name, replacement in config["replace_map"].items()
    }
    import_map = {name: KnownType(is_builtin=True) for name in known_builtins}
    import_map.update({
        name: KnownType.from_cfg(spec)
        for name, spec in config["import_map"].items()
    })
    stub_transformer = TreeTransformer(
        transform_docstring=partial(
            transform_docstring, replace_map=replace_map, import_map=import_map
        )
    )

    if not out_dir:
        out_dir = source_dir.parent
    out_dir = Path(out_dir) / (source_dir.name + "-stubs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for py_path, stub_path in walk_python_package(source_dir, out_dir):
        existing_stub = py_path.with_suffix(".pyi")
        if existing_stub.exists():
            logger.debug("using existing stub file %s", existing_stub)
            with existing_stub.open() as fo:
                stub_content = fo.read()
        else:
            with py_path.open() as fo:
                py_content = fo.read()
            logger.debug("creating stub from %s", py_path)
            try:
                stub_content = stub_transformer.python_to_stub(py_content)
            except Exception as e:
                logger.error("failed creating stub for %s:\n\n%s", py_path, e)
                continue
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        with stub_path.open("w") as fo:
            logger.info("wrote %s", stub_path)
            fo.write(stub_content)

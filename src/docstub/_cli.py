import logging
from pathlib import Path
from functools import partial

import click

from ._version import __version__
from ._docstrings import DocTransform, transform_docstring
from ._stubs import TreeTransformer
from ._config import load_config


logger = logging.getLogger(__name__)


def _walk_python_package(root_dir, target_dir):
    """

    Parameters
    ----------
    root_dir : Path
    target_dir : Path

    Returns
    -------
    py_path : Path
    stub_path : Path
    """
    for root, dirs, files in root_dir.walk(top_down=True):
        for name in files:
            if not name.endswith(".py"):
                continue
            py_path = root / name
            stub_path = target_dir / py_path.relative_to(root_dir)
            yield py_path, stub_path


@click.command()
@click.version_option(__version__)
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--config", "config_path", type=click.Path(exists=True, dir_okay=False)
)
def main(source_dir, config_path):
    source_dir = Path(source_dir)
    target_dir = source_dir.parent / (source_dir.name + "-stubs")

    if config_path is None:
        config_path = source_dir.parent / "docstub.toml"

    if config_path.exists():
        config = load_config(config_path)
    else:
        raise ValueError("no config")

    doc_transforms = {
        rule: DocTransform.from_str(spec)
        for rule, spec in config["doc_transforms"].items()
    }
    stub_transformer = TreeTransformer(
        transform_docstring=partial(transform_docstring, doc_transforms=doc_transforms)
    )

    for py_path, stub_path in _walk_python_package(source_dir, target_dir):
        with py_path.open() as fo:
            py_content = fo.read()
        stub_content = stub_transformer.python_to_stub(py_content)
        with stub_path.open("w") as fo:
            logger.info("wrote %s", stub_path)
            fo.write(stub_content)

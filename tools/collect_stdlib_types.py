#!/usr/bin/python

"""Pre-collecting types in `_typeshed` and write to `src/docstub/`.

The script sources the `_typeshed` from the basedpyright package in the current
environment. It collects all non-private types and writes them to
`src/docstub/<TARGET_NAME>`.
"""

import argparse
import logging
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

import basedpyright

from docstub._analysis import StubTypeCollector
from docstub._stubs import try_format_stub

logger = logging.getLogger(__name__)


TARGET_MODULE_NAME = "_stdlib_types.py"


TEMPLATE = """# File generated with {script_name}

stdlib_types = {stdlib_types}
"""


def is_private_(qualname: str) -> bool:
    if qualname.startswith("_typeshed"):
        return False
    parts = qualname.split(".")
    return any(part.startswith("_") for part in parts)


def parse_command_line() -> dict:
    """Define and parse command line options."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--debug", action="store_true", help="show debugging information"
    )
    kwargs = vars(parser.parse_args())
    return kwargs


@contextmanager
def handle_exceptions():
    """Handle (un)expected exceptions in `main()`."""
    try:
        yield
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception:
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)


def main(**kwargs):
    typeshed_path = Path(basedpyright.__file__).parent / "dist/typeshed-fallback"
    assert typeshed_path.is_dir()

    docstub_path = (Path(__file__).parent / "../src/docstub").resolve()
    assert typeshed_path.is_dir()

    stdlib_types = set()
    dunder_all = set()
    stub_files = list((typeshed_path / "stdlib").glob("**/*.pyi"))
    for path in stub_files:
        types_in_path, dunder_all_in_path = StubTypeCollector.collect(path)
        logger.info("collected %i types in %s", len(types_in_path), path)
        stdlib_types |= types_in_path
        dunder_all |= dunder_all_in_path

    logger.info("formatting %i types", len(stdlib_types))
    stdlib_types = tuple(sorted(stdlib_types))
    dunder_all = tuple(sorted(dunder_all))

    content = TEMPLATE.format(
        stdlib_types=str(stdlib_types), script_name=Path(__file__).name
    )
    content = try_format_stub(content)

    out_path = docstub_path / TARGET_MODULE_NAME
    with out_path.open("w") as io:
        io.write(content)
    logger.info("wrote %s", out_path)


if __name__ == "__main__":
    with handle_exceptions():
        kwargs = parse_command_line()
        logging.basicConfig(
            stream=sys.stdout,
            level=logging.DEBUG if kwargs["debug"] else logging.INFO,
            format="%(filename)s: %(message)s",
        )
        main(**kwargs)

import argparse

from ._version import __version__


def parse_command_line(func):
    """Define and parse command line options.

    Has no effect if any keyword argument is passed to the underlying function.
    """
    parser = argparse.ArgumentParser(
        usage="Generate Python stub files from docstrings."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="print the version and exit",
    )

    def wrapped(**kwargs):
        if not kwargs:
            kwargs = vars(parser.parse_args())
        return func(**kwargs)

    return wrapped


@parse_command_line
def main():
    pass

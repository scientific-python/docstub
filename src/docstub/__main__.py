import logging
import sys

from ._cli import main

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(filename)s::%(funcName)s: %(message)s",
        stream=sys.stderr,
    )
    main()

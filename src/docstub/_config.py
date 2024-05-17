import logging
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


logger = logging.getLogger(__name__)


def load_config(path: Path) -> dict:
    """Return configuration options in local TOML file if they exist."""
    with path.open("rb") as fp:
        config = tomllib.load(fp)
    config = config.get("docstub", {})
    return config

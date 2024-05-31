import logging
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


logger = logging.getLogger(__name__)


DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.toml"


def load_config_file(path: Path) -> dict:
    """Return configuration options in local TOML file if they exist."""
    with open(path, "rb") as fp:
        config = tomllib.load(fp)
    config = config.get("tool", {}).get("docstub", {})
    return config


def default_config():
    config = load_config_file(DEFAULT_CONFIG_PATH)
    return config


def merge_config(*configurations):
    merged = {}
    merged["extended_grammar"] = "\n".join(
        cfg.get("extended_grammar", "") for cfg in configurations
    )
    merged["docnames"] = {}
    for cfg in configurations:
        docnames = cfg.get("docnames")
        if docnames and isinstance(docnames, dict):
            merged["docnames"].update(docnames)
    return merged

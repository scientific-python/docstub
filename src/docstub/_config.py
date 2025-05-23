import dataclasses
import logging
import tomllib
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    DEFAULT_CONFIG_PATH: ClassVar[Path] = Path(__file__).parent / "default_config.toml"

    types: dict[str, str] = dataclasses.field(default_factory=dict)
    type_prefixes: dict[str, str] = dataclasses.field(default_factory=dict)
    type_aliases: dict[str, str] = dataclasses.field(default_factory=dict)

    _source: tuple[Path, ...] = ()

    @classmethod
    def from_toml(cls, path):
        """Return configuration options in local TOML file if they exist.

        Parameters
        ----------
        path : Path or str

        Returns
        -------
        config : Self
        """
        path = Path(path)
        with open(path, "rb") as fp:
            raw = tomllib.load(fp)
        config = cls(**raw.get("tool", {}).get("docstub", {}), _source=(path,))
        logger.debug("created Config from %s", path)
        return config

    @classmethod
    def from_default(cls):
        """Create a configuration with default values.

        Returns
        -------
        config : Self
        """
        config = cls.from_toml(cls.DEFAULT_CONFIG_PATH)
        return config

    def merge(self, other):
        """Merge contents with other and return a copy_with Config instance.

        Parameters
        ----------
        other : Self

        Returns
        -------
        merged : Self
        """
        if not isinstance(other, type(self)):
            return NotImplemented
        new = Config(
            types=self.types | other.types,
            type_prefixes=self.type_prefixes | other.type_prefixes,
            type_aliases=self.type_aliases | other.type_aliases,
            _source=self._source + other._source,
        )
        logger.debug("merged Config from %s", new._source)
        return new

    def to_dict(self):
        return dataclasses.asdict(self)

    def __post_init__(self):
        self.validate(self.to_dict())

    def __repr__(self) -> str:
        sources = " | ".join(str(s) for s in self._source)
        formatted = f"<{type(self).__name__}: {sources}>"
        return formatted

    @staticmethod
    def validate(mapping):
        for name in ["types", "type_prefixes", "type_aliases"]:
            table = mapping[name]
            if not isinstance(table, dict):
                raise TypeError(f"{name} must be a dict")
            for key, value in table.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise TypeError(f"`{key} = {value}` in {name} must both be a str")

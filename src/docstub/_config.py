import dataclasses
import logging
from pathlib import Path
from typing import ClassVar

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    DEFAULT_CONFIG_PATH: ClassVar[Path] = Path(__file__).parent / "default_config.toml"

    extend_grammar: str = ""
    known_imports: dict[str, dict[str, str]] = dataclasses.field(default_factory=dict)
    replace_doctypes: dict[str, str] = dataclasses.field(default_factory=dict)

    _source: tuple[Path, ...] = ()

    @classmethod
    def from_toml(cls, path: Path | str) -> "Config":
        """Return configuration options in local TOML file if they exist."""
        path = Path(path)
        with open(path, "rb") as fp:
            raw = tomllib.load(fp)
        config = cls(**raw.get("tool", {}).get("docstub", {}), _source=(path,))
        logger.debug("created Config from %s", path)
        return config

    @classmethod
    def from_default(cls):
        config = cls.from_toml(cls.DEFAULT_CONFIG_PATH)
        return config

    def merge(self, other):
        """Merge contents with other and return a new Config instance."""
        if not isinstance(other, type(self)):
            return NotImplemented
        new = Config(
            extend_grammar=self.extend_grammar + other.extend_grammar,
            known_imports=self.known_imports | other.known_imports,
            replace_doctypes=self.replace_doctypes | other.replace_doctypes,
            _source=self._source + other._source,
        )
        logger.debug("merged Config from %s", new._source)
        return new

    def to_dict(self):
        return dataclasses.asdict(self)

    def __post_init__(self):
        if not isinstance(self.extend_grammar, str):
            raise TypeError("extended_grammar must be a string")
        if not isinstance(self.known_imports, dict):
            raise TypeError("known_imports must be a dict")
        if not isinstance(self.replace_doctypes, dict):
            raise TypeError("replace_doctypes must be a string")

    def __repr__(self):
        sources = " | ".join(str(s) for s in self._source)
        formatted = f"<{type(self).__name__}: {sources}>"
        return formatted

import dataclasses
import logging
import tomllib
from pathlib import Path
from pprint import pformat
from typing import ClassVar

import lark.visitors

logger: logging.Logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    TEMPLATE_PATH: ClassVar[Path] = Path(__file__).parent / "config_template.toml"
    NUMPY_PATH: ClassVar[Path] = Path(__file__).parent / "numpy_config.toml"

    types: dict[str, str] = dataclasses.field(default_factory=dict)
    type_prefixes: dict[str, str] = dataclasses.field(default_factory=dict)
    type_nicknames: dict[str, str] = dataclasses.field(default_factory=dict)
    ignore_files: list[str] = dataclasses.field(default_factory=list)
    doctype_grammar: str | None = None
    doctype_transformer: lark.visitors.Transformer | None = None

    config_paths: tuple[Path, ...] = ()

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
        config = cls(**raw.get("tool", {}).get("docstub", {}), config_paths=(path,))
        logger.debug("Created `Config` from %s", path)
        return config

    @classmethod
    def from_pyfile(cls, path):
        """

        Parameters
        ----------
        path : Path

        Returns
        -------
        config : Self
        """
        source = path.read_text()
        config = {}
        eval(source, locals=config)
        logger.debug("Created `Config` from %s", path)
        return config

    @classmethod
    def from_file(cls, path):
        """

        Parameters
        ----------
        path : Path
        """
        if path.suffix.lower() == ".toml":
            return cls.from_toml(path)
        elif path.suffix.lower() == ".py":
            return cls.from_pyfile(path)
        else:
            raise ValueError(f"unsupported config file type: {path}")

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
            type_nicknames=self.type_nicknames | other.type_nicknames,
            ignore_files=self.ignore_files + other.ignore_files,
            config_paths=self.config_paths + other.config_paths,
            doctype_grammar=other.doctype_grammar or self.doctype_grammar,
            doctype_transformer=other.doctype_transformer or self.doctype_transformer,
        )
        logger.debug("Merged Config from %s", new.config_paths)
        return new

    def to_dict(self):
        return dataclasses.asdict(self)

    def __post_init__(self):
        self.validate(self.to_dict())

    def __repr__(self) -> str:
        sources = " | ".join(str(s) for s in self.config_paths)
        formatted = f"<{type(self).__name__}: {sources}>"
        return formatted

    def __str__(self) -> str:
        return pformat(self.to_dict())

    @staticmethod
    def validate(mapping):
        """Make sure that a valid Config can be created from `mapping`.

        Parameters
        ----------
        mapping : Mapping

        Raises
        ------
        TypeError
        """
        for field in ["types", "type_prefixes", "type_nicknames"]:
            table = mapping[field]
            if not isinstance(table, dict):
                raise TypeError(f"{field} must be a dict")
            for key, value in table.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise TypeError(f"`{key} = {value}` in {field} must both be a str")

        for field in ["ignore_files"]:
            sequence = mapping[field]
            if not isinstance(sequence, list):
                raise TypeError(f"{field} must be a list")
            for value in sequence:
                if not isinstance(value, str):
                    raise TypeError(f"`{value}` in {field} must be a str")

        grammar = mapping["doctype_grammar"]
        if grammar and not isinstance(grammar, str):
            raise TypeError(f"`doctype_grammar` must be a str")

        transformer = mapping["doctype_transformer"]
        if transformer:
            if isinstance(transformer, lark.visitors.Transformer):
                raise TypeError(
                    "`doctype_transformer` must be a `lark.visitors.Transformer`"
                )
            if not hasattr(transformer, "start") or not callable(transformer.start):
                raise TypeError("`doctype_transformer.start` must be a callable")

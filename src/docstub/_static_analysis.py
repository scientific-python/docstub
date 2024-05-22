import builtins
from dataclasses import dataclass


known_builtins = set(dir(builtins))


@dataclass(slots=True, frozen=True)
class KnownType:
    """A name that must be imported."""

    import_name: str = None
    import_path: str = None
    import_alias: str = None
    is_builtin: bool = False

    @classmethod
    def from_cfg(cls, value) -> "ImportableType | BuiltIn":
        if value == "" or value == "builtin":
            return cls(is_builtin=True)

        path, tail = value.split("::", maxsplit=1)
        name, *alias = tail.split("::", maxsplit=1)
        assert name
        if not path:
            path = None
        if not alias:
            alias = None
        else:
            assert len(alias) == 1
            alias = alias[0]
        return cls(import_name=name, import_path=path, import_alias=alias)

    def __str__(self):
        if self.is_builtin:
            raise RuntimeError("cannot import builtin")
        out = f"import {self.import_name}"
        if self.import_path:
            out = f"from {self.import_path} {out}"
        if self.import_alias:
            out = f"{out} as {self.import_alias}"
        return out



def locate_import_path():
    pass

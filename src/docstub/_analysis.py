"""Collect type information."""

import builtins
from dataclasses import dataclass
from pathlib import Path

import libcst as cst


@dataclass(slots=True, frozen=True)
class DocName:
    """An atomic name (without ".") in a docstring type with import info.
    """

    use_name: str
    import_name: str = None
    import_path: str = None
    import_alias: str = None
    is_builtin: bool = False

    @classmethod
    def from_cfg(cls, docname: str, spec: dict):
        use_name = spec.get("use", spec.get("as", spec.get("import", docname)))

        import_name = docname
        if "import" in spec:
            import_name = spec["import"]

        docname = cls(
            use_name=use_name,
            import_name=spec.get("import"),
            import_path=spec.get("from"),
            import_alias=spec.get("as"),
            is_builtin=spec.get("builtin", False)
        )
        return docname

    def format_import(self):
        if self.is_builtin:
            raise RuntimeError("cannot import builtin")
        out = f"import {self.import_name}"
        if self.import_path:
            out = f"from {self.import_path} {out}"
        if self.import_alias:
            out = f"{out} as {self.import_alias}"
        return out


def builtin_types():
    """Return a map of types for all bultins (in the current runtime).

    Returns
    -------
    types : dict[str, DocName]
    """
    known_builtins = set(dir(builtins))
    types = {
        name: DocName(use_name=name, is_builtin=True) for name in known_builtins
    }
    return types


def find_module_paths_using_search():
    # TODO use from mypy.stubgen import find_module_paths_using_search ?
    #   https://github.com/python/mypy/blob/66b48cbe97bf9c7660525766afe6d7089a984769/mypy/stubgen.py#L1526
    pass
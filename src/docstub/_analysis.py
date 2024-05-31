"""Collect type information."""

import builtins
import collections.abc
import typing
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DocName:
    """An atomic name (without ".") in a docstring type with import info."""

    use_name: str
    import_name: str = None
    import_path: str = None
    import_alias: str = None
    is_builtin: bool = False

    @classmethod
    def from_cfg(cls, docname: str, spec: dict):
        use_name = docname
        if "import" in spec:
            use_name = spec["import"]
        if "as" in spec:
            use_name = spec["as"]
        if "use" in spec:
            use_name = spec["use"]

        import_name = docname
        if "use" in spec:
            import_name = spec["use"]
        if "import" in spec:
            import_name = spec["import"]

        docname = cls(
            use_name=use_name,
            import_name=import_name,
            import_path=spec.get("from"),
            import_alias=spec.get("as"),
            is_builtin=spec.get("builtin", False),
        )
        return docname

    def format_import(self):
        if self.is_builtin:
            msg = "cannot import builtin"
            raise RuntimeError(msg)
        out = f"import {self.import_name}"
        if self.import_path:
            out = f"from {self.import_path} {out}"
        if self.import_alias:
            out = f"{out} as {self.import_alias}"
        return out

    @property
    def has_import(self):
        return not self.is_builtin


def _is_type(value) -> bool:
    """Check if value is a type."""
    # Checking for isinstance(..., type) isn't enough, some types such as
    # typing.Literal don't pass that check. So combine with checking for a
    # __class__ attribute. Not sure about edge cases!
    is_type = isinstance(value, type) or hasattr(value, "__class__")
    return is_type


def _builtin_docnames():
    """Return docnames for all builtins (in the current runtime).

    Returns
    -------
    docnames : dict[str, DocName]
    """
    known_builtins = set(dir(builtins))

    docnames = {}
    for name in known_builtins:
        if name.startswith("_"):
            continue
        value = getattr(builtins, name)
        if not _is_type(value):
            continue
        docnames[name] = DocName(use_name=name, is_builtin=True)

    return docnames


def _typing_docnames():
    """Return docnames for public types in the `typing` module.

    Returns
    -------
    docnames : dict[str, DocName]
    """
    docnames = {}
    for name in typing.__all__:
        if name.startswith("_"):
            continue
        value = getattr(typing, name)
        if not _is_type(value):
            continue
        docnames[name] = DocName.from_cfg(name, spec={"from": "typing"})
    return docnames


def _collections_abc_docnames():
    """Return docnames for public types in the `collections.abc` module.

    Returns
    -------
    docnames : dict[str, DocName]
    """
    docnames = {}
    for name in collections.abc.__all__:
        if name.startswith("_"):
            continue
        value = getattr(collections.abc, name)
        if not _is_type(value):
            continue
        docnames[name] = DocName.from_cfg(name, spec={"from": "collections.abc"})
    return docnames


def common_docnames():
    """Return docnames for commonly supported types.

    This includes builtin types, and types from the `typing` or
    `collections.abc` module.

    Returns
    -------
    docnames : dict[str, DocName]
    """
    docnames = _builtin_docnames()
    docnames |= _typing_docnames()
    docnames |= _collections_abc_docnames()  # Overrides containers from typing
    return docnames


def find_module_paths_using_search():
    # TODO use from mypy.stubgen import find_module_paths_using_search ?
    #   https://github.com/python/mypy/blob/66b48cbe97bf9c7660525766afe6d7089a984769/mypy/stubgen.py#L1526
    pass

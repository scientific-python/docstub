"""Collect type information."""

import builtins
import collections.abc
import itertools
import typing
from dataclasses import dataclass
from pathlib import Path

import libcst as cst


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

    def __repr__(self):
        classname = type(self).__name__
        if self.has_import:
            info = f"{self.import_name}"
            if self.import_path:
                info = f"{self.import_path}.{info}"
            if self.import_alias:
                info = f"{info} as {self.import_alias}"
            if self.use_name not in info:
                info = f"{info}; {self.use_name}"
        else:
            info = f"{self.use_name} (builtin)"
        return f"{classname}: {info}"


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


class DocNameCollector(cst.CSTVisitor):

    @classmethod
    def collect(cls, file, module_name):
        file = Path(file)
        with file.open("r") as fo:
            source = fo.read()

        tree = cst.parse_module(source)
        collector = cls(module_name=module_name)
        tree.visit(collector)
        return collector.docnames

    def __init__(self, *, module_name):
        self.module_name = module_name
        self._stack = []
        self.docnames = {}

    def visit_ClassDef(self, node):
        self._stack.append(node.name.value)

        use_name = ".".join(self._stack[:1])
        qualname = f"{self.module_name}.{'.'.join(self._stack)}"
        docname = DocName(
            use_name=use_name, import_name=use_name, import_path=self.module_name
        )
        self.docnames[qualname] = docname

        return True

    def leave_ClassDef(self, original_node):
        self._stack.pop()

    def visit_FunctionDef(self, node):
        self._stack.append(node.name.value)
        return True

    def leave_FunctionDef(self, original_node):
        self._stack.pop()


class StaticInspector:
    """Try to find docnames when requested."""

    def __init__(self, *, source_pkgs=None, docnames=None):
        if source_pkgs is None:
            source_pkgs = []
        if docnames is None:
            docnames = {}

        self.source_pkgs: list[Path] = source_pkgs
        self.docnames = docnames
        self._inspected = {}

    @staticmethod
    def _accumulate_module_name(qualname):
        fragments = qualname.split(".")
        yield from itertools.accumulate(fragments, lambda x, y: f"{x}.{y}")

    def _find_modules(self, qualname):
        for source in self.source_pkgs:
            for module_name in self._accumulate_module_name(qualname):
                module_path = module_name.replace(".", "/")
                # Return PYI files last, so their content overwrites
                files = [
                    source / f"{module_path}.py",
                    source / f"{module_path}.pyi",
                    source / f"{module_path}/__init__.py",
                    source / f"{module_path}/__init__.pyi",
                ]
                for file in files:
                    if file.is_file():
                        yield file, module_name

    def inspect_module(self, file, module_name):
        """Collect docnames from the given file.

        Parameters
        ----------
        file : Path

        Returns
        -------
        collected : set[DocName]
        """
        if file in self._inspected:
            return self._inspected[file]

        docnames = DocNameCollector.collect(file, module_name)
        self._inspected[file] = docnames
        self.docnames.update(docnames)
        return docnames

    def query(self, qualname):
        out = self.docnames.get(qualname)
        if out is None:
            for file, module_name in self._find_modules(qualname):
                self.inspect_module(file, module_name)
            out = self.docnames.get(qualname)
        return out

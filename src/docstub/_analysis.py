"""Collect type information."""

import builtins
import collections.abc
import itertools
import logging
import re
import typing
from dataclasses import dataclass
from pathlib import Path

import libcst as cst

logger = logging.getLogger(__name__)


def _shared_leading_path(*paths):
    """Identify the common leading parts between import paths.

    Parameters
    ----------
    *paths : tuple[str]

    Returns
    -------
    shared : str
    """
    if len(paths) < 2:
        raise ValueError("need more than two paths")
    splits = (p.split(".") for p in paths)
    shared = []
    for paths in zip(*splits, strict=False):
        if all(paths[0] == p for p in paths):
            shared.append(paths[0])
        else:
            break
    return ".".join(shared)


@dataclass(slots=True, frozen=True)
class KnownImport:
    """Import information associated with a single known type annotation.

    Parameters
    ----------
    annotation_name : str
        Name of the type annotation
    import_name :
        Dotted names after "import".
    import_path :
        Dotted names after "from".
    import_alias :
        Name (without ".") after "as".
    """

    annotation_name: str
    import_name: str = None
    import_path: str = None
    import_alias: str = None
    is_builtin: bool = False

    @classmethod
    def one_from_config(cls, name, *, info):
        """Create one KnownImport from the configuration format.

        Parameters
        ----------
        name : str
        info : dict[{"from", "import", "as", "is_builtin"}, str]

        Returns
        -------
        TypeImport : Self
        """
        assert not (info.keys() - {"from", "import", "as", "is_builtin"})

        import_name = name
        if "import" in info:
            import_name = info["import"]

        known_import = cls(
            annotation_name=name,
            import_name=import_name,
            import_path=info.get("from"),
            import_alias=info.get("as"),
            is_builtin=info.get("is_builtin", False),
        )
        return known_import

    @classmethod
    def many_from_config(cls, mapping):
        """Create many KnownImports from the configuration format.

        Parameters
        ----------
        mapping : dict[str, dict[{"from", "import", "as", "is_builtin"}, str]]

        Returns
        -------
        known_imports : dict[str, Self]
        """
        known_imports = {
            name: cls.one_from_config(name, info=info) for name, info in mapping.items()
        }
        return known_imports

    def format_import(self, relative_to=None):
        if self.is_builtin:
            msg = "cannot import builtin"
            raise RuntimeError(msg)
        out = f"import {self.import_name}"

        import_path = self.import_path
        if import_path:
            if relative_to:
                shared = _shared_leading_path(relative_to, import_path)
                if shared == import_path:
                    import_path = "."
                else:
                    import_path = self.import_path.replace(shared, "")

            out = f"from {import_path} {out}"
        if self.import_alias:
            out = f"{out} as {self.import_alias}"
        return out

    @property
    def has_import(self):
        return not self.is_builtin

    def __post_init__(self):
        if "." in self.annotation_name:
            raise ValueError("'.' in the annotation name aren't yet supported")

        if self.import_alias and self.import_alias != self.annotation_name:
            raise ValueError(
                f"annotation name must match given import alias: "
                f"{self.annotation_name} != {self.import_alias}"
            )
        elif self.import_name != self.annotation_name:
            raise ValueError(
                f"annotation name must match import name if no alias is given: "
                f"{self.annotation_name} != {self.import_name}"
            )


@dataclass(slots=True, frozen=True)
class InspectionContext:
    """Currently inspected module and other information."""

    file_path: Path
    in_package_path: str


def _is_type(value) -> bool:
    """Check if value is a type."""
    # Checking for isinstance(..., type) isn't enough, some types such as
    # typing.Literal don't pass that check. So combine with checking for a
    # __class__ attribute. Not sure about edge cases!
    is_type = isinstance(value, type) or hasattr(value, "__class__")
    return is_type


def _builtin_imports():
    """Return known imports for all builtins (in the current runtime).

    Returns
    -------
    known_imports : dict[str, KnownImport]
    """
    known_builtins = set(dir(builtins))

    known_imports = {}
    for name in known_builtins:
        if name.startswith("_"):
            continue
        value = getattr(builtins, name)
        if not _is_type(value):
            continue
        known_imports[name] = KnownImport(annotation_name=name, is_builtin=True)

    return known_imports


def _typing_imports():
    """Return known imports for public types in the `typing` module.

    Returns
    -------
    known_imports : dict[str, KnownImport]
    """
    known_imports = {}
    for name in typing.__all__:
        if name.startswith("_"):
            continue
        value = getattr(typing, name)
        if not _is_type(value):
            continue
        known_imports[name] = KnownImport.one_from_config(name, info={"from": "typing"})
    return known_imports


def _collections_abc_imports():
    """Return known imports for public types in the `collections.abc` module.

    Returns
    -------
    known_imports : dict[str, KnownImport]
    """
    known_imports = {}
    for name in collections.abc.__all__:
        if name.startswith("_"):
            continue
        value = getattr(collections.abc, name)
        if not _is_type(value):
            continue
        known_imports[name] = KnownImport.one_from_config(
            name, info={"from": "collections.abc"}
        )
    return known_imports


def common_known_imports():
    """Return known imports for commonly supported types.

    This includes builtin types, and types from the `typing` or
    `collections.abc` module.

    Returns
    -------
    known_imports : dict[str, KnownImport]
    """
    known_imports = _builtin_imports()
    known_imports |= _typing_imports()
    known_imports |= _collections_abc_imports()  # Overrides containers from typing
    return known_imports


class KnownImportCollector(cst.CSTVisitor):
    @classmethod
    def collect(cls, file, module_name):
        file = Path(file)
        with file.open("r") as fo:
            source = fo.read()

        tree = cst.parse_module(source)
        collector = cls(module_name=module_name)
        tree.visit(collector)
        return collector.known_imports

    def __init__(self, *, module_name):
        self.module_name = module_name
        self._stack = []
        self.known_imports = {}

    def visit_ClassDef(self, node):
        self._stack.append(node.name.value)

        use_name = ".".join(self._stack[:1])
        qualname = f"{self.module_name}.{'.'.join(self._stack)}"
        known_import = KnownImport(
            use_name=use_name, import_name=use_name, import_path=self.module_name
        )
        self.known_imports[qualname] = known_import

        return True

    def leave_ClassDef(self, original_node):
        self._stack.pop()

    def visit_FunctionDef(self, node):
        self._stack.append(node.name.value)
        return True

    def leave_FunctionDef(self, original_node):
        self._stack.pop()


class StaticInspector:
    """Static analysis of Python packages.

    Attributes
    ----------
    current_source : ~.PackageFile | None

    Examples
    --------
    >>> from docstub._analysis import StaticInspector, common_known_imports
    >>> inspector = StaticInspector(known_imports=common_known_imports())
    >>> inspector.query("Any")
    """

    def __init__(
        self,
        *,
        source_pkgs=None,
        known_imports=None,
    ):
        """
        Parameters
        ----------
        source_pkgs: list[Path], optional
        known_imports: dict[str, KnownImport], optional
        """
        if source_pkgs is None:
            source_pkgs = []
        if known_imports is None:
            known_imports = {}

        self.current_source = None
        self.source_pkgs = source_pkgs
        self._inspected = {"initial": known_imports}

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
        """Collect known imports from the given file.

        Parameters
        ----------
        file : Path

        Returns
        -------
        collected : set[KnownImport]
        """
        if file in self._inspected:
            return self._inspected[file]

        known_imports = KnownImportCollector.collect(file, module_name)
        self._inspected[file] = known_imports
        self.known_imports.update(known_imports)
        return known_imports

    def query(self, qualname):
        """
        Parameters
        ----------
        qualname : str

        Returns
        -------
        out : KnownImport | None
        """
        out = self.known_imports.get(qualname)

        *prefix, name = qualname.split(".")
        if not out and "~" in prefix:
            pattern = qualname.replace(".", r"\.")
            pattern = pattern.replace("~", ".*")
            pattern = re.compile(pattern + "$")
            matches = {
                key: value
                for key, value in self.known_imports.items()
                if re.match(pattern, key)
            }
            if len(matches) > 1:
                shortest_key = sorted(matches.keys(), key=lambda x: len(x))[0]
                out = matches[shortest_key]
                logger.warning(
                    "%s matches multiple types %s, using %s",
                    qualname,
                    matches.keys(),
                    shortest_key,
                )
            elif len(matches) == 1:
                _, out = matches.popitem()

        elif not out and self.current_source:
            try_qualname = f"{self.current_source.import_path}.{qualname}"
            out = self.known_imports.get(try_qualname)

        return out

    @property
    def known_imports(self):
        current_known_imports = {}

        for _, known_imports in self._inspected.items():
            current_known_imports.update(known_imports)

        return current_known_imports

    def __repr__(self):
        repr = f"{type(self).__name__}({self.source_pkgs})"
        return repr

# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# ruff: noqa: T201

import inspect
import shutil
import sys
from datetime import date
from functools import cache
from pathlib import Path
from subprocess import check_output

import setuptools_scm

import docstub
from docstub._path_utils import walk_source_package
from docstub._utils import module_name_from_path

# -- Project information ------------------------------------------------------

project = "docstub"

version = setuptools_scm.get_version(search_parent_directories=True)
version = f"v{version}"
version = version.replace("+", "<wbr>+")  # Insert wrapping hint for long dev version

copyright = f"{date.today().year} docstub contributors."

templates_path = ["templates"]


# -- Extension configuration --------------------------------------------------

extensions = [
    "sphinx.ext.intersphinx",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.linkcode",
    "sphinx_copybutton",
    "myst_parser",
    "numpydoc",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "typing": ("https://typing.python.org/en/latest/", None),
    "lark": ("https://lark-parser.readthedocs.io/en/latest/", None),
    "libcst": ("https://libcst.readthedocs.io/en/latest/", None),
}

myst_enable_extensions = [
    # Enable fieldlist to allow for Field Lists like in rST (e.g., :orphan:)
    "fieldlist",
    # Enable fencing directives with `:::`
    "colon_fence",
]

myst_heading_anchors = 3

autosummary_generate = True

autodoc_default_options = {"show-inheritance": True, "private-members": True}

autodoc_member_order = "alphabetical"

numpydoc_show_class_members = False

add_module_names = False


@cache
def get_git_revision_hash():
    """Extract hash of current revision."""
    output = check_output(["git", "rev-parse", "HEAD"])
    full_hash = output.decode().strip()
    return full_hash


def linkcode_resolve(domain, info):
    """Resolve link for code objects.

    This function is a hook called by the sphinx extension linkcode [1]_.
    Loosely inspired by a function in NumPy [2]_.

    Parameters
    ----------
    domain : str
        Specifies the language domain of the given object.
    info : dict
        A dictionary describing the object.

    Returns
    -------
    url : str
        An URL to the source code.

    References
    ---------
    .. [1] http://www.sphinx-doc.org/en/master/usage/extensions/linkcode.html
    .. [2] https://github.com/numpy/numpy/blob/cbf3a081271a43e980e3c2f76625deb43fd53922/doc/source/conf.py#L303-L357
    """
    if domain != "py" or "module" not in info or "fullname" not in info:
        return None

    # Get reference to the object, start with the module
    obj = sys.modules.get(info["module"])
    for part in info["fullname"].split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError:
            # Not all attributes exist, e.g. instance attributes
            return None
    # Strip decorators which would resolve to the source of the decorator
    obj = inspect.unwrap(obj)

    file = info["module"].replace(".", "/")
    try:
        source, start_line = inspect.getsourcelines(obj)
    except (TypeError, OSError):
        # Skip unexpected types, occurs when `obj` isn't a module, class, method,
        # function, etc.
        return None
    stop_line = start_line + len(source) - 1

    template = "https://github.com/scientific-python/docstub/blob/{revision}/src/{file}.py#L{start}-{stop}"
    revision = get_git_revision_hash()
    assert len(revision) == 40
    url = template.format(
        revision=revision, file=file, start=start_line, stop=stop_line
    )
    return url


# -- HTML output --------------------------------------------------------------

html_theme = "furo"

html_static_path = ["static"]

html_css_files = ["furo_overrides.css"]

html_title = "docstub docs"

html_theme_options = {
    "light_css_variables": {
        # Make font less harsh on light theme
        "color-foreground-primary": "#363636",
        "color-announcement-background": "var(--color-admonition-title-background--important)",
        "color-announcement-text": "var(--color-content-foreground)",
        "admonition-font-size": "var(--font-size--normal)",
    },
    "dark_css_variables": {
        "color-announcement-background": "var(--color-admonition-title-background--important)",
    },
    "announcement": "<b>🧪 In early development!</b> API and behavior may break between releases.",
}

html_sidebars = {
    "**": [
        "sidebar/brand.html",
        "version.html",
        "sidebar/search.html",
        "sidebar/scroll-start.html",
        "sidebar/navigation.html",
        "external-links.html",
        "ethical-ads.html",
        "sidebar/scroll-end.html",
        "sidebar/variant-selector.html",
    ]
}


# -- Pregenerate doc sources ---------------------------------------------------

PYTHON_API_TEMPLATE = """.. Generated by `conf.py`

Python API
==========

Docstub is primarily intended to be used as a command line tool.
Nevertheless we document it's Python facing API here.

Modules
-------

.. autosummary::
  :toctree:
  :recursive:
  :template: module.rst
  :nosignatures:

"""


def is_private_qualname(name):
    parts = name.split(".")
    return any(p.startswith("_") for p in parts)


def write_python_api(module, *, exclude_modules=()):
    """Create ``python_api/index.rst`` as an entrypoint for autosummary.

    Parameters
    ----------
    module : ModuleType
    exclude_modules : tuple[str, ...]
    """
    package_path = Path(module.__file__).parent

    names = sorted(
        module_name_from_path(path) for path in walk_source_package(package_path)
    )
    names = [n for n in names if n not in exclude_modules]

    # Sort private modules after public ones
    public_names = [n for n in names if not is_private_qualname(n)]
    private_names = [n for n in names if is_private_qualname(n)]
    names = public_names + private_names

    names = [f"  {name}" for name in names]
    content = "\n".join([PYTHON_API_TEMPLATE, *names])

    api_dir = Path(__file__).parent / "python_api"
    if api_dir.exists():
        shutil.rmtree(api_dir)
        print(f"[conf.py] deleted {api_dir}")

    api_dir.mkdir()
    index_path = api_dir / "index.rst"
    index_path.write_text(content)
    print(f"[conf.py] wrote {index_path}")


write_python_api(
    docstub,
    exclude_modules=("docstub.__main__", "docstub._version"),
)


# -- Patch Sphinx --------------------------------------------------------------


def autodoc_skip_members(app, obj_type, name, obj, skip, options):
    """Force autosummary to show private members too."""
    # TODO ensure that click commands are included as well
    if name.startswith("_") and not name.startswith("__"):
        # Force autosummary to show private members to,
        # `autodoc_default_options = {"private-members": True}`
        # doesn't solve this on its own
        return False
    return None  # Default behavior


def truncate_signature_defaults(
    app, what, name, obj, options, signature, return_annotation
):
    """Truncate long defaults in function signatures."""
    if what in {"module", "property", "attribute"}:
        return signature, return_annotation

    try:
        signature_object = inspect.signature(obj)
    except (TypeError, ValueError):
        pass
    else:
        for param in signature_object.parameters.values():
            if param.default is inspect.Parameter.empty:
                continue
            default = repr(param.default)
            if len(default) > 30:
                truncated = default[:12] + "..." + default[-12:]
                signature = signature.replace(default, truncated)

    return signature, return_annotation


def setup(app):
    app.connect("autodoc-process-signature", truncate_signature_defaults)
    app.connect("autodoc-skip-member", autodoc_skip_members)

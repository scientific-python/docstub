# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

from datetime import date

import setuptools_scm

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
    "sphinx_copybutton",
    # https://numpydoc.readthedocs.io/
    "myst_parser",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "typing": ("https://typing.python.org/en/latest/", None),
}

myst_enable_extensions = [
    # Enable fieldlist to allow for Field Lists like in rST (e.g., :orphan:)
    "fieldlist",
    # Enable fencing directives with `:::`
    "colon_fence",
]

myst_heading_anchors = 3


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

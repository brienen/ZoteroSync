"""Sphinx configuration."""
project = "Zoterosync"
author = "Arjen Brienen"
copyright = "2025, Arjen Brienen"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_click",
    "myst_parser",
]
autodoc_typehints = "description"
html_theme = "furo"

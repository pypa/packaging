# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import os

# -- Project information loading ----------------------------------------------

ABOUT = {}
_BASE_DIR = os.path.join(os.path.dirname(__file__), os.pardir)
with open(os.path.join(_BASE_DIR, "src", "packaging", "__init__.py")) as f:
    exec(f.read(), ABOUT)

# -- General configuration ----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

# Add any Sphinx extension module names here, as strings. They can be
# extensions  coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "sphinx_toolbox.more_autodoc.autotypeddict",
]

# General information about the project.
project = "Packaging"
version = ABOUT["__version__"]
release = ABOUT["__version__"]
copyright = ABOUT["__copyright__"]

# -- Options for HTML output --------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.

html_theme = "furo"
html_title = project

# -- Options for autodoc ----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#configuration

autodoc_member_order = "bysource"
autodoc_preserve_defaults = True

# Automatically extract typehints when specified and place them in
# descriptions of the relevant function/method.
autodoc_typehints = "description"

# Don't show class signature with the class' name.
autodoc_class_signature = "separated"

# -- Options for extlinks -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/extlinks.html#configuration

extlinks = {
    "issue": ("https://github.com/pypa/packaging/issues/%s", "#%s"),
    "pull": ("https://github.com/pypa/packaging/pull/%s", "PR #%s"),
}

# -- Options for intersphinx ----------------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#configuration

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "pypug": ("https://packaging.python.org/", None),
}

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html



# Add the directory containing your module to the Python paths
import os
import sys
print(sys.executable)
import pywifes

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath('../src/pywifes/'))
sys.path.insert(0, os.path.abspath('../../reduction_scripts/'))


# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'PyWiFeS'
copyright = '2024, Automation Team'
author = 'Automation Team'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx.ext.autodoc',
              'sphinx.ext.napoleon']

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']

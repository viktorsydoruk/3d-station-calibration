"""Project-root package marker.

The project directory name is not a valid Python identifier, so this file is
also imported as a standalone module by pytest when collecting the project
root. Only re-export the library when imported as a real package.
"""

if __package__:
    from ._3dsc_libs import *

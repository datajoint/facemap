"""
Copright © 2023 Howard Hughes Medical Institute, Authored by Carsen Stringer and Atika Syeda.
"""

from importlib.metadata import PackageNotFoundError, version
import sys 
from platform import python_version
import torch, numpy

try:
    version = version("facemap")
except PackageNotFoundError:
    version = 'unknown'

version_str = f"""
facemap version: \t{version} 
platform:       \t{sys.platform} 
python version: \t{python_version()} 
torch version:  \t{torch.__version__}
numpy version:  \t{numpy.__version__}
"""
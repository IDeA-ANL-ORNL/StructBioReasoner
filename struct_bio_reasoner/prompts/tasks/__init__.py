"""Auto-discover and import all task modules in this package."""

import importlib
import pkgutil
from pathlib import Path

for _finder, _name, _ispkg in pkgutil.iter_modules([str(Path(__file__).parent)]):
    importlib.import_module(f"{__package__}.{_name}")

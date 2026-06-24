"""Worker Bee — auto-register all tools on package import."""
import importlib
import os
import pkgutil
import sys

_tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
for _, _mod_name, _ in pkgutil.iter_modules([_tools_dir]):
    if not _mod_name.startswith("_"):
        try:
            importlib.import_module(f"tools.{_mod_name}")
        except Exception as e:
            print(f"  [Tool load error] {_mod_name}: {e}", file=sys.stderr)

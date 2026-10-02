import os
import sys
import glob

# Automatically add the local .venv site-packages to sys.path so any python3 command works out of the box
_base = os.path.dirname(os.path.abspath(__file__))
_pkgs = glob.glob(os.path.join(_base, ".venv/lib/python*/site-packages"))
if _pkgs and _pkgs[0] not in sys.path:
    sys.path.insert(0, _pkgs[0])

import runpy
import sys
from pathlib import Path

# Windowless launcher used by "Start with Windows": pythonw.exe start.pyw
sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_module("metranscript.server", run_name="__main__")

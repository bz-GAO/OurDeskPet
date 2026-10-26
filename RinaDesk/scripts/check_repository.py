"""Compatibility entrypoint for the unified public source audit."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[2]
raise SystemExit(subprocess.call([sys.executable,str(root/'scripts/check-release.py'),'--root',str(root)]))

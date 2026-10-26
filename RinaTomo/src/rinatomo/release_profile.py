"""Private data for the public OurDeskPet distribution, isolated from developer state."""
import os
from pathlib import Path

def initialize():
    # Do not inherit a developer API key or caller-selected config home.
    for name in list(os.environ):
        if name.startswith(('DASHSCOPE_', 'RINATOMO_', 'RINAYAKI_')):
            os.environ.pop(name, None)
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'OurDeskPet'
    os.environ['RINATOMO_CONFIG_HOME'] = str(base / 'RinaTomo')
    os.environ['RINAYAKI_CONFIG_HOME'] = str(base / 'RinaYaki')
    os.environ['RINAYAKI_ROOT'] = str(Path(__file__).resolve().parents[3] / 'RinaYaki')
    runtime = Path(__file__).resolve().parents[3] / 'runtime' / 'python' / 'tcl'
    if runtime.is_dir():
        os.environ['TCL_LIBRARY'] = str(runtime / 'tcl8.6')
        os.environ['TK_LIBRARY'] = str(runtime / 'tk8.6')

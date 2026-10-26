"""Assemble portable component runtimes. No user config or account data is copied."""
from pathlib import Path
import argparse
import shutil

parser=argparse.ArgumentParser()
parser.add_argument('--release',type=Path,required=True)
parser.add_argument('--python-home',type=Path,required=True)
parser.add_argument('--yaki-environment',type=Path,required=True)
parser.add_argument('--yaki-tools',type=Path,required=True)
args=parser.parse_args()
root=args.release.resolve()
if not (root/'release-manifest.json').is_file():raise SystemExit('Not an OurDeskPet release root.')
runtime=root/'runtime'; base=runtime/'python'
def ignore(directory,names):
    return [name for name in names if name in ('site-packages','__pycache__','test','tests','idlelib','ensurepip') or name.endswith(('.pyc','.pyo','.log'))]
base.mkdir(parents=True,exist_ok=True)
for name in ('Lib','DLLs','tcl'):
    shutil.copytree(args.python_home/name,base/name,ignore=ignore,dirs_exist_ok=True)
shutil.copy2(args.python_home/'LICENSE.txt',base/'LICENSE.txt')
site=runtime/'site-packages';site.mkdir(exist_ok=True)
for path in (args.yaki_environment/'Lib/site-packages').iterdir():
    name=path.name.lower()
    if name in ('__pycache__','pip') or name.startswith(('pip-','rinayaki','__editable__')) or name.endswith(('.pth','.pyc')):continue
    target=site/path.name
    if path.is_dir():shutil.copytree(path,target,ignore=lambda directory,names:[name for name in names if name=='__pycache__' or name.endswith('.pyc') or name=='direct_url.json'],dirs_exist_ok=True)
    else:shutil.copy2(path,target)
for project in ('RinaYaki','RinaTomo'):
    scripts=root/project/'.venv/Scripts';scripts.mkdir(parents=True,exist_ok=True)
    for name in ('python.exe','pythonw.exe','python3.dll','python314.dll','vcruntime140.dll','vcruntime140_1.dll'):
        shutil.copy2(args.python_home/name,scripts/name)
    (scripts/'python314._pth').write_text('../../../runtime/python/Lib\n../../../runtime/python/DLLs\n../../../runtime/site-packages\n../../src\nimport site\n',encoding='utf-8')
tools=root/'RinaYaki/.tools';tools.mkdir(exist_ok=True)
for name in ('ffmpeg/ffmpeg.exe','ffmpeg/ffprobe.exe','yt-dlp.exe'):
    source=args.yaki_tools/name
    if not source.is_file():raise SystemExit('Required media tool missing: '+name)
    target=tools/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
print('Portable Python, shared dependency packages and media executables prepared.')

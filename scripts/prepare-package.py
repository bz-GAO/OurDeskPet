"""Build an explicit resource map; development folders and credentials cannot enter it."""
import argparse
import json
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,required=True)
args=parser.parse_args();root=args.root.resolve()
resources={}
def add(relative):
    path=root/relative
    if not path.exists():raise SystemExit('Missing required package resource: '+relative)
    resources[path.as_posix()]=relative
for folder in ('RinaDesk/assistant','RinaDesk/prompts','RinaDesk/skills','RinaDesk/docs','RinaDesk/app/src','RinaDesk/app/src-tauri/src',
               'RinaYaki/src','RinaYaki/scripts','RinaYaki/config','RinaYaki/assets','RinaYaki/.venv','RinaYaki/.tools',
               'RinaTomo/src','RinaTomo/.venv','runtime'):
    add(folder)
for file in ('RinaDesk/release-profile.json','RinaDesk/app/src-tauri/tauri.conf.json','RinaDesk/README.md',
             'RinaYaki/pyproject.toml','RinaYaki/README.md','RinaYaki/Start-RinaYaki.vbs','RinaYaki/Start-RinaYaki.cmd',
             'RinaTomo/pyproject.toml','RinaTomo/README.md','RinaTomo/Start-RinaTomo.vbs','RinaTomo/Start-RinaTomo.cmd',
             'LICENSE.txt','THIRD-PARTY-NOTICES.md','THIRD-PARTY-LICENSES.txt','release-manifest.json'):
    add(file)
packaging=root/'packaging';packaging.mkdir(exist_ok=True)
anchor=packaging/'rinadesk-root.txt';anchor.write_text('RinaDesk',encoding='utf-8')
resources[anchor.as_posix()]='rinadesk-root.txt'
config={'bundle':{'resources':resources}}
(root/'RinaDesk/app/src-tauri/tauri.package.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
print('Package resource map: '+str(len(resources))+' entries.')

"""Collect notices from the actual locked dependencies without credentials or user data."""
from pathlib import Path
import argparse
import json
import os
import tomllib

parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
root=parser.parse_args().root.resolve();sections=[]
def collect(folder:Path,label:str):
    texts=[]
    for item in folder.iterdir():
        if item.is_file() and item.name.lower().startswith(('license','licence','copying','copyright','notice')) and item.stat().st_size<512000:
            texts.append(item.read_text(encoding='utf-8',errors='replace'))
    if texts:sections.append(label+'\n\n'+'\n\n'.join(texts))
modules=root/'RinaDesk/app/node_modules'
for manifest in modules.rglob('package.json'):
    if len(manifest.relative_to(modules).parts)>5:continue
    try:meta=json.loads(manifest.read_text(encoding='utf-8'))
    except (ValueError,OSError):continue
    collect(manifest.parent,str(meta.get('name','package'))+' '+str(meta.get('version','')))
cargo_home=Path(os.environ.get('CARGO_HOME') or Path.home()/'.cargo')
registries=list((cargo_home/'registry/src').glob('*'))
locked=tomllib.loads((root/'RinaDesk/app/src-tauri/Cargo.lock').read_text(encoding='utf-8'))
for package in locked['package']:
    if 'source' not in package:continue
    for registry in registries:
        folder=registry/(package['name']+'-'+package['version'])
        if folder.is_dir():collect(folder,package['name']+' '+package['version']);break
text='Third-party software notices for OurDeskPet\nProject-owned non-commercial terms do not override these licenses.\n\n'+'\n\n'+'\n\n'+'\n\n'.join('\n'+'='*72+'\n'+section for section in sections)
(root/'THIRD-PARTY-LICENSES.txt').write_text(text,encoding='utf-8')
print('Collected '+str(len(sections))+' dependency license sections.')

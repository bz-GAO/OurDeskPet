"""Audit the exact Git source candidates of the public distribution."""
from pathlib import Path
import argparse
import importlib.util
import re
import subprocess

parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--compare-source',type=Path)
args=parser.parse_args();root=args.root.resolve()
result=subprocess.run(['git','-c',f'safe.directory={root.as_posix()}','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root,capture_output=True,check=True)
names=[name for name in result.stdout.decode('utf-8').split('\0') if name]
secret=re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})')
private_parts={'.venv','node_modules','target','runtime','.build-cache','.tools','Conversations','workspaces','references'}
errors=[];known=set()
if args.compare_source:
    source=args.compare_source.resolve();spec=importlib.util.spec_from_file_location('workspace_check',source/'scripts/check_workspace.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);known=module.local_sensitive_values(source)
for name in names:
    path=root/name;relative=Path(name)
    if any(part in private_parts for part in relative.parts):errors.append('Private/build directory: '+name);continue
    if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):errors.append('Redirected source: '+name);continue
    if path.name.startswith('.env') and path.name!='.env.example':errors.append('Private environment: '+name);continue
    if path.suffix.lower() in ('.exe','.dll','.wav','.mp3','.zip','.bin','.pyc'):errors.append('Binary/private source candidate: '+name);continue
    if not path.is_file():continue
    if path.suffix.lower() in ('.py','.rs','.ts','.tsx','.js','.cjs','.mjs','.json','.toml','.md','.txt','.ps1','.vbs','.cmd','.yaml','.yml','.html','.css') or path.name.startswith('.'):
        text=path.read_text(encoding='utf-8',errors='replace')
        if secret.search(text) or any(value in text for value in known):errors.append('Possible credential/account value: '+name)
config=__import__('json').loads((root/'RinaDesk/app/src-tauri/tauri.conf.json').read_text(encoding='utf-8'))
if config['identifier']!='com.bzgao.ourdeskpet':errors.append('Release application identity is not isolated.')
if config['mainBinaryName']!='OurDeskPet':errors.append('Release process name is not isolated.')
if errors:raise SystemExit('\n'.join(errors))
print(f'PASS: {len(names)} public source candidates; runtime binaries, developer data and known private values excluded.')

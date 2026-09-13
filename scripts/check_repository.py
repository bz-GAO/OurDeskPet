"""Check final image inventory and git-add candidates, without staging or reading secrets."""
from pathlib import Path
import hashlib,json,subprocess,sys
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'assets/manifest.json').read_text(encoding='utf8'))
expected={a['path']:a for a in manifest['assets']}
errors=[]
for path,item in expected.items():
 p=root/path
 if not p.is_file():errors.append(f'Missing asset: {path}')
 elif hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:errors.append(f'Update asset manifest hash: {path}')
result=subprocess.run(['git','-c',f'safe.directory={root.as_posix()}','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root,capture_output=True,check=True)
paths=set(result.stdout.decode('utf8').split('\0'))
images=[]
for path in sorted(paths):
 p=root/path
 if not p.is_file():continue
 if p.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif','.svg','.ico','.icns'}:
  images.append(path)
  if path not in expected:errors.append(f'Non-final image in submission candidates: {path}')
 if path.startswith(('.local-archive/','references/')) or p.suffix.lower()=='.lnk' or (p.name.startswith('.env') and p.name!='.env.example'):
  errors.append(f'Local-only file in submission candidates: {path}')
if errors:print('\n'.join(errors));sys.exit(1)
print(f'PASS: {len(images)} final images only; manifest hashes match; no local archives, shortcuts or .env in candidates.')

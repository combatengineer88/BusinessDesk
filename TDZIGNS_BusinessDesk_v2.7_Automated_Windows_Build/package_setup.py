"""Validate and publish Inno Setup EXE alongside the existing ONEDIR ZIP.

Run after package_release.py and after ISCC compiled businessdesk.iss.
"""
import hashlib
import json
import re
from pathlib import Path

HERE=Path(__file__).resolve().parent
source=(HERE/'businessdesk.py').read_text(encoding='utf-8')
match=re.search(r"^VERSION = '([0-9]+\.[0-9]+\.[0-9]+)'",source,re.M)
if not match:raise SystemExit('BusinessDesk version missing')
version=match.group(1)
setup=HERE/'output'/f'TDZIGNS_BusinessDesk_Setup_{version}.exe'
if not setup.is_file() or setup.stat().st_size<1_000_000:
    raise SystemExit(f'Missing or suspicious Windows Setup EXE: {setup}')
with setup.open('rb') as file:
    if file.read(2)!=b'MZ':raise SystemExit('Windows Setup does not have an MZ executable header')
sha=hashlib.sha256(setup.read_bytes()).hexdigest()
checksum=setup.with_suffix('.sha256')
checksum.write_text(f'{sha}  {setup.name}\n',encoding='utf-8')
manifest_path=HERE/'update_manifest.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
if manifest.get('version')!=version:raise SystemExit('Update manifest version mismatch')
manifest['installer_url']=f'https://github.com/combatengineer88/BusinessDesk/releases/download/v{version}/{setup.name}'
manifest['installer_sha256']=sha
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Published Windows Setup installer:',setup.name,sha)

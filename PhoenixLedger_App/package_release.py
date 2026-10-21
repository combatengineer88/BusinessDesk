"""Bundle PyInstaller ONEDIR output into a verifiable GitHub update ZIP."""
from pathlib import Path
import hashlib, json, zipfile, re
from release_layout import valid_release_names

source=(Path(__file__).resolve().parent/'businessdesk.py').read_text(encoding='utf-8')
match=re.search(r"^VERSION = '([0-9]+\.[0-9]+\.[0-9]+)'",source,re.M)
if not match:
    raise SystemExit('Could not determine PhoenixLedger application version')
VERSION = match.group(1)
REPOSITORY = "combatengineer88/BusinessDesk"
DIST = Path('dist/PhoenixLedger')
EXE = DIST / 'PhoenixLedger.exe'
DLL = DIST / '_internal/python312.dll'
if not EXE.is_file() or not DLL.is_file():
    raise SystemExit('Missing ONEDIR Windows app or Python DLL. Build with --onedir first.')
ZIP=Path(f'PhoenixLedger_{VERSION}.zip')
with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for item in sorted(DIST.rglob('*')):
        if item.is_file():
            archive.write(item,arcname=item.relative_to(DIST).as_posix())
with zipfile.ZipFile(ZIP) as archive:
    if not valid_release_names(archive.namelist()):
        raise SystemExit('Release layout is invalid; refusing to publish')
digest=hashlib.sha256(ZIP.read_bytes()).hexdigest()
ZIP.with_suffix('.sha256').write_text(f'{digest}  {ZIP.name}\n',encoding='utf-8')
manifest={'version':VERSION,'url':f'https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{ZIP.name}','sha256':digest}
Path('update_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Prepared ONEDIR Windows release:',ZIP.name)

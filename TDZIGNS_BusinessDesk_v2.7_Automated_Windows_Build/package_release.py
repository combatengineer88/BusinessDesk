"""Bundle PyInstaller ONEDIR output into a verifiable GitHub update ZIP."""
from pathlib import Path
import hashlib, json, zipfile
from release_layout import valid_release_names

VERSION = "2.9.8"
REPOSITORY = "combatengineer88/BusinessDesk"
DIST = Path('dist/TDZIGNS_BusinessDesk')
EXE = DIST / 'TDZIGNS_BusinessDesk.exe'
DLL = DIST / '_internal/python312.dll'
if not EXE.is_file() or not DLL.is_file():
    raise SystemExit('Missing ONEDIR Windows app or Python DLL. Build with --onedir first.')
ZIP=Path(f'TDZIGNS_BusinessDesk_{VERSION}.zip')
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

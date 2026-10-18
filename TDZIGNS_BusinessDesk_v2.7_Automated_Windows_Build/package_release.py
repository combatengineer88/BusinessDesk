"""Package a prebuilt Windows EXE and SHA-256 manifest for a tagged GitHub Release."""
import hashlib
import json
import zipfile
from pathlib import Path

VERSION = "2.9.3"
REPOSITORY = "combatengineer88/BusinessDesk"
TAG = f"v{VERSION}"
EXE = Path("dist/TDZIGNS_BusinessDesk.exe")
if not EXE.is_file():
    raise SystemExit("Missing dist/TDZIGNS_BusinessDesk.exe: run the Windows build first.")

ZIP = Path(f"TDZIGNS_BusinessDesk_{VERSION}.zip")
with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(EXE, arcname="TDZIGNS_BusinessDesk.exe")
digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()
ZIP.with_suffix(".sha256").write_text(f"{digest}  {ZIP.name}\n", encoding="utf-8")
manifest = {
    "version": VERSION,
    "url": f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{ZIP.name}",
    "sha256": digest,
}
Path("update_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print("Ready for release:", ZIP.name, ZIP.with_suffix('.sha256').name, "update_manifest.json")

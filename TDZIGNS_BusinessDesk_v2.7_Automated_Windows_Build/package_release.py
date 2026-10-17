"""Run on Windows after building the EXE to create an update ZIP and manifest."""
import hashlib, json, zipfile
from pathlib import Path
VERSION = "2.7.0"
EXE = Path("dist/TDZIGNS_BusinessDesk.exe")
if not EXE.is_file():
    raise SystemExit("Build the Windows EXE first with build_windows.bat")
ZIP = Path(f"TDZIGNS_BusinessDesk_{VERSION}.zip")
with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
    z.write(EXE, arcname="TDZIGNS_BusinessDesk.exe")
digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()
Path(ZIP.with_suffix(".sha256")).write_text(digest+"  "+ZIP.name+"\n",encoding="utf-8")
manifest = {"version": VERSION, "url": "https://REPLACE-WITH-YOUR-HOST/"+ZIP.name, "sha256": digest}
Path("update_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print("Created:",ZIP,"and update_manifest.json. Set a real HTTPS URL before publishing.")

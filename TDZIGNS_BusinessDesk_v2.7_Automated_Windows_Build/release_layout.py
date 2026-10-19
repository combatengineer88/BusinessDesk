"""Strict Windows onedir update ZIP validation (no runtime imports)."""
from pathlib import PurePosixPath
import zipfile

EXE = 'TDZIGNS_BusinessDesk.exe'
RUNTIME_PREFIX = '_internal/'


def valid_release_names(names):
    files = [x for x in names if not x.endswith('/')]
    if not files or len(files) > 12000 or len(set(files)) != len(files):
        return False
    if EXE not in files:
        return False
    if not any(x.casefold() == '_internal/python312.dll' for x in files):
        return False
    for item in files:
        path=PurePosixPath(item)
        if item.startswith('/') or '\\' in item or '..' in path.parts:
            return False
        if not (item == EXE or item.startswith(RUNTIME_PREFIX)):
            return False
    return True


def inspect_release(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        entries = [e for e in archive.infolist() if not e.is_dir()]
        if not valid_release_names([e.filename for e in entries]):
            raise ValueError('Expected EXE and _internal/python312.dll in release ZIP')
        if not 100_000 < archive.getinfo(EXE).file_size < 300_000_000:
            raise ValueError('Unexpected EXE size')
        if sum(e.file_size for e in entries) > 1_000_000_000:
            raise ValueError('Update package is too large when extracted')
        return len(entries)

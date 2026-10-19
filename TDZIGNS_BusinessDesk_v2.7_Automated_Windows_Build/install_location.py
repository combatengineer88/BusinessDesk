"""Permanent installation targeting for GitHub updater.

Never install into temporary ZIP extraction folders. Pure functions remain easy to
regression test on non-Windows CI while Windows uses real TEMP/LOCALAPPDATA values.
"""
from pathlib import PureWindowsPath

EXE_NAME = "TDZIGNS_BusinessDesk.exe"


def _parts(path):
    return tuple(part.casefold() for part in PureWindowsPath(str(path)).parts)


def is_temporary_install(executable, temp_root):
    """True for a Windows Temp descendant or Explorer's ZIP extraction layout."""
    path = PureWindowsPath(str(executable))
    if path.name.casefold() != EXE_NAME.casefold():
        raise ValueError("Unexpected BusinessDesk executable name")
    file_parts = _parts(path)
    temp_parts = _parts(temp_root) if temp_root else ()
    if temp_parts and file_parts[:len(temp_parts)] == temp_parts:
        return True
    # Zip extraction folder name seen in Windows Explorer diagnostics:
    # 4f48..._BusinessDesk_2.9.3.zip.a81\TDZIGNS_BusinessDesk.exe
    return any('.zip.' in part for part in file_parts[:-1])


def choose_install_target(executable, local_app_data, temp_root):
    """BusinessDesk installs to a predictable per-user folder, including migration from old installs.

    The second return value indicates whether the launcher must create/migrate shortcuts.
    """
    current = PureWindowsPath(str(executable))
    stable = PureWindowsPath(str(local_app_data)) / 'Programs' / 'TDZIGNS BusinessDesk' / EXE_NAME
    if current.name.casefold() != EXE_NAME.casefold():
        raise ValueError('Unexpected BusinessDesk executable name')
    return str(stable), _parts(current) != _parts(stable)

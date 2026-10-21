"""Helpers for updater status and confirming that an updated app is running.

Everything here uses only the standard library so it also works in frozen builds.
"""
import json
import os
from pathlib import Path

READY_ENV = 'BUSINESSDESK_UPDATE_READY_FILE'
STATUS_NAME = 'install_status.json'


def read_status(data_dir):
    """Read installer status; corrupted/stale status does not prevent app login."""
    path = Path(data_dir) / 'updates' / STATUS_NAME
    try:
        if path.stat().st_size > 16000:
            return None
        obj = json.loads(path.read_text(encoding='utf-8-sig'))
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def signal_ready(data_dir, version, executable_path):
    """A process-start handshake: only write inside our app update directory."""
    marker = os.environ.get(READY_ENV, '').strip()
    if not marker:
        return False
    try:
        base = (Path(data_dir) / 'updates').resolve()
        target = Path(marker).resolve()
        if target.parent != base or not target.name.startswith('ready_') or target.suffix != '.json':
            return False
        payload = {'version': str(version), 'exe': str(executable_path), 'pid': os.getpid()}
        with target.open('x', encoding='utf-8') as stream:
            json.dump(payload, stream)
        return True
    except (OSError, ValueError, TypeError):
        return False

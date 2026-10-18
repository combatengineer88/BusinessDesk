"""BusinessDesk Windows entry point with visible/logged startup failures."""
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def start():
    try:
        if '--smoke-test' in sys.argv:
            # GitHub's Windows runner executes this compiled EXE before release.
            from core_v1 import connect
            from businessdesk import schema
            conn = connect()
            try:
                schema(conn)
                if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Smoke-test database integrity check failed')
            finally:
                conn.close()
            return
        from businessdesk import BusinessDesk
        BusinessDesk().run()
    except Exception:
        error = traceback.format_exc()
        data = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'BusinessDesk' / 'updates'
        data.mkdir(parents=True, exist_ok=True)
        path = data / 'startup_errors.log'
        with path.open('a', encoding='utf-8') as log:
            log.write(f'\n--- Startup failed {datetime.now().isoformat(timespec="seconds")} ---\n{error}\n')
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f'BusinessDesk failed to start.\n\nDetails saved to:\n{path}', 'BusinessDesk startup error', 0x10)
        except Exception:
            print(error, file=sys.stderr)
        raise SystemExit(1)

if __name__ == '__main__':
    start()

"""Offline, single-use account recovery tokens for PhoenixLedger.

Recovery tokens are secret, never stored in plaintext, and replace only a login
password. Other business data is never changed. Requires an existing user account.
"""
import base64
import datetime
import secrets
import sqlite3
from pathlib import Path

ITERATIONS = 260_000


def normalize_code(code):
    return ''.join(ch for ch in str(code or '').upper() if ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')


def create_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS account_recovery (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        secret_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')
    db.commit()


def generate_code(db, user_id):
    """Return a recovery code once. Admin/user must already be authenticated."""
    from core_v1 import hashed
    code=base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')
    normalized=normalize_code(code)
    formatted='-'.join(normalized[i:i+5] for i in range(0,len(normalized),5))
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db:
        if not db.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone():
            raise ValueError('Account does not exist.')
        db.execute('INSERT OR REPLACE INTO account_recovery(user_id,secret_hash,created_at) VALUES(?,?,?)',
                   (user_id,hashed(normalized),now))
    return formatted


def has_code(db, user_id):
    return bool(db.execute('SELECT 1 FROM account_recovery WHERE user_id=?',(user_id,)).fetchone())


def lookup_by_code(db, code):
    """Return (user_id, username) for a valid token; otherwise None."""
    from core_v1 import verify
    normalized=normalize_code(code)
    if len(normalized)<25:
        return None
    rows=db.execute('''SELECT u.id,u.username,r.secret_hash
        FROM account_recovery r JOIN users u ON u.id=r.user_id''').fetchall()
    for user_id,username,token_hash in rows:
        if verify(normalized,token_hash):
            return int(user_id),str(username)
    return None


def backup_database(db, data_folder):
    """Create a consistent SQLite backup before modifying credentials."""
    directory=Path(data_folder)/'recovery_backups'
    directory.mkdir(parents=True, exist_ok=True)
    timestamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    destination=directory/f'before_password_reset_{timestamp}.db'
    with sqlite3.connect(str(destination)) as snapshot:
        db.backup(snapshot)
        status=snapshot.execute('PRAGMA integrity_check').fetchone()[0]
        if status!='ok':
            raise RuntimeError('Backup failed SQLite integrity check.')
    return destination


def reset_with_code(db, code, new_password, data_folder):
    """Consume one token and change its owning user's password only."""
    from core_v1 import hashed
    if len(new_password)<10:
        raise ValueError('New password must contain at least 10 characters.')
    candidate=lookup_by_code(db,code)
    if not candidate:
        raise ValueError('Invalid or already-used recovery code.')
    user_id,username=candidate
    backup=backup_database(db,data_folder)
    with db:
        # Re-check before use and ensure one-time token is consumed.
        current=lookup_by_code(db,code)
        if not current or current[0]!=user_id:
            raise ValueError('Recovery code was already used.')
        db.execute('UPDATE users SET password=? WHERE id=?',(hashed(new_password),user_id))
        db.execute('DELETE FROM account_recovery WHERE user_id=?',(user_id,))
    return username,backup

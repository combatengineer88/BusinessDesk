"""Choose and validate the installable GitHub asset; no network access needed."""
import re
from pathlib import Path
from urllib.parse import urlsplit

SHA256 = re.compile(r'^[a-fA-F0-9]{64}$')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')

def select_update_asset(manifest, trusted_prefix=None):
    if not isinstance(manifest,dict):
        raise ValueError('Invalid GitHub release manifest.')
    version=str(manifest.get('version',''))
    if not VERSION.fullmatch(version):
        raise ValueError('Release manifest contains an invalid version.')
    installer=bool(manifest.get('installer_url'))
    url=str(manifest.get('installer_url') if installer else manifest.get('url',''))
    checksum=str(manifest.get('installer_sha256') if installer else manifest.get('sha256','')).lower()
    parsed=urlsplit(url)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('Release must be downloaded over HTTPS.')
    if not SHA256.fullmatch(checksum):
        raise ValueError('Missing or invalid release checksum.')
    filename=Path(parsed.path).name
    if installer:
        if filename != f'TDZIGNS_BusinessDesk_Setup_{version}.exe':
            raise ValueError('Incorrect BusinessDesk installer filename.')
    elif filename != f'TDZIGNS_BusinessDesk_{version}.zip':
        raise ValueError('Incorrect BusinessDesk update ZIP filename.')
    if trusted_prefix and not url.startswith(trusted_prefix.rstrip('/')+'/v'+version+'/'):
        raise ValueError('Release must come from the trusted BusinessDesk GitHub repository.')
    return version,url,checksum,('setup' if installer else 'zip')


def validate_setup_file(file):
    path=Path(file)
    if not path.is_file():raise FileNotFoundError('Windows Setup file not found.')
    if not re.fullmatch(r'TDZIGNS_BusinessDesk_Setup_\d+\.\d+\.\d+\.exe',path.name,re.I):
        raise ValueError('Choose a TDZIGNS_BusinessDesk_Setup_X.Y.Z.exe installer from GitHub Releases.')
    if not (1_000_000 < path.stat().st_size < 200_000_000):
        raise ValueError('Windows Setup file size is outside the expected range.')
    with path.open('rb') as stream:
        if stream.read(2)!=b'MZ':raise ValueError('Selected file is not a Windows executable.')
    return True

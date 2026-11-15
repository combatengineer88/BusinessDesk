"""Check that the selected release tag and PhoenixLedger source agree.

This prevents publishing a tag like v3.5.0 with code still marked 3.4.0.
Use before creating the GitHub tag: python release_preflight.py v3.6.0
GitHub Actions runs the same check against the checked-out tagged commit.
"""
import argparse
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent

def release_version():
    source=(HERE/'businessdesk.py').read_text(encoding='utf-8')
    matches=re.findall(r"^VERSION = '([0-9]+\.[0-9]+\.[0-9]+)'\s*$",source,re.M)
    if len(matches)!=1:
        raise ValueError('Expected exactly one VERSION = \'X.Y.Z\' in businessdesk.py')
    return matches[0]

def verify(expected_tag=None):
    version=release_version()
    if expected_tag and expected_tag!=f'v{version}':
        raise ValueError(
            f'Tag/source mismatch: tag {expected_tag!r}, but '
            f'PhoenixLedger_App/businessdesk.py says {version!r}. '
            'Upload the complete updated PhoenixLedger_App folder and the '
            'workflow to main, commit them, confirm the version in GitHub, '
            'and create a NEW release tag on that commit. Rerunning an old '
            'tag will not include newer commits.')
    setup=(HERE/'businessdesk.iss').read_text(encoding='utf-8')
    defaults=re.findall(r'^\s*#define BuildVersion "([0-9]+\.[0-9]+\.[0-9]+)"',setup,re.M)
    if defaults!=[version]:
        raise ValueError('Inno Setup default BuildVersion does not match businessdesk.py')
    packager=(HERE/'package_release.py').read_text(encoding='utf-8')
    if 'VERSION = match.group(1)' not in packager:
        raise ValueError('Release packager must derive version from businessdesk.py')
    print(f'PASS PhoenixLedger source version {version}, installer and package release aligned.')
    print(f'Tag: {expected_tag or "not yet set"}')
    return version

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag',nargs='?',help='Expected tag, e.g. v3.6.0')
    args=parser.parse_args()
    try:verify(args.tag)
    except (OSError,ValueError) as e:
        print('RELEASE PRECHECK FAILED:',e,file=sys.stderr)
        sys.exit(1)

"""One-time administrator setup; never build or run the application as root."""
import argparse
import os
from pathlib import Path
import platform
import pwd
import re
import subprocess
import sys


PACKAGES = ('git', 'ca-certificates', 'python3-venv', 'python3-dev',
            'build-essential', 'libhidapi-libusb0', 'fonts-dejavu-core',
            'libjpeg-dev', 'zlib1g-dev')


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True, help='Existing non-root account that will run the kiosk')
    args = parser.parse_args(argv)
    if platform.system() != 'Linux':
        parser.error('System setup requires Raspberry Pi OS/Debian Linux.')
    if os.geteuid() != 0:
        parser.error('Run this setup as root or from an administrator account using sudo.')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*\$?', args.user):
        parser.error('Invalid kiosk account name.')
    try:
        account = pwd.getpwnam(args.user)
    except KeyError:
        parser.error('The kiosk account must already exist; no account was created.')
    if account.pw_uid == 0:
        parser.error('The kiosk account must not be root.')
    rule = Path(__file__).resolve().parent / '60-foxoe-streamdeck.rules'
    if not rule.is_file():
        parser.error('The Stream Deck udev rules are missing from this source folder.')

    # All account/source validation precedes privileged mutations. Application
    # dependencies, Git releases, credentials and home directories stay user-owned.
    run('apt-get', 'update')
    run('apt-get', 'install', '-y', *PACKAGES)
    run('groupadd', '-f', 'plugdev')
    run('usermod', '-aG', 'plugdev', account.pw_name)
    run('install', '-m', '0644', rule, '/etc/udev/rules.d/60-foxoe-streamdeck.rules')
    run('udevadm', 'control', '--reload-rules')
    run('loginctl', 'enable-linger', account.pw_name)
    print(f'System setup complete for {account.pw_name}; no sudo access was granted.')
    print('Reboot once and reconnect the Stream Deck. Then log in directly as the kiosk user and run bash install.sh --channel beta.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError, KeyboardInterrupt) as error:
        print(f'FoxOE system setup failed: {error or "interrupted"}. Correct the problem and rerun setup.', file=sys.stderr)
        sys.exit(1)

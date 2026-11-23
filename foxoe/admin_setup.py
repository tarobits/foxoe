"""Opt-in network administration, configured by the kiosk user without sudo."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import tempfile

from .admin import password_digest


def load_settings(directory):
    path = directory / 'admin/config.json'
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if value.get('enabled') is False:
        return None
    if (value.get('enabled') is not True or type(value.get('port')) is not int or not 1024 <= value['port'] <= 65535
            or value['port'] in (8765, 8766) or not re.fullmatch('[a-f0-9]{32}', value.get('salt', ''))
            or not re.fullmatch('[a-f0-9]{64}', value.get('passwordHash', ''))):
        raise ValueError('Invalid administrator configuration')
    return value


def configure(directory, password, hostname, port=8767):
    if not 12 <= len(password) <= 1024:
        raise ValueError('Use an administrator password of 12–1024 characters.')
    try:
        san = 'IP:' + str(ipaddress.ip_address(hostname))
    except ValueError:
        if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?', hostname):
            raise ValueError('Use a hostname or IP address, without a URL or port.') from None
        san = 'DNS:' + hostname
    if not 1024 <= port <= 65535 or port in (8765, 8766):
        raise ValueError('Choose an unused port from 1024–65535 other than 8765 or 8766.')
    if not shutil.which('openssl'):
        raise ValueError('OpenSSL is required to generate the HTTPS certificate.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    admin = directory / 'admin'
    admin.mkdir(exist_ok=True, mode=0o700)
    # Keep a stable certificate across password changes and normal updates.
    if not (admin / 'certificate.pem').exists() or not (admin / 'private-key.pem').exists():
        with tempfile.TemporaryDirectory(prefix='tls-', dir=admin) as temp:
            stage = Path(temp)
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '825',
                            '-keyout', str(stage / 'private-key.pem'), '-out', str(stage / 'certificate.pem'),
                            '-subj', '/CN=FoxOE', '-addext', f'subjectAltName={san},DNS:localhost,IP:127.0.0.1'],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            for name in ('private-key.pem', 'certificate.pem'):
                (stage / name).chmod(0o600)
                os.replace(stage / name, admin / name)
    salt = secrets.token_hex(16)
    settings = {'enabled': True, 'port': port, 'salt': salt, 'passwordHash': password_digest(password, salt)}
    fd, temp = tempfile.mkstemp(prefix='config-', dir=admin)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(settings, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, admin / 'config.json')
    finally:
        Path(temp).unlink(missing_ok=True)
    return settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path.home() / '.local/share/foxoe/data')
    parser.add_argument('--hostname', default=socket.gethostname())
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--disable', action='store_true', help='Disable network administration; restart the user service afterward')
    args = parser.parse_args()
    if args.disable:
        path = args.data_dir / 'admin/config.json'
        if path.exists():
            value = json.loads(path.read_text())
            value['enabled'] = False
            temporary = path.with_suffix('.next')
            with open(temporary, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
                json.dump(value, output)
            os.replace(temporary, path)
        print('Network administration disabled. Restart the user service: systemctl --user restart foxoe')
        return
    password = getpass.getpass('New administrator password (at least 12 characters): ')
    if password != getpass.getpass('Repeat administrator password: '):
        parser.error('Passwords do not match; nothing was changed.')
    try:
        configure(args.data_dir, password, args.hostname, args.port)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print(f'Network administration configured at https://{args.hostname}:{args.port}/')
    print('Restart the user service: systemctl --user restart foxoe')
    print('The certificate is self-signed; your browser will show a warning.')


if __name__ == '__main__':
    main()

"""User-owned Git releases; privileged prerequisites are prepared separately.

Builds never modify the active release. A durable activation journal allows the
next invocation to recover an interrupted switch, including the old data format.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import errno
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import uuid


REPOSITORY = 'https://github.com/tarobits/foxoe.git'
NODE_VERSION = '22.23.4'
UNIT = 'foxoe.service'


class DeploymentError(Exception):
    pass


class NoRelease(DeploymentError):
    pass


def semver(tag):
    match = re.fullmatch(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
                        r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
                        r'(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?', tag) if isinstance(tag, str) else None
    if not match:
        raise DeploymentError('Release tags must use semantic versions, such as v1.0.0 or v1.1.0-beta.1.')
    identifiers = match[4].split('.') if match[4] else []
    if any(part.isdigit() and len(part) > 1 and part.startswith('0') for part in identifiers):
        raise DeploymentError('Numeric prerelease identifiers cannot contain leading zeroes.')
    # Numeric prerelease identifiers sort before text; a final release sorts
    # above every prerelease of that version. Build metadata has no precedence.
    return (*map(int, match.group(1, 2, 3)), 0 if identifiers else 1,
            tuple((0, int(part)) if part.isdigit() else (1, part) for part in identifiers))


def published_release(repository, version=None, channel='stable'):
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?', repository)
    if not match:
        raise DeploymentError('Use an HTTPS github.com repository URL without credentials or query parameters.')
    if version:
        semver(version)
    if channel not in ('stable', 'beta'):
        raise DeploymentError('Unknown release channel.')
    candidates = []
    for page in range(1, 101):
        endpoint = '/tags/' + version if version else f'?per_page=100&page={page}'
        request = urllib.request.Request(f'https://api.github.com/repos/{match[1]}/{match[2]}/releases{endpoint}',
            headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'FoxOE-installer',
                     'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise DeploymentError('No published GitHub release found. Publish a release before installing.') from None
            raise DeploymentError(f'GitHub release lookup failed (HTTP {error.code}); installation was not changed.') from None
        releases = [result] if version else result
        if not isinstance(releases, list):
            raise DeploymentError('Invalid GitHub release response.')
        for release in releases:
            if not isinstance(release, dict):
                raise DeploymentError('Invalid GitHub release response.')
            if version and release.get('tag_name') != version:
                raise DeploymentError('GitHub returned a different version than requested.')
            try:
                order = semver(release.get('tag_name'))
            except DeploymentError:
                if version:
                    raise
                continue
            if release.get('draft') is not False or not release.get('published_at'):
                continue
            if not isinstance(release.get('prerelease'), bool):
                continue
            if channel == 'stable' and (release['prerelease'] or order[3] == 0):
                continue
            candidates.append(release)
        if version or len(releases) < 100:
            break
    else:
        raise DeploymentError('Too many release pages; select a version explicitly with --version.')
    if not candidates:
        raise NoRelease(f'No published release is available for the {channel} channel.')
    return max(candidates, key=lambda item: semver(item['tag_name']))


def newer_release(current, candidate):
    installed, available = semver(current), semver(candidate)
    if available < installed:
        raise DeploymentError(f'Refusing downgrade from {current} to {candidate}.')
    return available > installed


def validate_release(release, tag):
    version = tag[1:]
    python = tomllib.loads((release / 'pyproject.toml').read_text())
    javascript = json.loads((release / 'package.json').read_text())
    # npm uses SemVer; Python uses PEP 440. A prerelease may use its base Python
    # version, or conventional a/b/rc notation, while npm/tag identify it exactly.
    order = semver(tag)
    base = '.'.join(map(str, order[:3]))
    python_versions = {version.split('+')[0], base}
    conventional = re.fullmatch(r'\d+\.\d+\.\d+-(alpha|beta|rc)\.(\d+)(?:\+.*)?', version)
    if conventional:
        python_versions.add(base + {'alpha': 'a', 'beta': 'b', 'rc': 'rc'}[conventional[1]] + conventional[2])
    if python.get('project', {}).get('version') not in python_versions or javascript.get('version') != version:
        raise DeploymentError('Release tag and Python/JavaScript package versions do not match.')
    changelog = (release / 'CHANGELOG.md').read_text()
    if not re.search(r'^## \[' + re.escape(version) + r'\] - \d{4}-\d{2}-\d{2}\s*$', changelog, re.MULTILINE):
        raise DeploymentError('Release is missing its dated CHANGELOG.md entry.')


def run(*args, cwd=None, env=None, capture=False):
    result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=env,
                            check=True, text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with open(temporary, 'w', encoding='utf-8') as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


@contextmanager
def locked(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(root / 'deploy.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeploymentError('Another FoxOE install or update is running.') from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def systemctl(*args, capture=False):
    return run('systemctl', '--user', *args, capture=capture)


def checked_path(value):
    path = Path(value).expanduser().absolute()
    # Keep generated systemd commands unambiguous, including specifier expansion.
    if not re.fullmatch(r'[A-Za-z0-9/_. -]+', str(path)):
        raise DeploymentError('Installation paths may contain letters, digits, spaces, /, _, . and - only.')
    return path


def service_text(root):
    return f'''# Managed by FoxOE installer. Keep custom settings in foxoe.service.d/.
[Unit]
Description=Fox Operating Environment
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={root}/current
ExecStart="{root}/current/.venv/bin/python" -m foxoe --data-dir "{root}/data"
EnvironmentFile=-{root}/service.env
StandardOutput=append:{root}/logs/service.log
StandardError=inherit
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
'''


def prerequisites():
    for command in ('git', 'systemctl'):
        if not shutil.which(command):
            raise DeploymentError(f'Missing prerequisite: {command}. Ask an administrator to run setup-system.sh --user <kiosk-user>.')
    try:
        systemctl('show-environment', capture=True)
    except subprocess.CalledProcessError:
        raise DeploymentError('The user service manager is unavailable. Log in directly as the kiosk user after administrator setup.') from None


def check_install_port():
    """Fail before downloading/building; never stop an unidentified listener."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', 8765))
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                raise DeploymentError("Port 127.0.0.1:8765 is already in use. Identify the listener with ss -ltnp 'sport = :8765' before retrying; no service was stopped.") from None
            raise


def build_environment(root):
    """Use a supported Node, or install a checksum-verified official user copy."""
    env = os.environ.copy()
    node_dir = root / 'tools' / f'node-{NODE_VERSION}'
    env['PATH'] = str(node_dir / 'bin') + os.pathsep + env.get('PATH', '')
    try:
        version = run('node', '--version', env=env, capture=True).lstrip('v').split('.')
        if tuple(map(int, version)) >= (22, 18, 0):
            run('npm', '--version', env=env, capture=True)
            return env
    except (OSError, ValueError, subprocess.CalledProcessError):
        pass
    architecture = {'aarch64': 'arm64', 'arm64': 'arm64', 'armv7l': 'armv7l',
                    'x86_64': 'x64'}.get(platform.machine())
    if not architecture:
        raise DeploymentError('Install Node.js 22.18+ and npm for this architecture first.')
    name = f'node-v{NODE_VERSION}-linux-{architecture}.tar.xz'
    base = f'https://nodejs.org/dist/v{NODE_VERSION}/'
    node_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=node_dir.parent) as work:
        work = Path(work)
        with urllib.request.urlopen(base + 'SHASUMS256.txt', timeout=60) as response:
            checksums = dict(line.split()[::-1] for line in response.read().decode().splitlines())
        archive = work / name
        with urllib.request.urlopen(base + name, timeout=60) as response, open(archive, 'wb') as output:
            shutil.copyfileobj(response, output)
        with open(archive, 'rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if checksums.get(name) != digest:
            raise DeploymentError('Node download checksum mismatch; nothing installed.')
        with tarfile.open(archive) as bundle:
            # Python 3.11 security backports provide data_filter. Never fall back
            # to unrestricted extraction on older/unpatched runtimes.
            if not hasattr(tarfile, 'data_filter'):
                raise DeploymentError('Update Python 3.11 security packages before installing Node.')
            bundle.extractall(work, filter='data')
        extracted = work / name.removesuffix('.tar.xz')
        if node_dir.exists():
            raise DeploymentError(f'Broken managed Node installation: {node_dir}. Repair it before retrying.')
        extracted.rename(node_dir)
    return env


def prepare_release(root, repository, tag, env):
    releases = root / 'releases'
    releases.mkdir(exist_ok=True)
    release = releases / uuid.uuid4().hex
    try:
        # No checkout is reset or pulled in place. The selected remote is trusted
        # application code; dependency/build scripts run as the invoking user.
        semver(tag)
        run('git', 'init', '--quiet', release)
        run('git', 'remote', 'add', 'origin', repository, cwd=release)
        # Fetch the explicit tag ref; a branch named v1.0.0 cannot shadow it.
        run('git', 'fetch', '--depth', '1', 'origin', 'refs/tags/' + tag, cwd=release)
        run('git', 'checkout', '--detach', 'FETCH_HEAD', cwd=release)
        commit = run('git', 'rev-parse', 'HEAD', cwd=release, capture=True)
        for name in ('pyproject.toml', 'package-lock.json', 'foxoe/server.py', 'deploy/manage.py'):
            if not (release / name).is_file():
                raise DeploymentError(f'Repository is empty or missing required file: {name}.')
        validate_release(release, tag)
        run(sys.executable, '-m', 'venv', release / '.venv')
        run(release / '.venv/bin/python', '-m', 'pip', 'install', '-e', '.[device]', cwd=release)
        run('npm', 'ci', '--include=dev', '--no-audit', '--no-fund', cwd=release, env=env)
        run('npm', 'run', 'build', cwd=release, env=env)
        if not (release / 'dist/index.html').is_file():
            raise DeploymentError('Build did not produce the dashboard.')
        return release, {'repository': repository, 'version': tag, 'commit': commit}
    except BaseException:
        if release.exists():
            shutil.rmtree(release)
        raise


def switch(root, target):
    temporary = root / 'current.next'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, root / 'current')


def healthy(root, timeout=30):
    """Require both systemd's live process and this release's health identity."""
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    expected = str((root / 'current').resolve())
    last_problem = 'the service has no running process'
    while time.monotonic() < deadline:
        try:
            pid = systemctl('show', UNIT, '--property=MainPID', '--value', capture=True)
            last_problem = 'the service has no running process'
            if int(pid) > 0:
                with opener.open('http://127.0.0.1:8765/api/health', timeout=2) as response:
                    status = json.load(response)
                if not isinstance(status, dict):
                    last_problem = 'the health endpoint returned an invalid response'
                elif status.get('pid') == int(pid) and status.get('release') == expected:
                    with opener.open('http://127.0.0.1:8765/', timeout=2) as response:
                        if response.status == 200:
                            return
                else:
                    last_problem = 'port 8765 responded from a different process or release'
        except urllib.error.HTTPError as error:
            last_problem = f'the HTTP check returned status {error.code}'
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            # Response bodies/exception text may contain unrelated applications'
            # data. Report only the failure category and the private log path.
            last_problem = f'the health check failed ({type(error).__name__})'
        time.sleep(.5)
    raise DeploymentError(f'FoxOE did not become healthy within {timeout:g} seconds: {last_problem}. Service output: {root}/logs/service.log')


def recover(root):
    journal_path = root / 'pending.json'
    if not journal_path.exists():
        return
    journal = json.loads(journal_path.read_text())
    systemctl('stop', UNIT)
    backup = Path(journal['backup'])
    # Keep the backup and failed data for manual inspection; never restore into
    # an existing database directory where WAL files could survive.
    if journal['had_data']:
        restored = Path(tempfile.mkdtemp(prefix='restore-', dir=root))
        shutil.copytree(backup / 'data', restored, dirs_exist_ok=True)
    else:
        restored = None
    data = root / 'data'
    if data.exists():
        data.rename(root / ('failed-data-' + uuid.uuid4().hex))
    if restored:
        restored.rename(data)
    if journal['previous']:
        switch(root, journal['previous'])
        systemctl('start', UNIT)
        healthy(root)
    else:
        (root / 'current').unlink(missing_ok=True)
    if journal['config'] is not None:
        atomic_json(root / 'installation.json', journal['config'])
    else:
        (root / 'installation.json').unlink(missing_ok=True)
    journal_path.unlink()


def activate(root, release, config):
    previous = (root / 'current').resolve() if (root / 'current').is_symlink() else None
    config_path = root / 'installation.json'
    old_config = json.loads(config_path.read_text()) if config_path.exists() else None
    backup = root / 'backups' / uuid.uuid4().hex
    backup.mkdir(parents=True)
    # Fresh installs have no previous service to stop. Updates must still fail
    # closed if stopping the running service fails, before touching its data.
    if previous:
        systemctl('stop', UNIT)
    try:
        had_data = (root / 'data').exists()
        if had_data:
            shutil.copytree(root / 'data', backup / 'data')
        atomic_json(root / 'pending.json', {'previous': str(previous) if previous else None,
                    'backup': str(backup), 'had_data': had_data, 'config': old_config})
    except BaseException:
        if previous:
            systemctl('start', UNIT)
        raise
    try:
        switch(root, release)
        systemctl('start', UNIT)
        healthy(root)
        atomic_json(config_path, config)
        (root / 'pending.json').unlink()
    except BaseException:
        recover(root)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'update'))
    parser.add_argument('--directory', default=str(Path.home() / '.local/share/foxoe'))
    parser.add_argument('--repository', default=REPOSITORY, help='Install source; updates use the saved repository')
    parser.add_argument('--version', help='Published tag, e.g. v1.0.0; default is highest eligible semantic version')
    parser.add_argument('--channel', choices=('stable', 'beta'), help='Remembered update channel; defaults to stable on install')
    parser.add_argument('--skip-system-deps', action='store_true', help='Compatibility option; system setup is always separate now')
    parser.add_argument('--recover', action='store_true', help='Restore an interrupted activation without fetching an update')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11) or platform.system() != 'Linux':
        parser.error('Use Raspberry Pi OS/Debian Linux with Python 3.11 or newer.')
    if os.geteuid() == 0:
        parser.error('Run as the kiosk user, without sudo. Administrators use setup-system.sh for system setup.')
    if args.action == 'update' and args.repository != REPOSITORY:
        parser.error('Updates use the saved repository; source changes must be explicit in installation.json.')
    root = checked_path(args.directory).resolve()
    checked_path(root)
    unit = Path.home() / '.config/systemd/user' / UNIT
    os.umask(0o077)
    with locked(root):
        if (root / 'pending.json').exists():
            print('Recovering the interrupted activation…', flush=True)
            recover(root)
            if not (root / 'installation.json').exists() and unit.exists() and unit.read_text() == service_text(root):
                unit.unlink()
                systemctl('daemon-reload')
        if args.recover:
            print('Recovery complete; no update fetched.')
            return
        installed = (root / 'installation.json').exists()
        if not installed and ((root / 'current').exists() or (root / 'current').is_symlink() or (root / 'data').exists()):
            raise DeploymentError('Unmanaged data or release already exists in this directory. Choose an empty runtime directory.')
        if args.action == 'install' and (installed or unit.exists()):
            raise DeploymentError('FoxOE is already installed or foxoe.service exists. Use update.sh; no existing unit was changed.')
        if args.action == 'update' and not installed:
            raise DeploymentError('No managed installation found. Run install.sh first.')
        if args.action == 'update' and (not (root / 'current').is_symlink() or not unit.exists()):
            raise DeploymentError('Managed release or service is missing. Repair the installation before updating.')
        if not installed:
            check_install_port()
        config = json.loads((root / 'installation.json').read_text()) if installed else {'repository': args.repository}
        channel = args.channel or config.get('channel', 'stable')
        try:
            selected = published_release(config['repository'], args.version, channel)
        except NoRelease:
            if not installed or args.version:
                raise
            atomic_json(root / 'installation.json', {**config, 'channel': channel})
            print(f'No release available for {channel}; keeping {config["version"]}. Channel saved.')
            return
        if installed and not args.version and semver(selected['tag_name']) < semver(config['version']):
            atomic_json(root / 'installation.json', {**config, 'channel': channel})
            print(f'Channel saved: {channel}. Keeping {config["version"]} until a newer eligible release is published.')
            return
        if installed and not newer_release(config['version'], selected['tag_name']):
            if channel != config.get('channel', 'stable'):
                atomic_json(root / 'installation.json', {**config, 'channel': channel})
            print(f'FoxOE {config["version"]} is already installed; update channel: {channel}.')
            return
        print(f'Preparing FoxOE {selected["tag_name"]}…', flush=True)
        prerequisites()
        env = build_environment(root)
        release, config = prepare_release(root, config['repository'], selected['tag_name'], env)
        config['channel'] = channel
        created_unit = False
        try:
            if not installed:
                logs = root / 'logs'
                logs.mkdir(exist_ok=True, mode=0o700)
                (logs / 'service.log').touch(mode=0o600, exist_ok=True)
                unit.parent.mkdir(parents=True, exist_ok=True)
                with open(unit, 'x') as output:
                    created_unit = True
                    output.write(service_text(root))
                systemctl('daemon-reload')
            activate(root, release, config)
            systemctl('enable', UNIT)
        except BaseException:
            if created_unit and not (root / 'pending.json').exists() and not (root / 'installation.json').exists():
                unit.unlink(missing_ok=True)
                systemctl('daemon-reload')
            raise
    print(f'FoxOE {config["version"]} ready at http://127.0.0.1:8765/ (commit {config["commit"][:12]}).')
    print(f'Changelog: {root}/current/CHANGELOG.md')
    print(f'Extension directory: {root}/current/extension')


def cancel_deployment(*_):
    raise KeyboardInterrupt()


if __name__ == '__main__':
    # A normal cancellation uses the same rollback/cleanup path as other failures.
    signal.signal(signal.SIGTERM, cancel_deployment)
    try:
        main()
    except (DeploymentError, OSError, ValueError, subprocess.CalledProcessError, KeyboardInterrupt) as error:
        print(f'FoxOE deployment failed: {error or "interrupted"}', file=sys.stderr)
        sys.exit(1)

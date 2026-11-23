"""Exercise deployment failure boundaries without root, downloads or systemd."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import io
import urllib.error

import pytest

spec = importlib.util.spec_from_file_location('foxoe_deploy', Path(__file__).parents[1] / 'deploy/manage.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / 'install'
    old = root / 'releases/old'
    new = root / 'releases/new'
    old.mkdir(parents=True)
    new.mkdir()
    (root / 'data').mkdir()
    (root / 'data/config').write_text('previous data')
    (root / 'data/bridge-token').write_text('test placeholder, not a credential')
    deploy.switch(root, old)
    config = {'repository': deploy.REPOSITORY, 'version': 'v1.0.0', 'commit': 'old'}
    deploy.atomic_json(root / 'installation.json', config)
    calls = []
    monkeypatch.setattr(deploy, 'systemctl', lambda *args, **kw: calls.append(args))
    monkeypatch.setattr(deploy, 'healthy', lambda *args: None)
    return root, old, new, config, calls


def test_success_preserves_data_and_credentials_and_records_revision(installation):
    root, old, new, config, calls = installation
    deploy.activate(root, new, {**config, 'commit': 'new'})
    assert (root / 'current').resolve() == new
    assert (root / 'data/config').read_text() == 'previous data'
    assert (root / 'data/bridge-token').read_text() == 'test placeholder, not a credential'
    assert json.loads((root / 'installation.json').read_text())['commit'] == 'new'
    assert not (root / 'pending.json').exists()
    assert calls == [('stop', deploy.UNIT), ('start', deploy.UNIT)]
    assert old.is_dir()


@pytest.mark.parametrize('failure', [RuntimeError('bad service'), KeyboardInterrupt()])
def test_failed_activation_restores_data_release_and_allows_next_update(installation, monkeypatch, failure):
    root, old, new, config, calls = installation
    def probe(*args):
        if (root / 'current').resolve() == new:
            (root / 'data/config').write_text('new incompatible format')
            (root / 'data/foxoe.sqlite-wal').write_text('must not survive rollback')
            raise failure
    monkeypatch.setattr(deploy, 'healthy', probe)
    with pytest.raises(type(failure)):
        deploy.activate(root, new, {**config, 'commit': 'new'})
    assert (root / 'current').resolve() == old
    assert (root / 'data/config').read_text() == 'previous data'
    assert not (root / 'data/foxoe.sqlite-wal').exists()
    assert json.loads((root / 'installation.json').read_text()) == config
    assert not (root / 'pending.json').exists()
    assert list(root.glob('failed-data-*'))
    monkeypatch.setattr(deploy, 'healthy', lambda *_: None)
    deploy.activate(root, new, {**config, 'commit': 'new'})
    assert (root / 'current').resolve() == new


def test_backup_failure_keeps_old_release_and_restarts_it(installation, monkeypatch):
    root, old, new, config, calls = installation
    monkeypatch.setattr(deploy.shutil, 'copytree', lambda *a, **kw: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError, match='disk full'):
        deploy.activate(root, new, config)
    assert (root / 'current').resolve() == old
    assert (root / 'data/config').read_text() == 'previous data'
    assert calls[-1] == ('start', deploy.UNIT)


def test_interrupted_rollback_retains_journal_for_retry(installation, monkeypatch):
    root, old, new, config, _ = installation
    monkeypatch.setattr(deploy, 'healthy', lambda *_: (_ for _ in ()).throw(OSError('still unavailable')))
    with pytest.raises(OSError):
        deploy.activate(root, new, {**config, 'commit': 'new'})
    assert (root / 'pending.json').exists()
    monkeypatch.setattr(deploy, 'healthy', lambda *_: None)
    deploy.recover(root)
    assert (root / 'current').resolve() == old
    assert (root / 'data/config').read_text() == 'previous data'
    assert not (root / 'pending.json').exists()


def test_failed_first_start_retains_generated_data_but_removes_current(tmp_path, monkeypatch):
    release = tmp_path / 'releases/new'
    release.mkdir(parents=True)
    monkeypatch.setattr(deploy, 'systemctl', lambda *a: None)
    def fail(*args):
        (tmp_path / 'data').mkdir()
        (tmp_path / 'data/config').write_text('partially created')
        raise RuntimeError('startup failed')
    monkeypatch.setattr(deploy, 'healthy', fail)
    with pytest.raises(RuntimeError):
        deploy.activate(tmp_path, release, {})
    assert not (tmp_path / 'current').is_symlink()
    assert not (tmp_path / 'installation.json').exists()
    assert not (tmp_path / 'data').exists()
    assert list(tmp_path.glob('failed-data-*'))


def test_lock_rejects_concurrent_deployment_and_releases_after_exception(tmp_path):
    with pytest.raises(RuntimeError):
        with deploy.locked(tmp_path):
            with pytest.raises(deploy.DeploymentError, match='Another'):
                with deploy.locked(tmp_path):
                    pytest.fail('Concurrent deployment entered')
            raise RuntimeError('cancelled')
    with deploy.locked(tmp_path):
        pass


@pytest.mark.parametrize('fail_on', ['fetch', 'ci', 'build'])
def test_build_failures_never_touch_running_release(installation, monkeypatch, fail_on):
    root, old, _, _, calls = installation
    def command(*args, **kwargs):
        if fail_on in args:
            raise subprocess.CalledProcessError(1, 'test command')
        if args[:2] == ('git', 'init'):
            target = Path(args[-1])
            for filename in ('pyproject.toml', 'package-lock.json', 'foxoe/server.py', 'deploy/manage.py'):
                file = target / filename
                file.parent.mkdir(parents=True, exist_ok=True)
                file.touch()
        return 'abc'
    monkeypatch.setattr(deploy, 'run', command)
    monkeypatch.setattr(deploy, 'validate_release', lambda *_: None)
    before = set((root / 'releases').iterdir())
    with pytest.raises(subprocess.CalledProcessError):
        deploy.prepare_release(root, deploy.REPOSITORY, 'v1.0.0', {})
    assert set((root / 'releases').iterdir()) == before
    assert (root / 'current').resolve() == old
    assert not calls


def test_service_paths_are_quoted_and_injection_is_rejected(tmp_path):
    root = deploy.checked_path(str(tmp_path / 'with spaces'))
    unit = deploy.service_text(root)
    assert f'WorkingDirectory="{root}/current"' in unit
    assert f'--data-dir "{root}/data"' in unit
    for suffix in ('bad\nExecStart=evil', 'bad%h', 'bad${HOME}', 'bad"'):
        with pytest.raises(deploy.DeploymentError):
            deploy.checked_path(str(tmp_path / suffix))


def test_health_rejects_another_process_on_the_same_port(tmp_path, monkeypatch):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return json.dumps({'pid': 999, 'release': str(tmp_path / 'current')}).encode()
    class Client:
        def open(self, *a, **kw): return Response()
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(deploy.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(deploy.time, 'sleep', lambda *_: None)
    monkeypatch.setattr(deploy, 'systemctl', lambda *a, **kw: '123')
    monkeypatch.setattr(deploy.urllib.request, 'build_opener', lambda *_: Client())
    with pytest.raises(deploy.DeploymentError, match='healthy'):
        deploy.healthy(tmp_path, timeout=1)


def test_install_rejects_existing_unit_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(deploy.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(deploy.os, 'geteuid', lambda: 1000)
    unit = tmp_path / '.config/systemd/user/foxoe.service'
    unit.parent.mkdir(parents=True)
    unit.write_text('unmanaged unit')
    with pytest.raises(deploy.DeploymentError, match='already installed'):
        deploy.main(['install', '--directory', str(tmp_path / 'foxoe')])
    assert unit.read_text() == 'unmanaged unit'


def release(tag, **kwargs):
    return {'tag_name': tag, 'draft': False, 'prerelease': '-' in tag,
            'published_at': '2026-01-01T00:00:00Z', **kwargs}


def mock_github(monkeypatch, pages):
    requests = []
    def fetch(request, **kwargs):
        requests.append(request.full_url)
        return io.BytesIO(json.dumps(pages[len(requests) - 1]).encode())
    monkeypatch.setattr(deploy.urllib.request, 'urlopen', fetch)
    return requests


def test_channels_use_semantic_order_ignore_drafts_and_do_not_depend_on_release_dates(monkeypatch):
    entries = [release('v1.10.0'), release('v1.9.0'), release('v2.0.0-beta.2'),
               release('v2.0.0-beta.10'), release('v99.0.0', draft=True),
               release('v88.0.0', published_at=None), release('not-semver'),
               release('v77.0.0', prerelease=False, draft=0),
               release('v3.0.0-beta.1', prerelease=False)]
    # A prerelease tag is never stable, even if GitHub's checkbox was missed.
    mock_github(monkeypatch, [entries, entries])
    assert deploy.published_release(deploy.REPOSITORY)['tag_name'] == 'v1.10.0'
    assert deploy.published_release(deploy.REPOSITORY, channel='beta')['tag_name'] == 'v3.0.0-beta.1'


def test_beta_promotes_to_final_and_paginates(monkeypatch):
    requests = mock_github(monkeypatch, [[release('v1.0.0-beta.10')] * 100, [release('v1.0.0')]])
    assert deploy.published_release(deploy.REPOSITORY, channel='beta')['tag_name'] == 'v1.0.0'
    assert requests[-1].endswith('page=2')


@pytest.mark.parametrize('tag', ['1.0.0', 'v01.0.0', 'v1.0', 'v1.0.0-beta.01', 'v1.0.0-', 'v1.0.0;evil', None])
def test_invalid_semver_tags_rejected(tag):
    with pytest.raises(deploy.DeploymentError):
        deploy.semver(tag)


def test_semver_numeric_identifiers_metadata_and_final_order():
    ordered = ['v1.0.0-alpha', 'v1.0.0-alpha.1', 'v1.0.0-alpha.beta', 'v1.0.0-beta',
               'v1.0.0-beta.2', 'v1.0.0-beta.11', 'v1.0.0-rc.1', 'v1.0.0', 'v1.0.1']
    assert sorted(reversed(ordered), key=deploy.semver) == ordered
    assert deploy.semver('v1.0.0+build.2') == deploy.semver('v1.0.0+build.99')
    assert not deploy.newer_release('v1.0.0', 'v1.0.0')
    with pytest.raises(deploy.DeploymentError, match='downgrade'):
        deploy.newer_release('v1.0.0', 'v1.0.0-rc.1')


def test_requested_prerelease_requires_beta_and_exact_published_tag(monkeypatch):
    mock_github(monkeypatch, [release('v1.1.0-beta.1'), release('v1.1.0-beta.1'), release('v9.0.0')])
    with pytest.raises(deploy.DeploymentError, match='stable channel'):
        deploy.published_release(deploy.REPOSITORY, 'v1.1.0-beta.1')
    assert deploy.published_release(deploy.REPOSITORY, 'v1.1.0-beta.1', 'beta')['tag_name'] == 'v1.1.0-beta.1'
    with pytest.raises(deploy.DeploymentError, match='different version'):
        deploy.published_release(deploy.REPOSITORY, 'v1.0.0')


@pytest.mark.parametrize('status', [403, 404, 429, 500])
def test_github_errors_fail_before_deployment(monkeypatch, status):
    def fail(*a, **kw):
        raise urllib.error.HTTPError('https://api.github.com', status, 'failure', {}, None)
    monkeypatch.setattr(deploy.urllib.request, 'urlopen', fail)
    with pytest.raises(deploy.DeploymentError):
        deploy.published_release(deploy.REPOSITORY)


@pytest.mark.parametrize('url', ['http://github.com/tarobits/foxoe', 'https://token@github.com/tarobits/foxoe',
                               'https://github.com.attacker.test/tarobits/foxoe', 'file:///tmp/repo'])
def test_repository_url_rejects_credentials_and_other_hosts(url):
    with pytest.raises(deploy.DeploymentError):
        deploy.published_release(url)


@pytest.mark.parametrize('tag,python_version', [('v1.0.0', '1.0.0'), ('v1.1.0-beta.1', '1.1.0b1')])
def test_release_versions_and_changelog_are_checked_before_build(tmp_path, tag, python_version):
    (tmp_path / 'pyproject.toml').write_text(f'[project]\nversion = "{python_version}"\n')
    (tmp_path / 'package.json').write_text(json.dumps({'version': tag[1:]}))
    (tmp_path / 'CHANGELOG.md').write_text(f'## [{tag[1:]}] - 2026-01-01\n\n### Added\n\n- A feature.\n')
    deploy.validate_release(tmp_path, tag)
    (tmp_path / 'CHANGELOG.md').write_text('## [Unreleased]\n')
    with pytest.raises(deploy.DeploymentError, match='changelog|CHANGELOG'):
        deploy.validate_release(tmp_path, tag)
    (tmp_path / 'package.json').write_text(json.dumps({'version': '0.0.0'}))
    with pytest.raises(deploy.DeploymentError, match='versions'):
        deploy.validate_release(tmp_path, tag)


def test_channel_persists_when_already_current_or_returning_to_older_stable(installation, monkeypatch):
    root, _, _, config, _ = installation
    unit = root / '.config/systemd/user/foxoe.service'
    unit.parent.mkdir(parents=True)
    unit.write_text('managed unit')
    monkeypatch.setattr(deploy.Path, 'home', lambda: root)
    monkeypatch.setattr(deploy.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(deploy.os, 'geteuid', lambda: 1000)
    seen = []
    def select(repository, version, channel):
        seen.append(channel)
        return release('v1.0.0')
    monkeypatch.setattr(deploy, 'published_release', select)
    deploy.main(['update', '--directory', str(root), '--channel', 'beta'])
    assert json.loads((root / 'installation.json').read_text())['channel'] == 'beta'
    deploy.main(['update', '--directory', str(root)])
    assert seen[-1] == 'beta'
    deploy.atomic_json(root / 'installation.json', {**config, 'version': 'v1.1.0-beta.1', 'channel': 'beta'})
    deploy.main(['update', '--directory', str(root), '--channel', 'stable'])
    saved = json.loads((root / 'installation.json').read_text())
    assert saved['channel'] == 'stable'
    assert saved['version'] == 'v1.1.0-beta.1'
    deploy.main(['update', '--directory', str(root)])
    assert json.loads((root / 'installation.json').read_text()) == saved
    monkeypatch.setattr(deploy, 'published_release', lambda *a: (_ for _ in ()).throw(deploy.NoRelease()))
    deploy.main(['update', '--directory', str(root), '--channel', 'stable'])
    assert json.loads((root / 'installation.json').read_text()) == saved


def test_node_checksum_failure_does_not_install_or_extract(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, 'run', lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(deploy.platform, 'machine', lambda: 'armv7l')
    name = f'node-v{deploy.NODE_VERSION}-linux-armv7l.tar.xz'
    def fetch(url, **kw):
        return io.BytesIO((('0' * 64 + '  ' + name + '\n').encode()) if url.endswith('.txt') else b'corrupt archive')
    monkeypatch.setattr(deploy.urllib.request, 'urlopen', fetch)
    with pytest.raises(deploy.DeploymentError, match='checksum'):
        deploy.build_environment(tmp_path)
    assert not (tmp_path / 'tools' / f'node-{deploy.NODE_VERSION}').exists()


def test_fresh_install_failure_cleans_unit_and_can_be_retried(tmp_path, monkeypatch):
    root = tmp_path / 'runtime'
    monkeypatch.setattr(deploy.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(deploy.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(deploy.os, 'geteuid', lambda: 1000)
    monkeypatch.setattr(deploy, 'published_release', lambda *a: release('v1.0.0'))
    monkeypatch.setattr(deploy, 'prerequisites', lambda *_: None)
    monkeypatch.setattr(deploy, 'build_environment', lambda *_: {})
    calls = []
    monkeypatch.setattr(deploy, 'systemctl', lambda *a, **kw: calls.append(a))
    def prepare(*args):
        candidate = root / 'releases/candidate'
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate, {'repository': deploy.REPOSITORY, 'version': 'v1.0.0', 'commit': 'test'}
    monkeypatch.setattr(deploy, 'prepare_release', prepare)
    monkeypatch.setattr(deploy, 'healthy', lambda *_: (_ for _ in ()).throw(deploy.DeploymentError('failed health')))
    command = ['install', '--directory', str(root), '--skip-system-deps', '--channel', 'beta']
    with pytest.raises(deploy.DeploymentError, match='health'):
        deploy.main(command)
    unit = tmp_path / '.config/systemd/user/foxoe.service'
    assert not unit.exists()
    assert not (root / 'pending.json').exists()
    assert not (root / 'installation.json').exists()
    monkeypatch.setattr(deploy, 'healthy', lambda *_: None)
    deploy.main(command)
    assert unit.exists()
    assert json.loads((root / 'installation.json').read_text())['channel'] == 'beta'
    assert ('enable', deploy.UNIT) in calls


def test_installer_does_not_adopt_unmanaged_data(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(deploy.os, 'geteuid', lambda: 1000)
    (tmp_path / 'data').mkdir()
    marker = tmp_path / 'data/important'
    marker.write_text('existing application data')
    with pytest.raises(deploy.DeploymentError, match='Unmanaged'):
        deploy.main(['install', '--directory', str(tmp_path)])
    assert marker.read_text() == 'existing application data'

"""Privileged setup is tested with intercepted commands, never real mutations."""
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('foxoe_system_setup', Path(__file__).parents[1] / 'deploy/setup_system.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


@pytest.fixture
def administrator(monkeypatch):
    monkeypatch.setattr(setup.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(setup.pwd, 'getpwnam', lambda name: SimpleNamespace(pw_name=name, pw_uid=1001))
    calls = []
    monkeypatch.setattr(setup, 'run', lambda *args: calls.append(tuple(map(str, args))))
    return calls


def test_admin_setup_targets_only_named_account_and_never_builds_as_root(administrator):
    setup.main(['--user', 'kiosk'])
    assert ('usermod', '-aG', 'plugdev', 'kiosk') in administrator
    assert ('loginctl', 'enable-linger', 'kiosk') in administrator
    assert not any('sudo' in args or 'wheel' in args for args in administrator)
    assert not any(args[0] in ('git', 'npm', 'pip', 'python3', 'chown', 'useradd') for args in administrator)
    assert administrator[-1] == ('loginctl', 'enable-linger', 'kiosk')


@pytest.mark.parametrize('name', ['root', 'missing', '-root', 'kiosk\nroot', 'kiosk;whoami', ''])
def test_invalid_accounts_are_rejected_before_any_system_changes(administrator, monkeypatch, name):
    def lookup(value):
        if value == 'missing':
            raise KeyError(value)
        return SimpleNamespace(pw_name=value, pw_uid=0 if value == 'root' else 1001)
    monkeypatch.setattr(setup.pwd, 'getpwnam', lookup)
    with pytest.raises(SystemExit):
        setup.main(['--user=' + name])
    assert not administrator


def test_target_account_is_required(administrator):
    with pytest.raises(SystemExit):
        setup.main([])
    assert not administrator


def test_nonprivileged_setup_fails_without_attempting_sudo(administrator, monkeypatch):
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 1001)
    with pytest.raises(SystemExit):
        setup.main(['--user', 'kiosk'])
    assert not administrator


@pytest.mark.parametrize('failed_command', ['apt-get', 'usermod', 'udevadm'])
def test_setup_failure_stops_then_can_be_retried(administrator, monkeypatch, failed_command):
    def command(*args):
        administrator.append(tuple(map(str, args)))
        if args[0] == failed_command:
            raise subprocess.CalledProcessError(1, failed_command)
    monkeypatch.setattr(setup, 'run', command)
    with pytest.raises(subprocess.CalledProcessError):
        setup.main(['--user', 'kiosk'])
    assert not any(args[0] == 'loginctl' for args in administrator)
    monkeypatch.setattr(setup, 'run', lambda *args: administrator.append(tuple(map(str, args))))
    setup.main(['--user', 'kiosk'])
    assert administrator[-1] == ('loginctl', 'enable-linger', 'kiosk')

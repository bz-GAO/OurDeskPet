import json
import queue
import socket
import time

import pytest

from rinatomo.config import AppConfig, ConfigError, load, save
from rinatomo.control import PanelControlServer, prepare_update
from rinatomo.napcat import NapCatSettings, save_napcat_settings


@pytest.mark.parametrize('payload', [
    {'features': {'ping': False, 'echo': 'invalid'}},
    {'features': {'retired_feature': True}},
    {'llm': {'enabled': 'true'}},
    {'llm': {'minReplyInterval': -1}},
    {'llm': {'maxTokens': 0}},
    {'llm': {'apiKey': 'must-not-cross-control-protocol'}},
    {'permissions': {'adminUsers': [True]}},
    {'permissions': {'adminUsers': [10001], 'enabledGroups': [-1]}},
    {'features': []}, {'autoStart': 'false'},
    {'features': {}, 'autoStart': True},
])
def test_invalid_update_cannot_partially_change_settings(payload):
    config = AppConfig()
    with pytest.raises(ConfigError):
        prepare_update(config, NapCatSettings(), payload)
    assert config.features.ping is True
    assert config.permissions.admin_users == []


def test_fresh_profile_is_independent(tmp_path, monkeypatch):
    monkeypatch.setenv('RINATOMO_CONFIG_HOME', str(tmp_path / 'first'))
    original = load()
    updated, _ = prepare_update(original, NapCatSettings(), {'permissions': {'adminUsers': [10001]}})
    save(updated)
    monkeypatch.setenv('RINATOMO_CONFIG_HOME', str(tmp_path / 'second'))
    assert load().permissions.admin_users == []
    assert not load().connection.access_token
    assert not load().path.exists()


def test_autostart_can_be_saved_before_napcat_install(tmp_path, monkeypatch):
    monkeypatch.setenv('RINATOMO_CONFIG_HOME', str(tmp_path))
    config = AppConfig()
    updated, settings = prepare_update(config, NapCatSettings(root=tmp_path / 'missing'), {'autoStart': True})
    save_napcat_settings(settings)
    assert updated is config
    assert json.loads((tmp_path / 'napcat.json').read_text())['auto_start'] is True


def test_llm_settings_are_validated_and_mapped_without_credentials():
    config, settings = prepare_update(AppConfig(), NapCatSettings(), {'llm': {
        'enabled': True,
        'minReplyInterval': 1.5,
        'timeoutSeconds': 20,
        'maxTokens': 300,
        'dailyTokenBudget': 12000,
        'maxInputChars': 1500,
        'maxConcurrentRequests': 3,
    }})
    assert settings == NapCatSettings()
    assert config.llm.enabled is True
    assert config.llm.min_reply_interval == 1.5
    assert config.llm.timeout_seconds == 20
    assert config.llm.max_tokens == 300
    assert config.llm.max_concurrent_requests == 3


def test_fragmented_tcp_request_and_idle_client_recovery():
    events = queue.Queue()
    server = PanelControlServer(events, ('127.0.0.1', 0))
    address = server.socket.getsockname()
    server.start()
    try:
        with socket.create_connection(address, timeout=3) as client:
            client.sendall(b'{"protocolVersion":1,')
            time.sleep(0.02)
            client.sendall(b'"command":"status"}')
            client.shutdown(socket.SHUT_WR)
            kind, request = events.get(timeout=2)
            assert kind == 'control_request'
            request.response.put({'ok': True, 'data': {'provider': 'rinatomo'}})
            assert json.loads(client.recv(4096))['ok'] is True
        with socket.create_connection(address, timeout=3) as idle:
            idle.settimeout(3)
            assert idle.recv(16) == b''
        with socket.create_connection(address, timeout=3) as client:
            client.sendall(b'RINATOMO_SHOW\n')
            assert client.recv(16) == b'OK\n'
    finally:
        server.stop()
        server.thread.join(timeout=3)

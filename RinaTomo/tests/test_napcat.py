import io
import subprocess
from unittest.mock import Mock, patch, PropertyMock

import pytest

from rinatomo.napcat import (
    NAPCAT_REQUIRED_FILES,
    NapCatError,
    NapCatProcess,
    NapCatSettings,
    NapCatWebUI,
    _qq_registry_path,
    discover_napcat_root,
    is_napcat_root,
    load_napcat_settings,
    save_napcat_settings,
)
from rinatomo.ui import _parse_ids


def test_validate_detects_incomplete_napcat_install(tmp_path):
    settings = NapCatSettings(root=tmp_path, qq_path=tmp_path / "QQ.exe")

    with pytest.raises(NapCatError, match="选择本机 NapCat"):
        NapCatProcess(settings).validate()


def test_napcat_settings_auto_start_defaults_off_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setenv("RINATOMO_CONFIG_HOME", str(tmp_path))

    assert load_napcat_settings().auto_start is False

    settings = NapCatSettings(
        root=tmp_path / "napcat",
        qq_path=tmp_path / "QQ.exe",
        quick_account="",
        auto_start=True,
    )
    save_napcat_settings(settings)

    assert load_napcat_settings().auto_start is True


def test_ensure_onebot_server_is_idempotent(tmp_path):
    client = NapCatWebUI(tmp_path)
    config = {"network": {"websocketServers": []}}
    written = []

    with patch.object(client, "get_ob11_config", return_value=config), patch.object(
        client, "set_ob11_config", side_effect=lambda value: written.append(value)
    ):
        assert client.ensure_onebot_server("127.0.0.1", 3001, "secret") is True
        assert client.ensure_onebot_server("127.0.0.1", 3001, "secret") is False

    assert len(written) == 1
    server = config["network"]["websocketServers"][0]
    assert server["name"] == "RinaTomo"
    assert server["messagePostFormat"] == "array"
    assert server["token"] == "secret"


def test_parse_ids_accepts_common_separators_and_deduplicates():
    assert _parse_ids("10001, 10002\n10001；10003", "测试") == [10001, 10002, 10003]


def test_parse_ids_rejects_non_positive_values():
    with pytest.raises(Exception, match="正整数"):
        _parse_ids("10001, 0", "测试")


def test_fresh_machine_uses_local_discovery_and_empty_account(tmp_path, monkeypatch):
    monkeypatch.setenv("RINATOMO_CONFIG_HOME", str(tmp_path / "user-a"))
    monkeypatch.setenv("RINATOMO_NAPCAT_ROOT", str(tmp_path / "portable-napcat"))
    settings = load_napcat_settings()
    assert settings.root == tmp_path / "portable-napcat"
    assert settings.quick_account == ""
    assert settings.auto_start is False
    settings.quick_account = "10001"
    save_napcat_settings(settings)
    monkeypatch.setenv("RINATOMO_CONFIG_HOME", str(tmp_path / "user-b"))
    assert load_napcat_settings().quick_account == ""


def test_invalid_settings_shape_does_not_crash_first_open(tmp_path, monkeypatch):
    monkeypatch.setenv("RINATOMO_CONFIG_HOME", str(tmp_path))
    (tmp_path / "napcat.json").write_text("[]", encoding="utf-8")
    assert load_napcat_settings().auto_start is False


def test_fresh_install_starts_before_webui_config_exists(tmp_path, monkeypatch):
    monkeypatch.setenv('RINATOMO_CONFIG_HOME', str(tmp_path / 'user'))
    for name in ('napcat.mjs', 'NapCatWinBootMain.exe', 'NapCatWinBootHook.dll', 'qqnt.json', 'QQ.exe'):
        (tmp_path / name).touch()
    process = NapCatProcess(NapCatSettings(root=tmp_path, qq_path=tmp_path / 'QQ.exe'))
    with patch('rinatomo.napcat.subprocess.Popen') as spawn:
        spawn.return_value.poll.return_value = 0
        spawn.return_value.stdout = io.BytesIO(b"started\n")
        assert process.start() is True
        spawn.assert_called_once()
        process.stop()


def test_wait_for_webui_retries_first_boot_config_generation(tmp_path):
    process = NapCatProcess(NapCatSettings(root=tmp_path))
    with patch.object(NapCatWebUI, 'webui_config', new_callable=PropertyMock) as config, patch.object(
        NapCatWebUI, 'authenticate'
    ) as authenticate, patch('rinatomo.napcat.port_is_open', return_value=True), patch('rinatomo.napcat.time.sleep'):
        config.side_effect = [NapCatError('configuration not generated yet'), {'port': 6099}]
        assert isinstance(process.wait_for_webui(), NapCatWebUI)
        authenticate.assert_called_once()
def test_release_napcat_does_not_discover_developer_drive_locations(tmp_path, monkeypatch):
    monkeypatch.delenv('RINATOMO_NAPCAT_ROOT', raising=False)
    root = tmp_path / 'NapCat' / 'Shell' / 'napcat'
    root.mkdir(parents=True)
    for name in NAPCAT_REQUIRED_FILES:
        (root / name).touch()
    with patch('rinatomo.napcat._windows_drive_roots', return_value=[tmp_path]) as drives:
        assert discover_napcat_root() == tmp_path / 'profile' / 'NapCat'
        drives.assert_not_called()
        assert is_napcat_root(root)


def test_stale_saved_paths_are_replaced_by_detected_install(tmp_path, monkeypatch):
    profile = tmp_path / 'profile'
    root = tmp_path / 'portable-napcat'
    root.mkdir()
    for name in NAPCAT_REQUIRED_FILES:
        (root / name).touch()
    qq = tmp_path / 'QQ.exe'
    qq.touch()
    profile.mkdir()
    (profile / 'napcat.json').write_text(
        '{"root":"Z:/missing","qq_path":"Z:/missing/QQ.exe"}', encoding='utf-8'
    )
    monkeypatch.setenv('RINATOMO_CONFIG_HOME', str(profile))
    monkeypatch.setenv('RINATOMO_NAPCAT_ROOT', str(root))
    monkeypatch.setenv('RINATOMO_QQ_PATH', str(qq))
    settings = load_napcat_settings()
    assert settings.root == root
    assert settings.qq_path == qq


def test_webui_wait_is_cancelled_before_network_access(tmp_path):
    import threading

    cancelled = threading.Event()
    cancelled.set()
    process = NapCatProcess(NapCatSettings(root=tmp_path))
    with patch.object(NapCatWebUI, 'authenticate') as authenticate:
        with pytest.raises(NapCatError, match='取消'):
            process.wait_for_webui(stop_event=cancelled)
    authenticate.assert_not_called()


@pytest.mark.parametrize("field,template", [
    ("InstallLocation", '"{root}"'),
    ("DisplayIcon", "{root}/QQ.exe,0"),
    ("DisplayIcon", '"{root}/QQ.exe",-1'),
    ("UninstallString", '"{root}/Uninstall.exe" /S'),
    ("UninstallString", "{root}/Uninstall.exe /S"),
])
def test_registry_discovery_separates_icon_indexes_and_command_arguments(
    tmp_path, field, template
):
    root = tmp_path / "Custom QQ"
    assert _qq_registry_path(field, template.format(root=root)) == root / "QQ.exe"


def test_registry_discovery_does_not_resolve_relative_paths_against_cwd():
    assert _qq_registry_path("DisplayIcon", "QQ.exe,0") is None
    assert _qq_registry_path("UninstallString", '"QQ.exe" /S') is None
    assert _qq_registry_path("InstallLocation", "") is None


def test_failed_shutdown_keeps_process_and_log_for_retry(tmp_path):
    manager = NapCatProcess(NapCatSettings(root=tmp_path, qq_path=tmp_path / "QQ.exe"))
    process = Mock()
    process.pid = 12345
    process.poll.return_value = None
    manager.process = process
    capture = Mock()
    manager._log_capture = capture
    with patch("rinatomo.napcat.subprocess.run", return_value=Mock(returncode=1)):
        with pytest.raises(NapCatError, match="重试关闭服务"):
            manager.stop()
    assert manager.process is process
    assert manager.running
    capture.close.assert_not_called()

    with patch("rinatomo.napcat.subprocess.run", return_value=Mock(returncode=0)):
        manager.stop()
    assert manager.process is None
    capture.close.assert_called_once()
    process.wait.assert_called_once_with(timeout=5.0)


def test_timed_out_shutdown_keeps_owned_process(tmp_path):
    manager = NapCatProcess(NapCatSettings(root=tmp_path, qq_path=tmp_path / "QQ.exe"))
    manager.process = process = Mock()
    process.poll.return_value = None
    with patch(
        "rinatomo.napcat.subprocess.run",
        side_effect=subprocess.TimeoutExpired("taskkill", 10),
    ):
        with pytest.raises(NapCatError, match="重试关闭服务"):
            manager.stop()
    assert manager.process is process


def test_spawn_failure_closes_prepared_log(tmp_path):
    for name in (*NAPCAT_REQUIRED_FILES, "QQ.exe"):
        (tmp_path / name).touch()
    manager = NapCatProcess(NapCatSettings(root=tmp_path, qq_path=tmp_path / "QQ.exe"))
    with patch("rinatomo.napcat.ManagedProcessLog") as capture, patch(
        "rinatomo.napcat.subprocess.Popen", side_effect=OSError("launch denied")
    ):
        with pytest.raises(OSError, match="launch denied"):
            manager.start()
    capture.return_value.close.assert_called_once()
    assert manager.process is None

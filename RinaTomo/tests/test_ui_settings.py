"""Native settings integration, isolated from live ports, accounts and NapCat."""
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

import pytest

from rinatomo.config import ConfigError, load
from rinatomo.napcat import NapCatError
from rinatomo.ui import App


@pytest.fixture(scope='module')
def tk_root():
    # One Tcl interpreter per module avoids Windows Tk re-initialization failures.
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def panel(tmp_path, monkeypatch, tk_root):
    monkeypatch.setenv('RINATOMO_CONFIG_HOME', str(tmp_path / 'settings'))
    monkeypatch.setenv('RINATOMO_NAPCAT_ROOT', str(tmp_path / 'not-installed'))
    window = tk.Toplevel(tk_root)
    window.withdraw()
    app = App(window, load(), enable_control_server=False)
    try:
        with patch('rinatomo.ui.messagebox.showerror', side_effect=AssertionError('Unexpected error dialog')):
            yield app
    finally:
        app._exit_app()


def test_remote_autostart_preserves_native_connection_draft(panel):
    panel.ws_url.set('an unfinished address')
    feedback = panel.connection_feedback.cget('text')
    panel._apply_control_update({'autoStart': True})
    assert panel.napcat_settings.auto_start is True
    assert panel.auto_start.get() is True
    assert panel.ws_url.get() == 'an unfinished address'
    assert panel.config.connection.url == 'ws://127.0.0.1:3002'
    assert panel.connection_feedback.cget('text') == feedback
    assert panel.pipeline_thread is None


def test_invalid_remote_update_does_not_overwrite_native_draft(panel):
    panel.feature_echo.set(True)
    with pytest.raises(ConfigError):
        panel._apply_control_update({'features': {'ping': False, 'echo': 'invalid'}})
    assert panel.config.features.ping is True
    assert panel.feature_echo.get() is True


def test_offline_connection_edit_does_not_start_napcat(panel, tmp_path):
    panel.napcat_root.set(str(tmp_path / 'another-missing-install'))
    assert panel.apply_connection_settings() is True
    assert panel.pipeline_thread is None
    assert panel._control_snapshot()['state'] == 'offline'


def test_native_and_embedded_feature_contract_is_public_only(panel):
    assert panel._control_snapshot()['features'] == {'ping': True, 'echo': False}
    panel._apply_control_update({'features': {'ping': False, 'echo': True}})
    assert panel.feature_ping.get() is False
    assert panel.feature_echo.get() is True
    assert panel._control_snapshot()['features'] == {'ping': False, 'echo': True}


def test_native_llm_settings_accept_presets_and_custom_interval(panel):
    panel.llm_enabled.set(True)
    panel.llm_interval.set('2.5')
    panel.llm_timeout.set('20')
    panel.llm_max_tokens.set('300')
    panel.llm_daily_budget.set('12000')
    panel.llm_max_input.set('1500')
    panel.llm_concurrency.set('3')
    assert panel.apply_llm_settings() is True
    assert panel.config.llm.enabled is True
    assert panel.config.llm.min_reply_interval == 2.5
    assert panel._control_snapshot()['llm']['maxConcurrentRequests'] == 3


def test_remote_llm_update_refreshes_native_controls(panel):
    panel._apply_control_update({'llm': {
        'enabled': False,
        'minReplyInterval': 5,
        'timeoutSeconds': 15,
        'maxTokens': 200,
        'dailyTokenBudget': 9000,
        'maxInputChars': 1200,
        'maxConcurrentRequests': 2,
    }})
    assert panel.llm_enabled.get() is False
    assert panel.llm_interval.get() == '5'
    assert panel.llm_timeout.get() == '15'
    assert panel.llm_feedback.cget('text') == '✓ 已应用'


def test_login_overlay_is_embedded_dismissible_and_in_snapshot(panel):
    panel.show_login_overlay(force=True)
    panel.window.update_idletasks()
    assert panel.login_overlay.winfo_manager() == 'place'
    assert panel._control_snapshot()['login']['required'] is True
    panel.dismiss_login_overlay()
    assert panel.login_overlay.winfo_manager() == ''
    assert panel._control_snapshot()['login']['required'] is True
    panel.hide_login_overlay()
    assert panel._control_snapshot()['login']['required'] is False


def test_settings_form_accepts_mouse_wheel(panel):
    with patch.object(panel.settings_canvas, 'yview', return_value=(0.25, 0.35)), patch.object(
        panel.settings_canvas, 'yview_scroll'
    ) as scroll:
        result = panel._scroll_settings(
            SimpleNamespace(widget=panel.settings_body, delta=-120, num=None)
        )
    assert result == 'break'
    scroll.assert_called_once_with(1, 'units')


def test_close_service_button_only_appears_while_pipeline_runs(panel):
    assert panel.shutdown_button.winfo_manager() == ''
    panel.pipeline_thread = SimpleNamespace(is_alive=lambda: True)
    panel._refresh_primary_action()
    assert panel.shutdown_button.winfo_manager() == 'pack'
    panel.pipeline_thread = None
    panel._refresh_primary_action()
    assert panel.shutdown_button.winfo_manager() == ''


def test_connection_details_are_advanced_and_redetection_applies(panel, tmp_path):
    root = tmp_path / 'napcat'
    root.mkdir()
    for name in ('napcat.mjs', 'NapCatWinBootMain.exe', 'NapCatWinBootHook.dll', 'qqnt.json'):
        (root / name).touch()
    qq = tmp_path / 'QQ.exe'
    qq.touch()
    assert panel.connection_advanced.winfo_manager() == ''
    panel._toggle_connection_advanced()
    assert panel.connection_advanced.winfo_manager() == 'grid'
    with patch('rinatomo.ui.discover_napcat_root', return_value=root), patch(
        'rinatomo.ui.discover_qq_path', return_value=qq
    ):
        assert panel.redetect_connection_settings() is True
    assert panel.napcat_settings.root == root
    assert panel.napcat_settings.qq_path == qq
    assert panel.connection_summary.get() == 'NapCat 已找到  ·  QQ 已找到'


def test_lifecycle_owner_controls_window_close_without_reminder(panel):
    panel.owner = 'desk'
    with patch.object(panel.window, 'withdraw') as withdraw, patch.object(
        panel, 'shutdown_all'
    ) as shutdown:
        panel.close_window()
    withdraw.assert_called_once()
    shutdown.assert_not_called()
    assert panel.panel_hidden is True
    assert panel._control_snapshot()['owner'] == 'desk'

    panel.owner = 'standalone'
    panel.panel_hidden = False
    with patch.object(panel, '_exit_app') as exit_app:
        panel.close_window()
    exit_app.assert_called_once()

    panel.pipeline_thread = SimpleNamespace(is_alive=lambda: True)
    with patch.object(panel, 'shutdown_all') as shutdown:
        panel.close_window()
    shutdown.assert_called_once()
    panel.pipeline_thread = None


def test_shutdown_during_process_launch_cleans_up_without_starting_bot(panel):
    process = Mock()
    process.start.side_effect = lambda: panel.pipeline_stop.set()
    with patch('rinatomo.ui.NapCatProcess', return_value=process), patch.object(
        panel.bot, 'start'
    ) as start:
        panel._pipeline_worker()
    process.wait_for_webui.assert_not_called()
    process.stop.assert_called_once()
    start.assert_not_called()


def test_shutdown_during_login_does_not_restart_bot(panel):
    process = Mock()
    client = process.wait_for_webui.return_value

    def login():
        panel.pipeline_stop.set()
        return {'isLogin': True}

    client.check_login.side_effect = login
    with patch('rinatomo.ui.NapCatProcess', return_value=process), patch.object(
        panel.bot, 'start'
    ) as start:
        panel._pipeline_worker()
    start.assert_not_called()
    process.stop.assert_called_once()


def test_shutdown_failure_preserves_owned_service_and_enables_retry(panel):
    process = Mock()
    process.running = True
    process.stop.side_effect = NapCatError("请重试关闭服务")
    panel.napcat_process = process
    panel.shutting_down = True
    panel.panel_hidden = True
    panel._shutdown_worker()
    with patch.object(panel, "_exit_app") as exit_app, patch.object(
        panel.window, "deiconify"
    ) as show:
        panel._poll_events()
    exit_app.assert_not_called()
    show.assert_called_once()
    assert panel.napcat_process is process
    assert panel.shutting_down is False
    assert panel._control_snapshot()["running"] is True
    assert panel._control_snapshot()["shutdownError"] == "请重试关闭服务"
    assert panel.shutdown_button.winfo_manager() == "pack"
    assert str(panel.shutdown_button.cget("state")) == "normal"
    assert str(panel.action_button.cget("state")) == "disabled"
    with patch("rinatomo.ui.threading.Thread") as thread:
        panel.start_pipeline()
    thread.assert_not_called()

    process.stop.side_effect = None
    process.running = False
    panel.shutting_down = True
    panel.shutdown_error = ""
    panel._shutdown_worker()
    with patch.object(panel, "_exit_app") as exit_app:
        panel._poll_events()
    exit_app.assert_called_once()
    assert panel.napcat_process is None


def test_shutdown_does_not_exit_with_a_live_message_worker(panel):
    with patch.object(type(panel.bot), "running", new_callable=PropertyMock, return_value=True), patch.object(
        panel.bot, "stop"
    ):
        panel._shutdown_worker()
    assert panel.events.get_nowait()[0] == "shutdown_failed"

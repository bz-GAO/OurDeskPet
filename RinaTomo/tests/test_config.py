from pathlib import Path

import pytest

from rinatomo.config import (
    AppConfig,
    ConfigError,
    FeaturesConfig,
    LlmConfig,
    PermissionsConfig,
    default_config_dir,
    load,
    save,
)


def _write_config(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_load_valid_config(tmp_path):
    path = _write_config(
        tmp_path / "config.toml",
        """
[connection]
url = "wss://example.invalid/onebot"
reconnect_delay = 1.5

[bot]
echo = true

[permissions]
admin_users = [10001]
enabled_groups = [20001]
""",
    )

    config = load(path)

    assert config.connection.url == "wss://example.invalid/onebot"
    assert config.connection.reconnect_delay == 1.5
    assert config.bot.echo is True
    assert config.permissions.admin_users == [10001]
    assert config.path == path


def test_default_config_path_is_stable(tmp_path, monkeypatch):
    config_home = tmp_path / "settings"
    config_home.mkdir()
    monkeypatch.setenv("RINATOMO_CONFIG_HOME", str(config_home))

    config = load()

    assert default_config_dir() == config_home
    assert config.path == config_home / "config.toml"
    assert "not found; using defaults" in config.sanitized_summary()


def test_save_roundtrip_includes_dynamic_features(tmp_path):
    path = tmp_path / "nested" / "config.toml"
    source = AppConfig(
        features=FeaturesConfig(ping=False),
        permissions=PermissionsConfig(
            admin_users=[10001],
            private_whitelist=[10002],
            enabled_groups=[20001],
        ),
        llm=LlmConfig(
            enabled=True,
            model="qwen-plus",
            timeout_seconds=12,
            max_tokens=128,
            daily_token_budget=999,
            min_reply_interval=1.5,
            max_input_chars=900,
            max_concurrent_requests=1,
        ),
        path=path,
    )

    assert save(source) == path
    restored = load(path)

    assert restored.features == source.features
    assert restored.permissions == source.permissions
    assert restored.llm == source.llm


@pytest.mark.parametrize(
    "body, message",
    [
        ('[connection]\nurl = "http://example.invalid"\n', "must be a ws"),
        ('[connection]\nurl = "ws://"\n', "must be a ws"),
        ('[connection]\nurl = "ws://user:pass@example.invalid"\n', "embedded credentials"),
        ('[connection]\nurl = "ws://example.invalid?access_token=test"\n', "query"),
        ('[connection]\nurl = "ws://example.invalid#test"\n', "fragment"),
        ('[connection]\nreconnect_delay = 0\n', "greater than zero"),
        ('[connection]\nreconnect_delay = inf\n', "finite number"),
        ('[bot]\necho = "false"\n', "must be true or false"),
        ('[bot]\nname = "  "\n', "must not be empty"),
        ('[features]\nping = "yes"\n', "must be true or false"),
        ('[permissions]\nadmin_users = [true]\n', "positive integers"),
        ('[llm]\ntimeout_seconds = 0\n', "timeout_seconds"),
        ('[llm]\nmax_tokens = -1\n', "max_tokens"),
        ('[llm]\nmin_reply_interval = -1\n', "min_reply_interval"),
        ('[llm]\nmin_reply_interval = inf\n', "min_reply_interval"),
        ('[llm]\nmax_concurrent_requests = true\n', "max_concurrent_requests"),
    ],
)
def test_invalid_config_is_rejected(tmp_path, body, message):
    path = _write_config(tmp_path / "config.toml", body)

    with pytest.raises(ConfigError, match=message):
        load(path)


def test_retired_settings_are_ignored_and_removed_on_save(tmp_path):
    path = _write_config(tmp_path / 'config.toml', '''
[features]
ping = false
retired_response = true
retired_cooldown = 12.5
[permissions]
admin_users = [10001]
''')
    config = load(path)
    assert vars(config.features) == {'ping': False}
    assert config.permissions.admin_users == [10001]
    save(config)
    assert 'retired_' not in path.read_text(encoding='utf-8')
    assert load(path).permissions.admin_users == [10001]

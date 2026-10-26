import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time

import pytest

from rinatomo import llm as llm_module
from rinatomo.config import LlmConfig
from rinatomo.llm import (
    ApiKeyMissing,
    LlmClient,
    LlmError,
    TokenBudget,
    read_env_file,
    resolve_api_settings,
    resolve_model_name,
)


@pytest.fixture(autouse=True)
def _isolate_project_env(tmp_path, monkeypatch):
    """Tests must not depend on a developer's real gitignored .env."""
    monkeypatch.setattr(llm_module, "PROJECT_ENV_PATH", tmp_path / "missing-project.env")


def test_env_resolution_prefers_process_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    with pytest.raises(ApiKeyMissing):
        resolve_api_settings(tmp_path)

    (tmp_path / ".env").write_text(
        "DASHSCOPE_API_KEY=file-key\nDASHSCOPE_BASE_URL=https://example.invalid/v1\n",
        encoding="utf-8",
    )
    assert resolve_api_settings(tmp_path) == ("file-key", "https://example.invalid/v1")

    monkeypatch.setenv("DASHSCOPE_API_KEY", "environment-key")
    key, _ = resolve_api_settings(tmp_path)
    assert key == "environment-key"


def test_read_env_file_does_not_mutate_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("RINATOMO_TEST_VALUE", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nRINATOMO_TEST_VALUE = 'quoted value'\nEMPTY=\nBAD LINE\n",
        encoding="utf-8",
    )
    assert read_env_file(path) == {"RINATOMO_TEST_VALUE": "quoted value"}
    import os

    assert "RINATOMO_TEST_VALUE" not in os.environ


def test_model_resolution_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_MODEL", raising=False)
    project_env = tmp_path / "project.env"
    project_env.write_text("DASHSCOPE_MODEL=project-model\n", encoding="utf-8")
    monkeypatch.setattr(llm_module, "PROJECT_ENV_PATH", project_env)

    config_dir = tmp_path / "profile"
    config_dir.mkdir()
    (config_dir / ".env").write_text("DASHSCOPE_MODEL=profile-model\n", encoding="utf-8")
    assert resolve_model_name("config-model", config_dir) == "profile-model"

    monkeypatch.setenv("DASHSCOPE_MODEL", "environment-model")
    assert resolve_model_name("config-model", config_dir) == "environment-model"


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/service",
        "https://user:secret@example.invalid/v1",
        "https://example.invalid/v1?token=secret",
    ],
)
def test_llm_client_rejects_unsafe_base_url(url):
    with pytest.raises(LlmError, match="base URL"):
        LlmClient("key", url, LlmConfig())


def test_budget_reserves_parallel_capacity_and_persists(tmp_path):
    state_path = tmp_path / "usage.json"
    budget = TokenBudget(100, state_path)
    first = budget.try_reserve(60)
    assert first is not None
    assert budget.try_reserve(50) is None
    budget.settle(first, 40)
    assert budget.used == 40
    assert json.loads(state_path.read_text(encoding="utf-8"))["used"] == 40
    assert TokenBudget(100, state_path).used == 40


def test_budget_falls_back_to_reservation_when_provider_usage_is_missing():
    budget = TokenBudget(100)
    reservation = budget.try_reserve(35)
    assert reservation is not None
    budget.settle(reservation, 0)
    assert budget.used == 35


def test_budget_persistence_failure_preserves_in_memory_guard(tmp_path, monkeypatch):
    from pathlib import Path

    budget = TokenBudget(100, tmp_path / 'usage.json')
    def denied(*args, **kwargs):
        raise PermissionError('read-only profile')
    monkeypatch.setattr(Path, 'mkdir', denied)
    monkeypatch.setattr(Path, 'unlink', denied)
    reservation = budget.try_reserve(35)
    assert reservation is not None
    budget.settle(reservation, 30)
    assert budget.snapshot() == {'used': 30, 'dailyLimit': 100, 'remaining': 70}


def test_budget_resets_by_utc_day(monkeypatch):
    budget = TokenBudget(100)
    reservation = budget.try_reserve(25)
    assert reservation is not None
    budget.settle(reservation, 25)
    monkeypatch.setattr(TokenBudget, "_today", staticmethod(lambda: "2099-12-31"))
    assert budget.used == 0


async def _fake_llm_server(handler):
    from aiohttp import web

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    return runner, f"http://127.0.0.1:{port}/v1"


def test_llm_client_round_trip_and_sanitized_http_error():
    async def scenario():
        import aiohttp
        from aiohttp import web

        received = []

        async def ok(request):
            received.append(await request.json())
            return web.json_response(
                {
                    "choices": [{"message": {"content": " 嗯。 "}}],
                    "usage": {"total_tokens": 42},
                }
            )

        runner, url = await _fake_llm_server(ok)
        try:
            client = LlmClient("key", url, LlmConfig(timeout_seconds=5))
            messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "问句"}]
            async with aiohttp.ClientSession() as session:
                completion = await client.complete(session, messages)
            assert completion.text == "嗯。"
            assert completion.total_tokens == 42
            assert received[0]["messages"] == messages
        finally:
            await runner.cleanup()

        async def fail(request):
            return web.Response(status=401, text="secret echoed body")

        runner, url = await _fake_llm_server(fail)
        try:
            client = LlmClient("key", url, LlmConfig(timeout_seconds=5))
            async with aiohttp.ClientSession() as session:
                with pytest.raises(LlmError) as caught:
                    await client.complete(session, [{"role": "user", "content": "x"}])
            assert "secret echoed body" not in str(caught.value)
            assert "401" in str(caught.value)
        finally:
            await runner.cleanup()

    asyncio.run(scenario())


def test_llm_client_timeout():
    async def scenario():
        import aiohttp
        from aiohttp import web

        async def slow(request):
            await asyncio.sleep(1)
            return web.json_response({"choices": []})

        runner, url = await _fake_llm_server(slow)
        try:
            client = LlmClient("key", url, LlmConfig(timeout_seconds=0.05))
            async with aiohttp.ClientSession() as session:
                with pytest.raises(LlmError, match="timed out"):
                    await client.complete(session, [{"role": "user", "content": "x"}])
        finally:
            await runner.cleanup()

    asyncio.run(scenario())


def test_budget_snapshot_reports_usage_and_remaining(tmp_path):
    budget = TokenBudget(1000, tmp_path / 'llm-usage.json')
    assert budget.snapshot() == {'used': 0, 'dailyLimit': 1000, 'remaining': 1000}
    reservation = budget.try_reserve(400)
    assert budget.snapshot() == {'used': 0, 'dailyLimit': 1000, 'remaining': 600}
    budget.settle(reservation, 350)
    assert budget.snapshot() == {'used': 350, 'dailyLimit': 1000, 'remaining': 650}


def test_budget_reservations_are_thread_safe():
    budget = TokenBudget(100000)

    def charge_batch():
        for _ in range(100):
            reservation = budget.try_reserve(10)
            assert reservation is not None
            budget.settle(reservation, 10)
            snapshot = budget.snapshot()
            assert snapshot['remaining'] >= 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: charge_batch(), range(4)))

    assert budget.snapshot() == {
        'used': 4000, 'dailyLimit': 100000, 'remaining': 96000,
    }


def test_read_usage_snapshot_loads_durable_state_without_responder(tmp_path):
    from rinatomo.llm import read_usage_snapshot

    state = tmp_path / 'llm-usage.json'
    today = time.strftime('%Y-%m-%d', time.gmtime())
    state.write_text(json.dumps({'day': today, 'used': 123}) + '\n', encoding='utf-8')
    assert read_usage_snapshot(1000, tmp_path) == {
        'used': 123, 'dailyLimit': 1000, 'remaining': 877,
    }
    # no config dir -> neutral zero usage
    assert read_usage_snapshot(500, None) == {'used': 0, 'dailyLimit': 500, 'remaining': 500}

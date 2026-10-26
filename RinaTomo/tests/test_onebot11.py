import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from rinatomo.actions import Actions
from rinatomo.config import ConnectionConfig, PermissionsConfig
from rinatomo.dispatcher import Dispatcher
from rinatomo.events import (
    GroupMessageEvent,
    MetaEvent,
    PrivateMessageEvent,
    extract_plain_text,
    parse_event,
)
from rinatomo.handlers import make_echo, ping
from rinatomo.permissions import Permissions
from rinatomo.transport import OneBot11Transport, TransportError
from tests.fake_onebot import FakeOneBotServer, wait_for_condition

BOT_ID = 90001
ADMIN_ID = 10001
USER_ID = 10002
GROUP_ID = 20001


def _group_event(text: str) -> dict:
    return {
        "post_type": "message",
        "message_type": "group",
        "self_id": BOT_ID,
        "group_id": GROUP_ID,
        "user_id": USER_ID,
        "message_id": 42,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
    }


def test_reply_quotes_source_and_targets_group_sender():
    async def scenario():
        transport = MagicMock()
        transport.call_action = AsyncMock(return_value={"message_id": 99})
        actions = Actions(transport)
        event = parse_event(_group_event("问：你好"))
        assert isinstance(event, GroupMessageEvent)

        await actions.reply_to_message(event, "回答")

        transport.call_action.assert_awaited_once_with(
            "send_group_msg",
            group_id=GROUP_ID,
            message=[
                {"type": "reply", "data": {"id": "42"}},
                {"type": "at", "data": {"qq": str(USER_ID)}},
                {"type": "text", "data": {"text": " 回答"}},
            ],
        )

    asyncio.run(scenario())


def test_parse_group_message():
    payload = _group_event(" ping ")
    payload["message"] = [
        {"type": "at", "data": {"qq": str(BOT_ID)}},
        {"type": "text", "data": {"text": " ping"}},
    ]
    event = parse_event(payload)
    assert isinstance(event, GroupMessageEvent)
    assert event.group_id == GROUP_ID
    assert event.text == "ping"
    assert event.is_at_me


def test_parse_private_message_string_form():
    event = parse_event(
        {
            "post_type": "message",
            "message_type": "private",
            "self_id": BOT_ID,
            "user_id": USER_ID,
            "message_id": 7,
            "message": "hello",
            "raw_message": "hello",
        }
    )
    assert isinstance(event, PrivateMessageEvent)
    assert event.text == "hello"
    assert not event.is_at_me


def test_parse_meta_and_non_events():
    assert isinstance(
        parse_event({"post_type": "meta_event", "meta_event_type": "heartbeat"}), MetaEvent
    )
    assert parse_event({"status": "ok", "retcode": 0, "echo": "x"}) is None
    assert parse_event({"post_type": "message", "message_type": "unknown"}) is None


def test_extract_plain_text_cq_string():
    assert extract_plain_text({"message": "abc", "raw_message": "abc"}) == "abc"


def test_ping_handler_ignores_other_text():
    actions = AsyncMock()
    event = parse_event(_group_event("hello"))
    asyncio.run(ping(event, actions))
    actions.send_group_msg.assert_not_called()


def test_permissions_default_deny():
    perms = Permissions(PermissionsConfig(admin_users=[ADMIN_ID]))
    sent = []

    async def capture_send(user_id, text):
        sent.append((user_id, text))

    actions = MagicMock()
    actions.send_private_msg = capture_send
    dispatcher = Dispatcher(actions, perms)
    dispatcher.register(ping)

    # Stranger private chat: dropped before reaching any handler.
    stranger = parse_event(
        {
            "post_type": "message",
            "message_type": "private",
            "self_id": BOT_ID,
            "user_id": USER_ID,
            "message_id": 1,
            "message": [{"type": "text", "data": {"text": "ping"}}],
        }
    )
    asyncio.run(dispatcher.dispatch(stranger))
    assert sent == []

    # Admin private chat: passes the gate, handler replies.
    admin = parse_event(
        {
            "post_type": "message",
            "message_type": "private",
            "self_id": BOT_ID,
            "user_id": ADMIN_ID,
            "message_id": 2,
            "message": [{"type": "text", "data": {"text": "ping"}}],
        }
    )
    asyncio.run(dispatcher.dispatch(admin))
    assert sent == [(ADMIN_ID, "pong")]

    # Non-whitelisted group: silent even for admin-authored ping from another member.
    group_msg = parse_event(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": BOT_ID,
            "group_id": GROUP_ID,
            "user_id": ADMIN_ID,
            "message_id": 3,
            "message": [{"type": "text", "data": {"text": "ping"}}],
        }
    )
    # admin bypasses group whitelist by design; use a normal member instead
    group_msg.user_id = USER_ID
    asyncio.run(dispatcher.dispatch(group_msg))
    assert len(sent) == 1  # unchanged

    # Non-message events always pass.
    assert perms.allows(parse_event({"post_type": "meta_event", "meta_event_type": "heartbeat"}))


def _run(coro):
    return asyncio.run(coro)


def test_full_loop_ping_pong():
    pytest.importorskip("aiohttp")

    async def scenario():
        server = FakeOneBotServer()
        url = await server.start()
        try:
            transport = OneBot11Transport(ConnectionConfig(url=url))
            dispatcher = Dispatcher(Actions(transport))
            dispatcher.register(ping)
            transport.set_event_handler(dispatcher.dispatch)
            runner = asyncio.create_task(transport.start())
            try:
                await wait_for_condition(lambda: server.connected)
                await server.push_group_message("ping")
                await wait_for_condition(lambda: server.received_actions)
                action = server.received_actions[0]
                assert action["action"] == "send_group_msg"
                assert action["params"]["message"] == "pong"
            finally:
                await transport.stop()
                await runner
        finally:
            await server.stop()

    _run(scenario())


def test_full_loop_echo_disabled():
    pytest.importorskip("aiohttp")

    async def scenario():
        server = FakeOneBotServer()
        url = await server.start()
        try:
            transport = OneBot11Transport(ConnectionConfig(url=url))
            dispatcher = Dispatcher(Actions(transport))
            dispatcher.register(make_echo(False))
            transport.set_event_handler(dispatcher.dispatch)
            runner = asyncio.create_task(transport.start())
            try:
                await wait_for_condition(lambda: server.connected)
                await server.push_group_message("repeat me")
                await asyncio.sleep(0.5)
                assert server.received_actions == []
            finally:
                await transport.stop()
                await runner
        finally:
            await server.stop()

    _run(scenario())


def test_action_response_correlation():
    pytest.importorskip("aiohttp")

    async def scenario():
        server = FakeOneBotServer()
        url = await server.start()
        try:
            transport = OneBot11Transport(ConnectionConfig(url=url))
            runner = asyncio.create_task(transport.start())
            try:
                await wait_for_condition(lambda: server.connected)
                data = await transport.call_action("get_status")
                assert data == {"message_id": 1}
            finally:
                await transport.stop()
                await runner
        finally:
            await server.stop()

    _run(scenario())


def test_connection_close_fails_pending_action_immediately():
    pytest.importorskip("aiohttp")

    async def scenario():
        server = FakeOneBotServer(respond_to_actions=False)
        url = await server.start()
        try:
            transport = OneBot11Transport(ConnectionConfig(url=url, reconnect_delay=0.1))
            runner = asyncio.create_task(transport.start())
            try:
                await wait_for_condition(lambda: server.connected)
                with pytest.raises(TransportError, match="connection closed"):
                    await asyncio.wait_for(transport.call_action("get_status"), timeout=2.0)
            finally:
                await transport.stop()
                await runner
        finally:
            await server.stop()

    _run(scenario())

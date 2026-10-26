"""CLI entry points: `rinatomo run` and `rinatomo doctor`.

`run` is the single long-running entry a future RinaDesk control layer can
launch as a child process; `doctor` doubles as a health-check command.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from contextlib import suppress
from pathlib import Path

from . import __version__
from .actions import Actions
from .config import AppConfig, ConfigError, load
from .dispatcher import Dispatcher
from .handlers.chat import ChatResponder
from .permissions import Permissions
from .runtime import build_handlers
from .transport import OneBot11Transport, TransportError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rinatomo", description="QQ bot skeleton (OneBot 11)")
    parser.add_argument("--version", action="version", version=f"rinatomo {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=None, help="path to config.toml")

    sub.add_parser("run", parents=[common], help="run the bot (long-running)")
    sub.add_parser("doctor", parents=[common], help="check config and protocol link")
    ui_parser = sub.add_parser("ui", parents=[common], help="open the local control panel")
    ui_parser.add_argument(
        "--owner",
        choices=("standalone", "desk"),
        default="standalone",
        help="lifecycle owner for the controller process",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load(args.config)
    except (ConfigError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "ui":
        from .ui import run_ui

        return run_ui(config, owner=args.owner)
    if args.command == "run":
        return asyncio.run(_run(config))
    return asyncio.run(_doctor(config))


async def _run(config: AppConfig) -> int:
    transport = OneBot11Transport(config.connection)
    dispatcher = Dispatcher(Actions(transport), Permissions(config.permissions))
    chat = ChatResponder(config)
    dispatcher.replace_handlers(build_handlers(config, chat))
    transport.set_event_handler(dispatcher.dispatch)
    try:
        await transport.start()
    finally:
        await transport.stop()
    return 0


async def _doctor(config: AppConfig) -> int:
    print(config.sanitized_summary())
    transport = OneBot11Transport(config.connection)
    try:
        login_info = await asyncio.wait_for(
            _probe(transport), timeout=20.0
        )
    except TransportError as exc:
        print(f"doctor: link FAILED: {exc}", file=sys.stderr)
        return 1
    except asyncio.TimeoutError:
        print("doctor: link FAILED: timed out", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"doctor: link FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        await transport.stop()
    print(f"doctor: link OK; login info: {login_info}")
    return 0


async def _probe(transport: OneBot11Transport):
    task = asyncio.create_task(transport.start())
    # OneBot11Transport.start() reconnects forever; probe once then stop it.
    try:
        for _ in range(50):
            try:
                return await transport.call_action("get_login_info")
            except TransportError as exc:
                message = str(exc)
                if any(
                    reason in message
                    for reason in ("not connected", "timed out", "connection closed")
                ):
                    await asyncio.sleep(0.2)
                    continue
                raise
        raise TransportError("probe did not complete")
    finally:
        await transport.stop()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

import asyncio
from unittest.mock import Mock, patch

from rinatomo.config import AppConfig
from rinatomo.runtime import BotService


def test_stop_cancels_transport_even_during_long_reconnect_backoff():
    async def run():
        service = BotService(lambda *_: None, lambda *_: None)
        service._config = AppConfig()
        cancelled = asyncio.Event()

        class WaitingTransport:
            def __init__(self, _):
                pass

            def set_event_handler(self, _):
                pass

            def set_state_handler(self, _):
                pass

            async def start(self):
                try:
                    service._stop_event.set()
                    await asyncio.sleep(60)
                finally:
                    cancelled.set()

            async def stop(self):
                pass

        with patch('rinatomo.runtime.OneBot11Transport', WaitingTransport):
            await asyncio.wait_for(service._serve(), timeout=1)
        assert cancelled.is_set()

    asyncio.run(run())


def test_timed_out_stop_retains_worker_ownership():
    service = BotService(lambda *_: None, lambda *_: None)
    worker = Mock()
    worker.is_alive.return_value = True
    service._thread = worker
    service.stop(timeout=0)
    assert service.running
    assert service._thread is worker

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rinayaki.translation import DashScopeApiError, DashScopeOpenAIClient, load_dotenv, qwen_mt_payload, refinement_payload


class TranslationPayloadTests(unittest.TestCase):
    def _stream(self, chunks, model='qwen-mt-flash', callback=None):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def __iter__(self):
                return iter(('data: ' + (item if isinstance(item, str) else json.dumps(item)) + '\n').encode() for item in chunks)
        updates = []
        client = DashScopeOpenAIClient('test', minimum_interval_seconds=0)
        with patch('rinayaki.translation.request_with_retry', return_value=Response()):
            result = client.chat_completions_stream(qwen_mt_payload('hello', model=model), on_update=callback or updates.append)
        return result, updates

    def test_truncated_stream_is_not_success(self):
        with self.assertRaises(DashScopeApiError):
            self._stream([{'choices': [{'delta': {'content': 'partial'}}]}])

    def test_stream_errors_and_abnormal_finish_are_not_success(self):
        for chunk in ({'error': {'message': 'failed'}}, {'choices': [{'finish_reason': 'length'}]}, []):
            with self.subTest(chunk=chunk), self.assertRaises(DashScopeApiError):
                self._stream([chunk, '[DONE]'])

    def test_cumulative_stream_can_correct_and_shorten_text(self):
        chunks = [{'choices': [{'delta': {'content': text}}]} for text in ('hello', 'help', 'hi')]
        result, updates = self._stream(chunks + ['[DONE]'], model='qwen-mt-plus')
        self.assertEqual(updates, ['hello', 'help', 'hi'])
        self.assertEqual(result.content, 'hi')

    def test_other_compatible_models_use_deltas(self):
        chunks = [{'choices': [{'delta': {'content': text}}]} for text in ('a', 'ab')]
        result, _ = self._stream(chunks + ['[DONE]'], model='compatible-model')
        self.assertEqual(result.content, 'aab')

    def test_callback_can_stop_stream(self):
        def stop(_text):
            raise RuntimeError('stopped')
        with self.assertRaisesRegex(RuntimeError, 'stopped'):
            self._stream([{'choices': [{'delta': {'content': 'a'}}]}, '[DONE]'], callback=stop)

    def test_qwen_mt_uses_exact_translation_parameters(self) -> None:
        payload = qwen_mt_payload("今日はありがとう。")
        self.assertEqual(payload["model"], "qwen-mt-flash")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "今日はありがとう。"}])
        self.assertEqual(
            payload["translation_options"],
            {"source_lang": "Japanese", "target_lang": "Chinese",
             "domains": "These are short timed subtitles from online video. Translate naturally and concisely for on-screen reading. Preserve meaning, tone, names, numbers, and established terms. Do not add explanations."},
        )
        self.assertNotIn("system", payload)
        self.assertNotIn('domains',qwen_mt_payload('こんにちは',model='qwen-mt-lite')['translation_options'])

    def test_refinement_reasoning_effort_is_model_specific(self) -> None:
        payload = refinement_payload(
            "原文", "译文", model="qwen3.8-flash", reasoning_effort="none"
        )
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertEqual(payload["max_completion_tokens"], 512)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["messages"][0]["role"], "system")

    def test_reasoning_refiner_gets_room_for_reasoning_and_answer(self) -> None:
        payload = refinement_payload(
            "原文", "译文", model="deepseek-v4.1-flash", reasoning_effort="low"
        )
        self.assertEqual(payload["max_completion_tokens"], 4096)

    def test_dotenv_does_not_override_existing_process_value(self) -> None:
        variable = "RINAYAKI_TEST_EXISTING_VALUE"
        old_value = os.environ.get(variable)
        os.environ[variable] = "process"
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / ".env"
                path.write_text(f"{variable}=file\n", encoding="utf-8")
                load_dotenv(path)
            self.assertEqual(os.environ[variable], "process")
        finally:
            if old_value is None:
                os.environ.pop(variable, None)
            else:
                os.environ[variable] = old_value

    def test_streaming_translation_reconstructs_incremental_flash_chunks(self) -> None:
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def __iter__(self):
                return iter((
                    b'data: {"id":"r1","model":"qwen-mt-flash","choices":[{"delta":{"content":"ni"},"finish_reason":null}]}\n',
                    b'data: {"id":"r1","model":"qwen-mt-flash","choices":[{"delta":{"content":"hao"},"finish_reason":"stop"}]}\n',
                    b'data: [DONE]\n',
                ))
        updates = []
        client = DashScopeOpenAIClient('test', minimum_interval_seconds=0)
        with patch('rinayaki.translation.request_with_retry', return_value=Response()):
            result = client.chat_completions_stream(
                qwen_mt_payload('hello'), on_update=updates.append, timeout_seconds=1
            )
        self.assertEqual(updates, ['ni', 'nihao'])
        self.assertEqual(result.content, 'nihao')

    def test_streaming_translation_normalizes_cumulative_plus_chunks(self) -> None:
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def __iter__(self):
                return iter((
                    b'data: {"model":"qwen-mt-plus","choices":[{"delta":{"content":"a"}}]}\n',
                    b'data: {"model":"qwen-mt-plus","choices":[{"delta":{"content":"ab"}}]}\n',
                    b'data: {"model":"qwen-mt-plus","choices":[{"delta":{"content":"abc"},"finish_reason":"stop"}]}\n',
                    b'data: [DONE]\n',
                ))
        updates = []
        client = DashScopeOpenAIClient('test', minimum_interval_seconds=0)
        payload = qwen_mt_payload('hello', model='qwen-mt-plus')
        with patch('rinayaki.translation.request_with_retry', return_value=Response()):
            result = client.chat_completions_stream(payload, on_update=updates.append, timeout_seconds=1)
        self.assertEqual(updates, ['a', 'ab', 'abc'])
        self.assertEqual(result.content, 'abc')


if __name__ == "__main__":
    unittest.main()

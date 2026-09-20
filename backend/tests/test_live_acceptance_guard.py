"""真实验收工具的保护栏测试；此处绝不访问外部模型。"""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fastapi import HTTPException
from scripts.accept_basic_live import Acceptance


class AcceptanceGuardTests(unittest.TestCase):
    def test_budget_stops_before_the_next_network_call(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = Acceptance(Path(directory), 1)
            llm = SimpleNamespace(model_name='fixture', invoke=Mock(return_value=
                SimpleNamespace(content='{"ok":true}', usage_metadata={'total_tokens': 4})))
            recorded = audit.instrument(lambda **_: llm)(role='test')
            recorded.invoke('synthetic input')
            self.assertEqual(audit.calls[0]['status'], 'complete')
            self.assertEqual(audit.calls[0]['usage']['total_tokens'], 4)
            with self.assertRaises(HTTPException) as error:
                recorded.invoke('not sent')
            self.assertEqual(error.exception.status_code, 429)
            self.assertEqual(llm.invoke.call_count, 1)

    def test_stream_records_all_chunks_and_redacts_exception_body(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = Acceptance(Path(directory), 2)
            def broken_stream(_):
                yield SimpleNamespace(content='partial')
                raise RuntimeError('provider-secret-must-not-be-logged')
            llm = SimpleNamespace(model_name='fixture', stream=broken_stream)
            recorded = audit.instrument(lambda **_: llm)(role='test')
            with self.assertRaises(RuntimeError):
                list(recorded.stream('synthetic input'))
            self.assertEqual(audit.calls[0]['status'], 'failed')
            self.assertNotIn('provider-secret', json.dumps(audit.calls))
            parts = json.loads((Path(directory) / 'model-output-1.json').read_text())
            self.assertEqual(parts, ['partial'])

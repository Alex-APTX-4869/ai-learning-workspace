import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app import create_app
from backend.database import Base, get_db
from backend.providers.models import LLMModelConfig, LlmProvider
from backend.providers.routing import initial_capabilities
from backend.providers.schemas import ModelCapabilityDeclaration
from backend.providers.schemas import ModelRuntimePolicy
from backend.providers import probes


class ProviderProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{self.temp.name}/test.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        app = create_app(initialize_database=False, inline_jobs=True)

        def database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        with Session(self.engine) as db:
            provider = LlmProvider(
                name="检测连接", base_url="https://example.test/v1",
                model="chat-a", key_ref="internal-ref", is_active=False,
            )
            db.add(provider)
            db.flush()
            model = LLMModelConfig(
                provider_id=provider.id, label="综合模型", model="chat-a",
                capabilities_json=initial_capabilities(ModelCapabilityDeclaration(
                    text_chat=True, structured_output=True, streaming=True,
                    vision=True, embeddings=False,
                )), runtime_policy_json={}, is_enabled=True, revision=1,
            )
            db.add(model)
            db.commit()
            self.model_id = model.id

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    @patch("backend.providers.probes.secrets.get_api_key", return_value="SECRET_SENTINEL")
    @patch("backend.providers.probes._run_probe")
    def test_server_probe_records_results_without_exposing_secret(self, run_probe, _key):
        def outcome(capability, **_):
            if capability == "vision":
                raise RuntimeError("provider body SECRET_SENTINEL")
        run_probe.side_effect = outcome
        reply = self.client.post(
            f"/llm-models/{self.model_id}/verify",
            json={"expected_revision": 1, "capabilities": ["text_chat", "vision"]},
        )
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertNotIn("SECRET_SENTINEL", reply.text)
        body = reply.json()
        self.assertEqual(body["capabilities"]["text_chat"]["status"], "verified")
        self.assertEqual(body["capabilities"]["vision"]["status"], "failed")
        self.assertEqual(body["capabilities"]["vision"]["error_code"], "provider_request_failed")
        self.assertEqual(body["revision"], 2)

    @patch("backend.providers.probes.secrets.get_api_key", return_value="secret")
    @patch("backend.providers.probes._run_probe")
    def test_probe_uses_cas_and_rejects_undeclared_capability(self, run_probe, _key):
        rejected = self.client.post(
            f"/llm-models/{self.model_id}/verify",
            json={"expected_revision": 1, "capabilities": ["embeddings"]},
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)
        run_probe.assert_not_called()
        stale = self.client.post(
            f"/llm-models/{self.model_id}/verify",
            json={"expected_revision": 9, "capabilities": ["text_chat"]},
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        run_probe.assert_not_called()

    @patch("backend.providers.probes._chat_model")
    def test_vision_requires_correct_image_content(self, model):
        kwargs = dict(base_url="http://127.0.0.1/v1", model="test", api_key="test", policy=ModelRuntimePolicy())
        model.return_value.invoke.return_value = Mock(content="OK")
        with self.assertRaises(ValueError):
            probes._run_probe("vision", **kwargs)
        image, expected = probes._vision_challenge()
        import json
        with patch.object(probes, "_vision_challenge", return_value=(image, expected)):
            model.return_value.invoke.return_value = Mock(content=json.dumps(expected))
            probes._run_probe("vision", **kwargs)
        self.assertIn("image_url", model.return_value.invoke.call_args.args[0][0].content[1])

    @patch("backend.providers.probes.ChatOpenAI")
    def test_probe_budget_capped_and_stream_closed(self, chat):
        closed = []
        def chunks():
            try:
                yield Mock(content="OK")
                yield Mock(content=".")
            finally:
                closed.append(True)
        chat.return_value.stream.return_value = chunks()
        probes._run_probe("streaming", base_url="http://127.0.0.1/v1", model="test", api_key="test",
                          policy=ModelRuntimePolicy(request_timeout_seconds=600, max_output_tokens=10000))
        self.assertEqual(chat.call_args.kwargs["timeout"], 30)
        self.assertEqual(chat.call_args.kwargs["max_completion_tokens"], 256)
        self.assertEqual(closed, [True])

    @patch("backend.providers.probes.secrets.get_api_key", return_value="secret")
    @patch("backend.providers.probes._run_probe")
    def test_configuration_change_during_probe_does_not_save_stale_result(self, run_probe, _key):
        def change(*_, **__):
            with Session(self.engine) as db:
                row = db.get(LLMModelConfig, self.model_id)
                row.model = "changed"
                row.revision += 1
                db.commit()
        run_probe.side_effect = change
        reply = self.client.post(f"/llm-models/{self.model_id}/verify",
                                 json={"expected_revision": 1, "capabilities": ["text_chat"]})
        self.assertEqual(reply.status_code, 409, reply.text)
        with Session(self.engine) as db:
            self.assertEqual(db.get(LLMModelConfig, self.model_id).capabilities_json["text_chat"]["status"], "unverified")


if __name__ == "__main__":
    unittest.main()

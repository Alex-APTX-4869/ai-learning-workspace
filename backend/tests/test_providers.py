import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app import create_app
from backend.database import Base, get_db
from backend.providers import service
from backend.providers.models import LlmProvider
from backend.providers.schemas import ProviderCreate


class ProviderTests(unittest.TestCase):
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
        self.key_store = {}
        self.patchers = [
            patch(
                "backend.providers.service.nus_settings",
                return_value=("ENV_SECRET_SENTINEL", "https://nus.example/v1", "qwen"),
            ),
            patch(
                "backend.providers.service.secrets.set_api_key",
                side_effect=lambda ref, key: self.key_store.__setitem__(ref, key),
            ),
            patch(
                "backend.providers.service.secrets.get_api_key",
                side_effect=lambda ref: self.key_store[ref],
            ),
            patch(
                "backend.providers.service.secrets.delete_api_key",
                side_effect=lambda ref: self.key_store.pop(ref, None),
            ),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in reversed(self.patchers):
            item.stop()
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def create_provider(self, *, activate=False, key="SAVED_SECRET_SENTINEL"):
        reply = self.client.post(
            "/llm-providers",
            json={
                "name": "本地模型",
                "base_url": "http://localhost:11434/v1",
                "model": "local-model",
                "api_key": key,
                "activate": activate,
            },
        )
        self.assertEqual(reply.status_code, 201, reply.text)
        return reply

    def test_key_is_only_in_key_store_and_never_in_api_or_runtime_repr(self):
        sentinel = "SAVED_SECRET_SENTINEL"
        reply = self.create_provider(key=sentinel)
        self.assertNotIn(sentinel, reply.text)
        payload = reply.json()
        self.assertTrue(payload["has_api_key"])
        with Session(self.engine) as db:
            row = db.get(LlmProvider, payload["id"])
            self.assertNotEqual(row.key_ref, sentinel)
            self.assertNotIn(sentinel, repr(row.__dict__))
            self.assertEqual(self.key_store[row.key_ref], sentinel)

        self.assertNotIn(sentinel, self.client.get("/llm-providers").text)
        with patch("backend.providers.service.get_engine", return_value=self.engine):
            self.client.post(f'/llm-providers/{payload["id"]}/activate')
            runtime = service.resolve_active_provider()
        self.assertEqual(runtime.api_key.get_secret_value(), sentinel)
        self.assertNotIn(sentinel, repr(runtime))
        self.assertNotIn(sentinel, runtime.model_dump_json())

    def test_environment_fallback_saved_activation_and_switch_back(self):
        listed = self.client.get("/llm-providers").json()
        self.assertEqual(listed[0]["source"], "environment")
        self.assertTrue(listed[0]["is_active"])
        saved = self.create_provider(activate=False).json()
        self.assertEqual(self.client.get("/llm-providers/active").json()["source"], "environment")

        activated = self.client.post(f'/llm-providers/{saved["id"]}/activate')
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertEqual(activated.json()["source"], "saved")
        self.assertEqual(self.client.get("/llm-providers/active").json()["id"], saved["id"])

        environment = self.client.post("/llm-providers/environment/activate")
        self.assertEqual(environment.status_code, 200, environment.text)
        self.assertEqual(environment.json()["source"], "environment")
        with Session(self.engine) as db:
            self.assertFalse(db.get(LlmProvider, saved["id"]).is_active)
        with patch("backend.providers.service.get_engine", return_value=self.engine):
            runtime = service.resolve_active_provider()
        self.assertEqual(runtime.source, "environment")
        self.assertEqual(runtime.api_key.get_secret_value(), "ENV_SECRET_SENTINEL")

    def test_validation_errors_remove_all_inputs_and_secrets(self):
        sentinels = [
            "BODY_SECRET_SENTINEL",
            "CAMEL_SECRET_SENTINEL",
            "PASSWORD_SECRET_SENTINEL",
            "QUERY_SECRET_SENTINEL",
        ]
        cases = [
            {
                "base_url": "https://example.com/v1",
                "model": "model",
                "api_key": sentinels[0],
                "apiKey": sentinels[1],
            },
            {
                "name": "x",
                "base_url": f"https://user:{sentinels[2]}@example.com:bad/v1",
                "model": "model",
                "api_key": sentinels[0],
            },
            {
                "name": "x",
                "base_url": f"https://example.com/v1?api_key={sentinels[3]}",
                "model": "model",
                "api_key": sentinels[0],
            },
        ]
        for body in cases:
            with self.subTest(body=body.get("base_url")):
                reply = self.client.post("/llm-providers", json=body)
                self.assertEqual(reply.status_code, 422, reply.text)
                self.assertNotIn('"input"', reply.text)
                self.assertNotIn('"ctx"', reply.text)
                for sentinel in sentinels:
                    self.assertNotIn(sentinel, reply.text)

    def test_url_boundary_allows_secure_remote_and_loopback_http_only(self):
        accepted = [
            "https://example.com/v1",
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
            "http://[::1]:11434/v1",
        ]
        for url in accepted:
            with self.subTest(accepted=url):
                value = ProviderCreate(
                    name="x", base_url=url, model="m", api_key="secret", activate=False
                )
                self.assertEqual(value.base_url.scheme, url.split(":", 1)[0])

        rejected = [
            "http://example.com/v1",
            "ftp://example.com/v1",
            "https://user:password@example.com/v1",
            "https://example.com/v1?region=sg",
            "https://example.com/v1#models",
        ]
        for url in rejected:
            with self.subTest(rejected=url), self.assertRaises(ValidationError):
                ProviderCreate(name="x", base_url=url, model="m", api_key="secret")

    def test_create_and_activate_do_not_contact_model(self):
        with patch("backend.ai.client.ChatOpenAI") as model:
            saved = self.create_provider(activate=False).json()
            self.client.get("/llm-providers")
            self.client.post(f'/llm-providers/{saved["id"]}/activate')
            model.assert_not_called()

    def test_missing_environment_is_clean_and_saved_provider_still_lists(self):
        self.create_provider(activate=False)
        with patch(
            "backend.providers.service.nus_settings",
            side_effect=RuntimeError("missing env"),
        ):
            listed = self.client.get("/llm-providers")
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(len(listed.json()), 1)
            self.assertEqual(self.client.get("/llm-providers/active").status_code, 404)
            self.assertEqual(
                self.client.post("/llm-providers/environment/activate").status_code,
                404,
            )


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# 导入 app 以登记所有外键相关的 SQLAlchemy 模型。
from backend import app as _app  # noqa: F401
from backend.ai import client as ai_client
from backend.database import Base
from backend.providers import routing
from backend.providers.models import LLMModelConfig, LLMRoleBinding, LlmProvider


class RouteSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{self.temp.name}/snapshot.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            first_provider = LlmProvider(
                name="first",
                base_url="https://first.example/v1",
                model="legacy-first",
                key_ref="first-key-ref",
                is_active=False,
            )
            second_provider = LlmProvider(
                name="second",
                base_url="https://second.example/v1",
                model="legacy-second",
                key_ref="second-key-ref",
                is_active=False,
            )
            db.add_all([first_provider, second_provider])
            db.flush()
            first_model = LLMModelConfig(
                provider_id=first_provider.id,
                label="first-model",
                model="model-before",
                capabilities_json=routing.legacy_capabilities(),
                runtime_policy_json={"temperature": 0.2, "request_timeout_seconds": 91},
                is_enabled=True,
                revision=1,
            )
            second_model = LLMModelConfig(
                provider_id=second_provider.id,
                label="second-model",
                model="model-after",
                capabilities_json=routing.legacy_capabilities(),
                runtime_policy_json={"temperature": 0.8},
                is_enabled=True,
                revision=1,
            )
            db.add_all([first_model, second_model])
            db.flush()
            db.add(
                LLMRoleBinding(
                    scope_type="global",
                    scope_id=None,
                    scope_key="global",
                    role_key="content.lesson",
                    model_config_id=first_model.id,
                    revision=1,
                )
            )
            db.commit()
            self.first_provider_id = first_provider.id
            self.second_model_id = second_model.id

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def test_snapshot_keeps_original_route_after_binding_changes(self):
        with Session(self.engine) as db:
            snapshot = routing.resolve_routing_snapshot(
                db, ["content.lesson"], scope_type="global"
            )
        frozen = snapshot["routes"]["content.lesson"]
        original_fingerprint = frozen["config_fingerprint"]

        # 模拟任务已排队后，用户把同一职责改到另一连接。
        with Session(self.engine) as db:
            binding = db.scalar(
                select(LLMRoleBinding).where(
                    LLMRoleBinding.role_key == "content.lesson"
                )
            )
            binding.model_config_id = self.second_model_id
            binding.revision += 1
            db.commit()

        keys = {
            "first-key-ref": "FIRST_SECRET_SENTINEL",
            "second-key-ref": "SECOND_SECRET_SENTINEL",
        }
        with (
            patch("backend.providers.routing.get_engine", return_value=self.engine),
            patch(
                "backend.providers.routing.secrets.get_api_key",
                side_effect=lambda key_ref: keys[key_ref],
            ),
        ):
            runtime = routing.runtime_from_snapshot(frozen)
            self.assertEqual(runtime.model, "model-before")
            self.assertEqual(runtime.base_url, "https://first.example/v1")
            self.assertEqual(runtime.config_fingerprint, original_fingerprint)
            self.assertEqual(
                runtime.api_key.get_secret_value(), "FIRST_SECRET_SENTINEL"
            )

            with patch("backend.ai.client.ChatOpenAI") as chat_model:
                ai_client.get_llm(
                    role="content.lesson", snapshot=snapshot
                )
            kwargs = chat_model.call_args.kwargs
            self.assertEqual(kwargs["model"], "model-before")
            self.assertEqual(kwargs["base_url"], "https://first.example/v1")
            self.assertEqual(kwargs["temperature"], 0.2)
            self.assertEqual(kwargs["timeout"], 91)

        serialized = json.dumps(snapshot, ensure_ascii=False)
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertNotIn("FIRST_SECRET_SENTINEL", serialized)
        self.assertNotIn("first-key-ref", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("key_ref", serialized)

    def test_environment_snapshot_freezes_public_config_but_uses_current_key(self):
        with Session(self.engine) as db:
            db.query(LLMRoleBinding).delete()
            with patch(
                "backend.providers.service.nus_settings",
                return_value=(
                    "OLD_ENV_SECRET",
                    "https://old-env.example/v1",
                    "old-env-model",
                ),
            ):
                snapshot = routing.resolve_routing_snapshot(
                    db, ["intake.explain"], scope_type="global"
                )

        route = snapshot["routes"]["intake.explain"]
        with patch(
            "backend.providers.service.nus_settings",
            return_value=(
                "ROTATED_ENV_SECRET",
                "https://changed-env.example/v1",
                "changed-env-model",
            ),
        ):
            runtime = routing.runtime_from_snapshot(route)

        self.assertEqual(runtime.base_url, "https://old-env.example/v1")
        self.assertEqual(runtime.model, "old-env-model")
        self.assertEqual(
            runtime.api_key.get_secret_value(), "ROTATED_ENV_SECRET"
        )


if __name__ == "__main__":
    unittest.main()

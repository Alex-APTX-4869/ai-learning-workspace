import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app import create_app
from backend.courses.models import Course
from backend.database import Base, get_db
from backend.providers import routing
from backend.providers.models import LLMModelConfig, LLMRoleBinding


class ModelRoutingTests(unittest.TestCase):
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
        self.key_store: dict[str, str] = {}
        self.patchers = [
            patch(
                "backend.providers.service.nus_settings",
                return_value=("ENV_SECRET", "https://env.example/v1", "env-model"),
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
        for patcher in self.patchers:
            patcher.start()
        reply = self.client.post(
            "/llm-providers",
            json={
                "name": "测试连接",
                "base_url": "https://provider.example/v1",
                "model": "model-a",
                "api_key": "ROUTING_SECRET_SENTINEL",
                "activate": True,
            },
        )
        self.assertEqual(reply.status_code, 201, reply.text)
        self.provider_id = reply.json()["id"]

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def models(self):
        return self.client.get(
            f"/llm-providers/{self.provider_id}/models"
        ).json()

    def create_model(self, name: str, **capabilities):
        reply = self.client.post(
            f"/llm-providers/{self.provider_id}/models",
            json={
                "label": name,
                "model": name,
                "capabilities": {"text_chat": True, **capabilities},
            },
        )
        self.assertEqual(reply.status_code, 201, reply.text)
        return reply.json()

    def bind(self, role: str, model_id: int, *, scope_type="global", scope_id=None, revision=0):
        body = {
            "scope_type": scope_type,
            "model_config_id": model_id,
            "expected_revision": revision,
        }
        if scope_id is not None:
            body["scope_id"] = str(scope_id)
        return self.client.put(f"/llm-role-bindings/{role}", json=body)

    def test_legacy_provider_creation_also_creates_first_model_without_secret(self):
        models = self.models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["model"], "model-a")
        self.assertTrue(models[0]["capabilities"]["streaming"]["supported"])
        serialized = json.dumps(models)
        self.assertNotIn("ROUTING_SECRET_SENTINEL", serialized)
        self.assertNotIn("key_ref", serialized)

    def test_fixed_roles_expose_streaming_requirement_for_outline(self):
        reply = self.client.get("/llm-roles")
        self.assertEqual(reply.status_code, 200, reply.text)
        roles = {item["key"]: item for item in reply.json()}
        self.assertIn("retrieval.embed", roles)
        self.assertEqual(
            roles["outline.generate"]["required_capabilities"],
            ["text_chat", "structured_output", "streaming"],
        )
        self.assertEqual(roles["materials.vision"]["name"], "文档识别")
        self.assertEqual(roles["materials.vision"]["default_role"], "default.vision")
        self.assertEqual(roles["materials.vision"]["required_capabilities"],
                         ["text_chat", "structured_output", "vision"])

    def test_resolution_priority_course_role_then_course_default_then_global_role_then_default(self):
        with Session(self.engine) as db:
            course = Course(name="课程", intro="简介")
            db.add(course)
            db.commit()
            course_id = course.id
        first = self.models()[0]
        global_role = self.create_model("global-role", structured_output=True, streaming=True)
        course_default = self.create_model("course-default", structured_output=True, streaming=True)
        course_role = self.create_model("course-role", structured_output=True, streaming=True)
        bindings = [
            self.bind("outline.generate", global_role["id"]),
            self.bind("default.chat", course_default["id"], scope_type="course", scope_id=course_id),
            self.bind("outline.generate", course_role["id"], scope_type="course", scope_id=course_id),
        ]
        for reply in bindings:
            self.assertEqual(reply.status_code, 200, reply.text)

        def resolved_model():
            return self.client.get(
                "/llm-role-routing/outline.generate",
                params={"scope_type": "course", "scope_id": course_id},
            ).json()["model"]

        self.assertEqual(resolved_model(), "course-role")
        self.client.delete(
            "/llm-role-bindings/outline.generate",
            params={"scope_type": "course", "scope_id": course_id, "expected_revision": 1},
        )
        self.assertEqual(resolved_model(), "course-default")
        self.client.delete(
            "/llm-role-bindings/default.chat",
            params={"scope_type": "course", "scope_id": course_id, "expected_revision": 1},
        )
        self.assertEqual(resolved_model(), "global-role")
        self.client.delete(
            "/llm-role-bindings/outline.generate",
            params={"scope_type": "global", "expected_revision": 1},
        )
        self.assertEqual(resolved_model(), "model-a")

    def test_binding_uses_compare_and_swap_revision(self):
        model_id = self.models()[0]["id"]
        stale = self.bind("default.chat", model_id, revision=0)
        self.assertEqual(stale.status_code, 409, stale.text)
        updated = self.bind("default.chat", model_id, revision=1)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["revision"], 2)

    def test_legacy_activation_updates_only_global_default_chat_binding(self):
        second = self.client.post(
            "/llm-providers",
            json={
                "name": "第二连接",
                "base_url": "https://second.example/v1",
                "model": "second-model",
                "api_key": "SECOND_SECRET_SENTINEL",
                "activate": False,
            },
        ).json()
        second_model = self.client.get(
            f'/llm-providers/{second["id"]}/models'
        ).json()[0]
        role_model = self.create_model("outline-special", structured_output=True, streaming=True)
        self.assertEqual(self.bind("outline.generate", role_model["id"]).status_code, 200)
        activated = self.client.post(f'/llm-providers/{second["id"]}/activate')
        self.assertEqual(activated.status_code, 200, activated.text)
        default_route = self.client.get("/llm-role-routing/intake.explain").json()
        outline_route = self.client.get("/llm-role-routing/outline.generate").json()
        self.assertEqual(default_route["model_config_id"], second_model["id"])
        self.assertEqual(outline_route["model_config_id"], role_model["id"])
        environment = self.client.post("/llm-providers/environment/activate")
        self.assertEqual(environment.status_code, 200, environment.text)
        bindings = self.client.get("/llm-role-bindings").json()
        self.assertEqual([item["role_key"] for item in bindings], ["outline.generate"])

    def test_unverified_vision_cannot_bind_until_server_records_real_probe(self):
        model = self.create_model(
            "vision-model", structured_output=True, vision=True
        )
        rejected = self.bind("materials.vision", model["id"])
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertIn("尚未验证", rejected.text)
        with Session(self.engine) as db:
            routing.record_capability_verification(
                db, model["id"], "vision", status="verified"
            )
            db.commit()
        accepted = self.bind("materials.vision", model["id"])
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_client_cannot_self_report_verified_capability(self):
        model = self.create_model("vision-no-self-report", vision=True)
        reply = self.client.post(
            f'/llm-models/{model["id"]}/capabilities/vision',
            json={"expected_revision": model["revision"], "status": "verified"},
        )
        self.assertIn(reply.status_code, {404, 405})
        current = self.client.get(f'/llm-models/{model["id"]}').json()
        self.assertEqual(current["capabilities"]["vision"]["status"], "unverified")

    def test_document_assignment_does_not_replace_summary_or_chat_models(self):
        model = self.create_model("document-vision", structured_output=True, vision=True)
        with Session(self.engine) as db:
            routing.record_capability_verification(db, model["id"], "vision", status="verified")
            db.commit()
        self.assertEqual(self.bind("materials.vision", model["id"]).status_code, 200)
        document = self.client.get("/llm-role-routing/materials.vision").json()
        summary = self.client.get("/llm-role-routing/materials.summarize").json()
        chat = self.client.get("/llm-role-routing/intake.interview").json()
        self.assertEqual(document["model_config_id"], model["id"])
        self.assertEqual(summary["model"], "model-a")
        self.assertEqual(chat["model"], "model-a")
        # 仅删除专项绑定，原来的默认文本职责不变。
        reply = self.client.delete("/llm-role-bindings/materials.vision",
                                   params={"scope_type": "global", "expected_revision": 1})
        self.assertEqual(reply.status_code, 204)
        self.assertEqual(self.client.get("/llm-role-routing/materials.summarize").json()["model"], "model-a")

    def test_resolved_snapshot_and_runtime_never_expose_secret_or_key_reference(self):
        public = self.client.get("/llm-role-routing/intake.explain")
        self.assertEqual(public.status_code, 200, public.text)
        self.assertEqual(len(public.json()["config_fingerprint"]), 64)
        self.assertNotIn("ROUTING_SECRET_SENTINEL", public.text)
        self.assertNotIn("key_ref", public.text)
        with patch("backend.providers.routing.get_engine", return_value=self.engine):
            runtime = routing.resolve_role_runtime("intake.explain")
        self.assertEqual(
            runtime.api_key.get_secret_value(), "ROUTING_SECRET_SENTINEL"
        )
        self.assertNotIn("ROUTING_SECRET_SENTINEL", repr(runtime))
        self.assertNotIn("ROUTING_SECRET_SENTINEL", runtime.model_dump_json())
        self.assertNotIn("key_ref", repr(runtime))


if __name__ == "__main__":
    unittest.main()

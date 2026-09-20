from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from backend.app import create_app
from backend.database import Base
from backend.migrations.runner import (
    M1_REVISION,
    M2_REVISION,
    M3_REVISION,
    M4_REVISION,
    M5_REVISION,
    M6_REVISION,
    M7_REVISION,
    MIGRATIONS,
    ROUTING_SNAPSHOT_TABLES,
    migrate,
    registry,
    registry_metadata,
)


class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 确保所有 model 已登记到 Base.metadata。
        create_app(initialize_database=False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp.name) / 'migration.db'}"
        )

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def _insert_legacy_rows(self, conn) -> None:
        """插入 M2 之前已终止的业务记录，之后删列模拟真实旧库。"""
        now = datetime.now(timezone.utc)
        table = Base.metadata.tables
        conn.execute(table["llm_providers"].insert().values(
            id=1,
            name="Legacy provider",
            base_url="https://example.invalid/v1",
            model="legacy-chat-model",
            key_ref="credential-reference-must-not-be-copied",
            is_active=True,
        ))
        conn.execute(table["courses"].insert().values(
            id=1, name="Legacy course", intro="Before model routing"
        ))
        conn.execute(table["chapters"].insert().values(
            id=1, course_id=1, name="Chapter", position=0
        ))
        conn.execute(table["sections"].insert().values(
            id=1, chapter_id=1, name="Section", position=0,
            content_markdown=None,
        ))
        conn.execute(table["points"].insert().values(
            id=1, section_id=1, name="Point", intro="Intro", position=0,
            content_markdown=None,
        ))
        conn.execute(table["intake_sessions"].insert().values(
            id=1,
            initial_name="Legacy course",
            initial_intro="Legacy intake",
            status="completed",
            depth_options=[],
            selected_depth=None,
            question_count=0,
            current_question=None,
            brief={"summary": "done"},
            course_id=None,
            version=1,
        ))
        conn.execute(table["outline_versions"].insert().values(
            id=1,
            course_id=1,
            version_number=1,
            name="Legacy outline",
            outline_json={"name": "Legacy outline", "chapters": []},
            additional_requirements="",
            reference_version_id=None,
            created_at=now,
        ))
        conn.execute(table["directory_manifests"].insert().values(
            version_id=1,
            course_id=1,
            base_version_id=None,
            tree_json={"id": 1, "name": "Legacy course", "chapters": []},
            brief_json=None,
            origin="legacy",
            created_at=now,
        ))
        conn.execute(table["point_content_versions"].insert().values(
            id=1,
            point_id=1,
            plan_id=None,
            version_number=1,
            status="ready",
            origin="generated",
            content_json={"cards": []},
            review_json={},
            revision_count=0,
            context_hash="c" * 64,
            created_at=now,
        ))
        conn.execute(table["learning_generation_jobs"].insert().values(
            id=1,
            course_id=1,
            section_id=1,
            point_id=1,
            outline_version_id=1,
            status="ready",
            revision_count=0,
            plan_id=None,
            content_version_id=1,
            context_hash="c" * 64,
            structure_hash="s" * 64,
            context_json={},
            expected_selected_version_id=None,
            error_code=None,
            error=None,
            created_at=now,
            updated_at=now,
        ))
        conn.execute(table["version_tutor_sessions"].insert().values(
            id=1,
            course_id=1,
            point_id=1,
            outline_version_id=1,
            content_version_id=1,
            card_index=0,
            revision=0,
            completed=True,
            pending_request_id=None,
            responses={},
        ))
        conn.execute(table["version_tutor_turns"].insert().values(
            id=1,
            session_id=1,
            request_id="00000000-0000-0000-0000-000000000001",
            payload_hash="p" * 64,
            revision_before=0,
            card_id="card-1",
            action="message",
            status="ready",
            user_message="done",
            reply_markdown="done",
            error=None,
            teacher_action="stay",
        ))
        conn.execute(table["directory_drafts"].insert().values(
            id="00000000-0000-0000-0000-000000000001",
            course_id=1,
            base_version_id=1,
            revision=1,
            status="published",
            additions_json=[],
            published_version_id=1,
            created_at=now,
        ))

    def _install_legacy_m1(self, *, with_rows: bool = True) -> None:
        """只登记 M1，并去掉当前 model 中属于 M2 的列。"""
        with self.engine.begin() as conn:
            registry_metadata.create_all(conn)
            MIGRATIONS[0].apply(conn)
            MIGRATIONS[0].verify(conn)
            if with_rows:
                self._insert_legacy_rows(conn)
            for table_name in ROUTING_SNAPSHOT_TABLES:
                conn.execute(text(
                    f"ALTER TABLE {table_name} DROP COLUMN routing_snapshot_json"
                ))
            conn.execute(registry.insert().values(
                revision=M1_REVISION,
                applied_at=datetime.now(timezone.utc),
            ))

    def test_fresh_migration_is_ordered_and_idempotent(self):
        first = migrate(self.engine)
        second = migrate(self.engine)
        self.assertTrue(first["applied"])
        self.assertEqual(first["revision"], M7_REVISION)
        self.assertEqual(
            first["applied_revisions"], [M1_REVISION, M2_REVISION, M3_REVISION, M4_REVISION, M5_REVISION, M6_REVISION, M7_REVISION]
        )
        self.assertFalse(second["applied"])
        self.assertEqual(second["applied_revisions"], [])

    def test_m2_backfills_public_model_identity_without_credentials(self):
        self._install_legacy_m1()

        first = migrate(self.engine)
        second = migrate(self.engine)

        self.assertEqual(first["applied_revisions"], [M2_REVISION, M3_REVISION, M4_REVISION, M5_REVISION, M6_REVISION, M7_REVISION])
        self.assertFalse(second["applied"])
        with self.engine.connect() as conn:
            models = conn.execute(text(
                "SELECT provider_id, label, model, capabilities_json, "
                "runtime_policy_json, is_enabled, revision "
                "FROM llm_model_configs"
            )).mappings().all()
            bindings = conn.execute(text(
                "SELECT scope_type, scope_id, scope_key, role_key, "
                "model_config_id, revision FROM llm_role_bindings"
            )).mappings().all()
            self.assertEqual(len(models), 1)
            self.assertEqual(models[0]["provider_id"], 1)
            self.assertEqual(models[0]["model"], "legacy-chat-model")
            self.assertNotIn(
                "credential-reference-must-not-be-copied", repr(dict(models[0]))
            )
            self.assertEqual(len(bindings), 1)
            self.assertEqual(bindings[0]["scope_key"], "global")
            self.assertEqual(bindings[0]["role_key"], "default.chat")
            self.assertIsNone(bindings[0]["scope_id"])

            for table_name in ROUTING_SNAPSHOT_TABLES:
                value = conn.execute(text(
                    f"SELECT routing_snapshot_json FROM {table_name} LIMIT 1"
                )).scalar_one()
                self.assertIsNone(value, table_name)

    def test_m2_refuses_active_learning_job_and_tutor_turn(self):
        self._install_legacy_m1()
        with self.engine.begin() as conn:
            conn.execute(text(
                "UPDATE learning_generation_jobs SET status = 'queued' WHERE id = 1"
            ))
        with self.assertRaisesRegex(RuntimeError, "内容生成任务"):
            migrate(self.engine)

        with self.engine.begin() as conn:
            self.assertNotIn("llm_model_configs", inspect(conn).get_table_names())
            conn.execute(text(
                "UPDATE learning_generation_jobs SET status = 'ready' WHERE id = 1"
            ))
            conn.execute(text(
                "UPDATE version_tutor_turns SET status = 'running' WHERE id = 1"
            ))
        with self.assertRaisesRegex(RuntimeError, "讲师答疑"):
            migrate(self.engine)

        with self.engine.begin() as conn:
            self.assertNotIn("llm_model_configs", inspect(conn).get_table_names())
            conn.execute(text(
                "UPDATE version_tutor_turns SET status = 'ready' WHERE id = 1"
            ))
        self.assertEqual(migrate(self.engine)["applied_revisions"], [M2_REVISION, M3_REVISION, M4_REVISION, M5_REVISION, M6_REVISION, M7_REVISION])

    def test_recorded_revision_does_not_silently_recreate_m2_structure(self):
        migrate(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("DROP TABLE llm_role_bindings"))
        with self.assertRaisesRegex(RuntimeError, "llm_role_bindings"):
            migrate(self.engine)

    def test_recorded_revision_does_not_silently_restore_snapshot_column(self):
        migrate(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE intake_sessions DROP COLUMN routing_snapshot_json"
            ))
        with self.assertRaisesRegex(RuntimeError, "intake_sessions"):
            migrate(self.engine)


if __name__ == "__main__":
    unittest.main()

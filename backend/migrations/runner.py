from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, inspect, select, text
from sqlalchemy.orm import Session

from backend.database import Base
from backend.courses.models import Course
from backend.intake.models import IntakeSession
from backend.learning.models import LearningGenerationJob
from backend.outlines.models import OutlineVersion
from backend.providers.models import LLMModelConfig, LLMRoleBinding, LlmProvider
from backend.tutor.models import TutorSession, TutorTurn
from backend.versions.models import DirectoryDraft
from backend.versions import service
from backend.materials import models as _material_models
from backend.materials.vision_models import PageRecognition, PageAdoption
from backend.versions.material_models import DraftMaterialBinding


registry_metadata = MetaData()
registry = Table("app_schema_migrations", registry_metadata,
                 Column("revision", String(80), primary_key=True),
                 Column("applied_at", DateTime(timezone=True), nullable=False))
M1_REVISION = "20260908_01_directory_manifests"
M2_REVISION = "20260908_02_model_routing"
M3_REVISION = "20260909_03_material_batches"
M4_REVISION = "20260909_04_intake_extensions"
M5_REVISION = "20260914_05_page_recognition"
M6_REVISION = "20260915_06_page_adoption"
M7_REVISION = "20260915_07_draft_materials"
M3_TABLES = ("material_batches", "material_files", "material_processes", "material_analysis_steps")

# 这是 M1 发布时已经存在的完整表集合。必须冻结在 revision 内，不能对
# Base.metadata 无条件 create_all；否则以后新增 M2 model 会绕过 M2 迁移。
M1_TABLES = (
    "courses", "chapters", "sections", "points", "intake_sessions",
    "intake_turns", "llm_providers", "outline_versions",
    "course_outline_selections", "section_plans", "point_content_versions",
    "point_content_selections", "learning_generation_jobs",
    "directory_manifests", "directory_content_selections", "directory_drafts",
    "learning_job_steps", "version_tutor_sessions", "version_tutor_turns",
)

M2_TABLES = ("llm_model_configs", "llm_role_bindings")
ROUTING_SNAPSHOT_TABLES = (
    "intake_sessions",
    "outline_versions",
    "learning_generation_jobs",
    "version_tutor_turns",
    "directory_drafts",
)
ACTIVE_LEARNING_STATUSES = (
    "queued",
    "planning",
    "writing",
    "reviewing",
    "revising",
    "needs_attention",
)


@dataclass(frozen=True)
class Migration:
    revision: str
    apply: Callable
    verify: Callable


def _copy_tutor_history(db: Session):
    conn = db.connection()
    names = inspect(conn).get_table_names()
    if "tutor_sessions" not in names:
        return
    metadata = MetaData()
    old_sessions = Table("tutor_sessions", metadata, autoload_with=conn)
    old_turns = Table("tutor_turns", metadata, autoload_with=conn)
    for row in conn.execute(select(old_sessions)).mappings():
        if row["pending_request_id"] is not None:
            raise RuntimeError("存在未结束的旧讲师会话，请等待任务结束后迁移。")
        if db.get(TutorSession, row["id"]) is not None:
            raise RuntimeError("新会话表已有重叠 ID，停止迁移以免覆盖。")
        from backend.learning.models import PointContentVersion
        content = db.get(PointContentVersion, row["content_version_id"])
        if content is None or content.point_id != row["point_id"] or content.status != "ready":
            raise RuntimeError("旧讲师会话引用了不匹配或未就绪的内容版本，停止迁移。")
        outline_id = service.selected_id(db, row["course_id"])
        if outline_id:
            manifest = service.get_manifest(db, row["course_id"], outline_id)
            if row["point_id"] not in service.point_ids(manifest.tree_json):
                outline_id = None
        db.add(TutorSession(**dict(row), outline_version_id=outline_id))
    db.flush()
    for row in conn.execute(select(old_turns)).mappings():
        db.add(TutorTurn(**dict(row)))
    db.flush()
    if conn.dialect.name == "postgresql":
        for table in ("version_tutor_sessions", "version_tutor_turns"):
            # 表名固定，不接受用户输入；显式复制 ID 后修正自增序列。
            conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), EXISTS(SELECT 1 FROM {table}))"))


def _apply_m1(conn) -> None:
    existing = inspect(conn).get_table_names()
    if "learning_generation_jobs" in existing:
        count = conn.execute(text(
            "SELECT count(*) FROM learning_generation_jobs "
            "WHERE status IN ('queued','planning','writing','reviewing','revising','needs_attention')"
        )).scalar()
        if count:
            raise RuntimeError("存在活动的旧内容生成任务，请等待任务结束后迁移。")

    missing_models = [name for name in M1_TABLES if name not in Base.metadata.tables]
    if missing_models:
        raise RuntimeError(f"M1 迁移模型登记不完整：{', '.join(missing_models)}")
    Base.metadata.create_all(
        conn, tables=[Base.metadata.tables[name] for name in M1_TABLES]
    )
    job_columns = {
        column["name"]
        for column in inspect(conn).get_columns("learning_generation_jobs")
    }
    if "outline_version_id" not in job_columns:
        conn.execute(text(
            "ALTER TABLE learning_generation_jobs ADD COLUMN "
            "outline_version_id INTEGER REFERENCES directory_manifests(version_id)"
        ))
    conn.execute(text("DROP INDEX IF EXISTS uq_learning_job_active_section"))
    conn.execute(text("DROP INDEX IF EXISTS uq_learning_job_active_version_section"))
    conn.execute(text("DROP INDEX IF EXISTS uq_learning_job_active_legacy_section"))
    active = "status IN ('queued','planning','writing','reviewing','revising','needs_attention')"
    conn.execute(text(
        "CREATE UNIQUE INDEX uq_learning_job_active_version_section "
        "ON learning_generation_jobs (outline_version_id, section_id) "
        f"WHERE outline_version_id IS NOT NULL AND {active}"
    ))
    conn.execute(text(
        "CREATE UNIQUE INDEX uq_learning_job_active_legacy_section "
        "ON learning_generation_jobs (section_id) "
        f"WHERE outline_version_id IS NULL AND {active}"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_learning_generation_jobs_outline_version_id "
        "ON learning_generation_jobs (outline_version_id)"
    ))
    with Session(bind=conn) as db:
        for course in db.scalars(select(Course).order_by(Course.id)).all():
            service.ensure_legacy(db, course)
        _copy_tutor_history(db)
        db.flush()


def _verify_m1(conn) -> None:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    missing = sorted(set(M1_TABLES) - tables)
    if missing:
        raise RuntimeError(
            "M1 已登记但数据库结构不完整，缺少表：" + ", ".join(missing)
        )
    job_columns = {
        column["name"]
        for column in inspector.get_columns("learning_generation_jobs")
    }
    if "outline_version_id" not in job_columns:
        raise RuntimeError("M1 已登记但 learning_generation_jobs 缺少 outline_version_id。")
    indexes = {
        item["name"]
        for item in inspector.get_indexes("learning_generation_jobs")
    }
    required_indexes = {
        "uq_learning_job_active_version_section",
        "uq_learning_job_active_legacy_section",
        "ix_learning_generation_jobs_outline_version_id",
    }
    if missing_indexes := sorted(required_indexes - indexes):
        raise RuntimeError(
            "M1 已登记但数据库缺少索引：" + ", ".join(missing_indexes)
        )
    tutor_columns = {
        column["name"]
        for column in inspector.get_columns("version_tutor_sessions")
    }
    if "outline_version_id" not in tutor_columns:
        raise RuntimeError("M1 已登记但讲师会话表缺少 outline_version_id。")


def _assert_m2_quiescent(conn) -> None:
    """M2 之前不猜测正在运行的请求应该冻结哪个模型。"""
    tables = set(inspect(conn).get_table_names())
    if "learning_generation_jobs" in tables:
        placeholders = ", ".join(f"'{status}'" for status in ACTIVE_LEARNING_STATUSES)
        active_jobs = conn.execute(text(
            "SELECT count(*) FROM learning_generation_jobs "
            f"WHERE status IN ({placeholders})"
        )).scalar_one()
        if active_jobs:
            raise RuntimeError(
                "存在活动的内容生成任务，请等待完成或明确取消后再进行 M2 迁移。"
            )
    if "version_tutor_turns" in tables:
        active_turns = conn.execute(text(
            "SELECT count(*) FROM version_tutor_turns "
            "WHERE status IN ('queued', 'running')"
        )).scalar_one()
        if active_turns:
            raise RuntimeError(
                "存在未结束的讲师答疑，请等待完成或明确取消后再进行 M2 迁移。"
            )


def _legacy_capabilities() -> dict:
    """冻结旧连接的已知能力；不根据模型名称猜测图片或向量能力。"""
    return {
        capability: {
            "supported": capability in {
                "text_chat", "structured_output", "streaming"
            },
            "status": (
                "unverified"
                if capability in {"text_chat", "structured_output", "streaming"}
                else "unsupported"
            ),
            "checked_at": None,
            "error_code": None,
        }
        for capability in (
            "text_chat",
            "structured_output",
            "streaming",
            "vision",
            "embeddings",
        )
    }


def _add_nullable_json_column(conn, table_name: str, column_name: str) -> None:
    columns = {
        column["name"] for column in inspect(conn).get_columns(table_name)
    }
    if column_name not in columns:
        # 表名和列名来自上面的冻结常量，不接受任何用户输入。
        conn.execute(text(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} JSON NULL"
        ))


def _backfill_saved_provider_models(conn) -> None:
    """只读公开配置列，凭据引用和密钥不进入迁移读取结果。"""
    providers = Base.metadata.tables[LlmProvider.__tablename__]
    models = Base.metadata.tables[LLMModelConfig.__tablename__]
    bindings = Base.metadata.tables[LLMRoleBinding.__tablename__]
    provider_rows = conn.execute(
        select(
            providers.c.id,
            providers.c.model,
            providers.c.is_active,
        ).order_by(providers.c.id)
    ).mappings().all()
    active_provider_ids = [
        row["id"] for row in provider_rows if bool(row["is_active"])
    ]
    if len(active_provider_ids) > 1:
        raise RuntimeError("数据库中存在多个活动的旧模型连接，拒绝猜测默认路由。")

    model_ids: dict[int, int] = {}
    now = datetime.now(timezone.utc)
    for provider in provider_rows:
        model_id = conn.execute(
            select(models.c.id).where(
                models.c.provider_id == provider["id"],
                models.c.model == provider["model"],
            )
        ).scalar_one_or_none()
        if model_id is None:
            result = conn.execute(models.insert().values(
                provider_id=provider["id"],
                label=str(provider["model"])[:120],
                model=provider["model"],
                capabilities_json=_legacy_capabilities(),
                runtime_policy_json={},
                is_enabled=True,
                revision=1,
                created_at=now,
                updated_at=now,
            ))
            model_id = result.inserted_primary_key[0]
        model_ids[provider["id"]] = model_id

    if active_provider_ids:
        current = conn.execute(select(bindings.c.id).where(
            bindings.c.scope_key == "global",
            bindings.c.role_key == "default.chat",
        )).scalar_one_or_none()
        if current is None:
            conn.execute(bindings.insert().values(
                scope_type="global",
                scope_id=None,
                scope_key="global",
                role_key="default.chat",
                model_config_id=model_ids[active_provider_ids[0]],
                revision=1,
                created_at=now,
                updated_at=now,
            ))


def _apply_m2(conn) -> None:
    _assert_m2_quiescent(conn)
    missing_models = [name for name in M2_TABLES if name not in Base.metadata.tables]
    if missing_models:
        raise RuntimeError(f"M2 迁移模型登记不完整：{', '.join(missing_models)}")
    # 只显式创建本 revision 所属的两张表，不允许全量 create_all。
    for table_name in M2_TABLES:
        Base.metadata.tables[table_name].create(conn, checkfirst=True)
    for table_name in ROUTING_SNAPSHOT_TABLES:
        _add_nullable_json_column(conn, table_name, "routing_snapshot_json")
    _backfill_saved_provider_models(conn)


def _verify_m2(conn) -> None:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if missing := sorted(set(M2_TABLES) - tables):
        raise RuntimeError(
            "M2 已登记但数据库结构不完整，缺少表：" + ", ".join(missing)
        )

    required_columns = {
        "llm_model_configs": {
            "id", "provider_id", "label", "model", "capabilities_json",
            "runtime_policy_json", "is_enabled", "revision", "created_at",
            "updated_at",
        },
        "llm_role_bindings": {
            "id", "scope_type", "scope_id", "scope_key", "role_key",
            "model_config_id", "revision", "created_at", "updated_at",
        },
    }
    for table_name, expected in required_columns.items():
        actual = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if missing := sorted(expected - actual):
            raise RuntimeError(
                f"M2 已登记但 {table_name} 缺少列：" + ", ".join(missing)
            )

    required_uniques = {
        "llm_model_configs": "uq_llm_model_provider_name",
        "llm_role_bindings": "uq_llm_role_binding_scope_role",
    }
    for table_name, constraint_name in required_uniques.items():
        uniques = {
            item["name"] for item in inspector.get_unique_constraints(table_name)
        }
        if constraint_name not in uniques:
            raise RuntimeError(
                f"M2 已登记但 {table_name} 缺少唯一约束 {constraint_name}。"
            )

    required_indexes = {
        "llm_model_configs": {"ix_llm_model_configs_provider_id"},
        "llm_role_bindings": {
            "ix_llm_role_bindings_role_key",
            "ix_llm_role_bindings_model_config_id",
        },
    }
    for table_name, expected in required_indexes.items():
        indexes = {item["name"] for item in inspector.get_indexes(table_name)}
        if missing := sorted(expected - indexes):
            raise RuntimeError(
                f"M2 已登记但 {table_name} 缺少索引：" + ", ".join(missing)
            )

    for table_name in ROUTING_SNAPSHOT_TABLES:
        columns = {
            column["name"]: column
            for column in inspector.get_columns(table_name)
        }
        snapshot = columns.get("routing_snapshot_json")
        if snapshot is None:
            raise RuntimeError(
                f"M2 已登记但 {table_name} 缺少 routing_snapshot_json。"
            )
        if not snapshot.get("nullable", True):
            raise RuntimeError(
                f"M2 已登记但 {table_name}.routing_snapshot_json 不允许为空。"
            )


def _apply_m3(conn):
    for name in M3_TABLES:
        Base.metadata.tables[name].create(conn, checkfirst=True)

def _verify_m3(conn):
    inspector = inspect(conn)
    expected = {
        "material_batches": {"id", "name", "intro", "completeness", "revision", "status", "manifest_json", "context_json", "routing_snapshot_json", "error", "intake_id", "created_at"},
        "material_files": {"id", "batch_id", "request_id", "filename", "suffix", "sha256", "byte_size", "annotations_json", "included", "text_only_accepted", "revision", "created_at"},
        "material_processes": {"id", "file_id", "status", "report_json", "error_code", "created_at"},
        "material_analysis_steps": {"id", "batch_id", "input_hash", "status", "result_json"},
    }
    tables = set(inspector.get_table_names())
    for name, columns in expected.items():
        if name not in tables or columns - {c["name"] for c in inspector.get_columns(name)}:
            raise RuntimeError(f"M3 资料结构不完整：{name}")
    for table, unique in (("material_files", "uq_material_upload_request"),
                          ("material_analysis_steps", "uq_material_analysis_input")):
        if unique not in {c["name"] for c in inspector.get_unique_constraints(table)}:
            raise RuntimeError(f"M3 缺少唯一约束：{unique}")

def _apply_m4(conn):
    for name in ("extension_proposal", "extension_history"):
        _add_nullable_json_column(conn, "intake_sessions", name)
    conn.execute(text("UPDATE intake_sessions SET extension_history = '[]' WHERE extension_history IS NULL"))

def _verify_m4(conn):
    columns = {column["name"] for column in inspect(conn).get_columns("intake_sessions")}
    if not {"extension_proposal", "extension_history"} <= columns:
        raise RuntimeError("需求确认补问结构不完整。")

def _apply_m5(conn):
    PageRecognition.__table__.create(conn, checkfirst=True)


def _verify_m5(conn):
    inspector = inspect(conn)
    name = PageRecognition.__tablename__
    if name not in inspector.get_table_names() or set(PageRecognition.__table__.columns.keys()) - {c["name"] for c in inspector.get_columns(name)}:
        raise RuntimeError("单页识别任务表不完整。")
    required = {index.name for index in PageRecognition.__table__.indexes}
    if required - {index["name"] for index in inspector.get_indexes(name)}:
        raise RuntimeError("单页识别任务索引不完整。")


def _apply_m6(conn):
    PageAdoption.__table__.create(conn, checkfirst=True)


def _verify_m6(conn):
    inspector = inspect(conn)
    name = PageAdoption.__tablename__
    if name not in inspector.get_table_names() or set(PageAdoption.__table__.columns.keys()) - {c['name'] for c in inspector.get_columns(name)}:
        raise RuntimeError('视觉转录采用表不完整。')


def _apply_m7(conn):
    DraftMaterialBinding.__table__.create(conn, checkfirst=True)


def _verify_m7(conn):
    inspector = inspect(conn)
    name = DraftMaterialBinding.__tablename__
    if name not in inspector.get_table_names() or set(DraftMaterialBinding.__table__.columns.keys()) - {c['name'] for c in inspector.get_columns(name)}:
        raise RuntimeError('目录修订资料关联表不完整。')


MIGRATIONS = (
    Migration(M1_REVISION, _apply_m1, _verify_m1),
    Migration(M2_REVISION, _apply_m2, _verify_m2),
    Migration(M3_REVISION, _apply_m3, _verify_m3),
    Migration(M4_REVISION, _apply_m4, _verify_m4),
    Migration(M5_REVISION, _apply_m5, _verify_m5),
    Migration(M6_REVISION, _apply_m6, _verify_m6),
    Migration(M7_REVISION, _apply_m7, _verify_m7),
)


def migrate(engine) -> dict:
    """按编号顺序执行并验证；已经登记的 revision 绝不偷偷补建空表。"""
    applied: list[str] = []
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(2026090801)"))
        registry_metadata.create_all(conn)
        recorded = set(conn.execute(select(registry.c.revision)).scalars())
        known = [migration.revision for migration in MIGRATIONS]
        if unknown := sorted(recorded - set(known)):
            raise RuntimeError(
                "数据库包含当前代码不认识的迁移版本：" + ", ".join(unknown)
            )
        # 已应用记录只能是代码迁移列表的连续前缀，不能跳过中间版本。
        recorded_flags = [revision in recorded for revision in known]
        if True in recorded_flags and recorded_flags != sorted(
            recorded_flags, reverse=True
        ):
            raise RuntimeError("数据库迁移记录不连续，拒绝猜测或跳级修复。")
        for migration in MIGRATIONS:
            if migration.revision not in recorded:
                migration.apply(conn)
                migration.verify(conn)
                conn.execute(registry.insert().values(
                    revision=migration.revision,
                    applied_at=datetime.now(timezone.utc),
                ))
                applied.append(migration.revision)
            else:
                migration.verify(conn)
    return {
        "revision": MIGRATIONS[-1].revision,
        "applied": bool(applied),
        "applied_revisions": applied,
    }

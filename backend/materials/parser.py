"""Mac 本机解析适配器：无凭据、无网络、受限文件范围；不静默裸跑。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from backend.materials.schemas import ParseReport

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_RSS_KB = 1024 * 1024
FORMATS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}

ERROR_MESSAGES = {
    "source_not_found": "没有找到待解析的原文件。",
    "parser_not_installed": "独立解析环境未安装，请先按资料解析文档安装依赖。",
    "sandbox_unavailable": "当前系统未配置受限解析环境；不会把私人文件交给未隔离进程。",
    "parser_dependency_missing": "解析依赖缺失或版本不可用。",
    "unsupported_format": "当前支持 PDF、DOCX 和 PNG/JPEG；旧 DOC 需要先转换。",
    "legacy_doc_converter_required": "旧版 DOC 转换器尚未通过隔离验收，请先另存为 DOCX 或 PDF，原文件不会被修改。",
    "file_size_limit": "单个文件不能超过 25 MB，请拆分后重试。",
    "page_limit_exceeded": "当前单份 PDF 支持 1–150 页，请拆成数份后上传。",
    "encrypted_document": "请先在本机解除文档密码，再上传可读取副本。",
    "format_mismatch": "文件实际格式与扩展名不一致。",
    "unsafe_archive_entry": "Word 文件包含不安全路径或加密成员，已停止处理。",
    "archive_expansion_limit": "Word 解压大小或内部文件数超限，请拆分文档。",
    "duplicate_archive_entries": "Word 包含重复内部文件，无法确定应读取的内容。",
    "active_content_not_supported": "文档含宏或嵌入可执行对象；请导出不含活动内容的 PDF/DOCX。",
    "unsafe_xml": "文档 XML 含外部实体或文档类型声明，已拒绝解析。",
    "image_pixel_limit": "图片像素超过 2000 万，请缩小后重试。",
    "animated_image_not_supported": "请上传静态图片；不会仅处理动画第一帧后假装完整。",
    "document_too_complex": "文件内容复杂度超出本次处理预算，请拆分后重试。",
    "invalid_page_dimensions": "PDF 页尺寸异常。",
    "parser_timeout": "解析超时，原文件未被修改；可拆分文件后重试。",
    "parser_resource_limit": "解析达到内存、CPU 或产物大小预算，请拆分文件。",
    "invalid_parser_output": "解析产物校验失败，未发布任何片段。",
    "malformed_or_unreadable_document": "文件损坏、无法读取或包含暂不支持的结构。",
}


class MaterialParseError(Exception):
    def __init__(self, code: str):
        self.code = code if code in ERROR_MESSAGES else "malformed_or_unreadable_document"
        super().__init__(ERROR_MESSAGES[self.code])


def sandbox_profile(job_dir: Path, python: Path) -> str:
    # macOS 启动解释器需要读取根目录本身；literal 不放行其子目录。
    # 资料进程只能读取系统库、独立依赖、解析代码与本次作业目录。
    roots = ["/System", "/usr", "/bin", "/dev", "/Library/Fonts", sys.base_prefix,
             str(python.parent.parent.resolve()), str(ROOT / "materials_runtime"), str(job_dir.resolve())]
    reads = " ".join(f"(subpath {json.dumps(path, ensure_ascii=False)})" for path in roots)
    writable = json.dumps(str(job_dir.resolve()), ensure_ascii=False)
    return ("(version 1) (deny default) (allow sysctl-read) (allow mach-lookup) "
            f"(allow process-exec (subpath {json.dumps(sys.base_prefix)})) "
            f"(allow file-read* (literal \"/\") {reads}) (allow file-read-metadata) "
            "(allow signal (target self)) "
            f"(allow file-write* (subpath {writable}) (literal \"/dev/null\"))")


def _stop(process: subprocess.Popen):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def _run(command: list[str], work: Path, *, timeout_seconds: float) -> dict:
    # 不继承 .env、数据库地址、API key、PYTHONPATH 或用户 shell 配置。
    environment = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "TMPDIR": str(work)}
    log = work / "process-output.json"
    with log.open("wb") as stdout:
        process = subprocess.Popen(command, cwd=work, env=environment, stdout=stdout,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        start = time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic() - start > timeout_seconds:
                    raise MaterialParseError("parser_timeout")
                rss = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(process.pid)],
                                     capture_output=True, text=True, timeout=2).stdout.strip()
                if rss.isdigit() and int(rss) > MAX_RSS_KB:
                    raise MaterialParseError("parser_resource_limit")
                # 输出目录只有本次作业，限制的是全部产物，不仅某一页。
                size = sum(path.lstat().st_size for path in work.rglob("*") if not path.is_symlink() and path.is_file())
                if size > MAX_OUTPUT_BYTES:
                    raise MaterialParseError("parser_resource_limit")
                time.sleep(0.1)
            if process.returncode != 0:
                raise MaterialParseError("parser_resource_limit" if process.returncode < 0 else "malformed_or_unreadable_document")
        finally:
            if process.poll() is None:
                _stop(process)
    if log.stat().st_size > 1024:
        raise MaterialParseError("invalid_parser_output")
    try:
        result = json.loads(log.read_text())
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise ValueError()
        return result
    except (ValueError, OSError) as error:
        raise MaterialParseError("invalid_parser_output") from error


def validate_output(output: Path, expected_hash: str) -> ParseReport:
    """首次发布与崩溃恢复使用相同校验，缺页或越界产物均不发布。"""
    try:
        if output.is_symlink() or not output.is_dir():
            raise ValueError()
        paths = list(output.rglob("*"))
        if any(path.is_symlink() or not path.is_file() for path in paths):
            raise ValueError()
        if sum(path.stat().st_size for path in paths) > MAX_OUTPUT_BYTES:
            raise ValueError()
        report_file = output / "report.json"
        if report_file.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError()
        report = ParseReport.model_validate_json(report_file.read_bytes())
        allowed = {"report.json", *(artifact.path for artifact in report.artifacts)}
        if {p.name for p in paths} != allowed or report.source_sha256 != expected_hash:
            raise ValueError()
        return report
    except Exception as error:
        raise MaterialParseError("invalid_parser_output") from error


def parse_document(source: Path, destination: Path, *, timeout_seconds: float = 90) -> ParseReport:
    """生成新处理产物目录；不覆盖既有结果、不修改原文件、不负责批准纳入课程。"""
    source, destination = Path(source), Path(destination)
    if source.suffix.lower() not in FORMATS:
        raise MaterialParseError("unsupported_format")
    if not source.is_file():
        raise MaterialParseError("source_not_found")
    if source.stat().st_size > MAX_FILE_BYTES:
        raise MaterialParseError("file_size_limit")
    if destination.exists():
        raise FileExistsError("处理产物已经存在，请为新修订使用新目录。")
    python = ROOT / ".venv-materials/bin/python"
    if not python.is_file():
        raise MaterialParseError("parser_not_installed")
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise MaterialParseError("sandbox_unavailable")
    work_root = ROOT / ".material-work"
    work_root.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="parse-", dir=work_root) as temporary:
        work = Path(temporary).resolve()
        copied = work / ("input" + source.suffix.lower())
        shutil.copyfile(source, copied)
        if copied.stat().st_size > MAX_FILE_BYTES:
            raise MaterialParseError("file_size_limit")
        expected_hash = hashlib.sha256(copied.read_bytes()).hexdigest()
        output = work / "output"
        profile = sandbox_profile(work, python)
        command = ["/usr/bin/sandbox-exec", "-p", profile, str(python), "-I", "-B",
                   str(ROOT / "materials_runtime/entrypoint.py"), str(copied), str(output)]
        result = _run(command, work, timeout_seconds=timeout_seconds)
        if not result["ok"]:
            raise MaterialParseError(result.get("code", "invalid_parser_output"))
        report = validate_output(output, expected_hash)
        # 只有全量解析及引用检查成功后才交付产物；失败的临时目录自动清理。
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output, destination)
        return report

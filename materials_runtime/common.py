from __future__ import annotations

import hashlib
import json
from pathlib import Path

PARSER_VERSION = "local-structure-v1"
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_PAGES = 150
MAX_UNPACKED_BYTES = 80 * 1024 * 1024
MAX_ELEMENTS = 12000
MAX_TEXT_CHARS = 2_000_000
MAX_IMAGE_PIXELS = 20_000_000


class ParseFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Report:
    def __init__(self, source: Path, kind: str, output: Path):
        self.output = output
        self.characters = 0
        self.data = {
            "schema_version": 1, "parser_version": PARSER_VERSION,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "format": kind, "status": "ready", "page_count": None,
            "elements": [], "outline": [], "issues": [], "artifacts": [],
            "coverage": {"text": "not_started", "visual": "not_started"},
            "external_requests": 0,
        }

    def issue(self, code: str, locator: dict | None = None):
        self.data["issues"].append({"code": code, "locator": locator})
        self.data["status"] = "needs_review"

    def add(self, kind: str, text: str, locator: dict, **extra):
        self.characters += len(text)
        if len(self.data["elements"]) >= MAX_ELEMENTS or self.characters > MAX_TEXT_CHARS:
            raise ParseFailure("document_too_complex")
        element = {"id": f"e{len(self.data['elements']) + 1}", "kind": kind,
                   "text": text, "locator": locator, **extra}
        self.data["elements"].append(element)
        return element

    def artifact(self, relative_path: str, mime_type: str, locator: dict):
        self.data["artifacts"].append({"path": relative_path, "mime_type": mime_type, "locator": locator})

    def save(self):
        (self.output / "report.json").write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

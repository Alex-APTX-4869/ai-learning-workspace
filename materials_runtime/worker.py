"""参数由父进程构造；stdout 只发机器可读状态，绝不输出文档或异常正文。"""
import argparse
import json
from pathlib import Path
import resource
import warnings

from materials_runtime.common import MAX_FILE_BYTES, MAX_IMAGE_PIXELS, ParseFailure, Report


def parse(source: Path, output: Path):
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ParseFailure("file_size_limit")
    signature = source.read_bytes()[:8]
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        if not signature.startswith(b"%PDF-"):
            raise ParseFailure("format_mismatch")
        from materials_runtime.pdf import parse_pdf
        return parse_pdf(source, output)
    if suffix == ".docx":
        if not signature.startswith(b"PK"):
            raise ParseFailure("format_mismatch")
        from materials_runtime.word import parse_docx
        return parse_docx(source, output)
    if suffix == ".doc":
        if signature != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            raise ParseFailure("format_mismatch")
        # 旧 DOC 需要单独的转换隔离验证，不允许自动调用系统 Office 打开。
        raise ParseFailure("legacy_doc_converter_required")
    if suffix in {".png", ".jpg", ".jpeg"}:
        from PIL import Image, ImageOps
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source) as image:
            expected = "PNG" if suffix == ".png" else "JPEG"
            if image.format != expected:
                raise ParseFailure("format_mismatch")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ParseFailure("image_pixel_limit")
            if getattr(image, "n_frames", 1) != 1:
                raise ParseFailure("animated_image_not_supported")
            image.load()
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized.thumbnail((2000, 2000))
            normalized.save(output / "image.png")
        report = Report(source, "image", output)
        locator = {"type": "image", "image": 1}
        report.add("image", "", locator, preview="image.png")
        report.artifact("image.png", "image/png", locator)
        report.issue("image_description_pending", locator)
        report.data["coverage"] = {"text": "missing", "visual": "pending_review"}
        return report
    raise ParseFailure("unsupported_format")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    # CPU、单文件产物和描述符预算；墙钟时间与进程组由父进程控制。
    resource.setrlimit(resource.RLIMIT_CPU, (60, 65))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (96, 96))
    try:
        args.output.mkdir(exist_ok=True)
        report = parse(args.source, args.output)
        report.save()
        print(json.dumps({"ok": True}))
    except ParseFailure as error:
        print(json.dumps({"ok": False, "code": error.code}))
    except ImportError:
        print(json.dumps({"ok": False, "code": "parser_dependency_missing"}))
    except Exception:
        print(json.dumps({"ok": False, "code": "malformed_or_unreadable_document"}))


if __name__ == "__main__":
    main()

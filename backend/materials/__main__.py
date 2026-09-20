import argparse
import json
from pathlib import Path

from backend.materials.parser import MaterialParseError, parse_document


parser = argparse.ArgumentParser(description="本机受限资料解析验收，不调用模型、不纳入课程")
parser.add_argument("source", type=Path)
parser.add_argument("destination", type=Path, help="新的处理修订目录，必须尚不存在")
args = parser.parse_args()
try:
    report = parse_document(args.source, args.destination)
    print(json.dumps({"status": report.status, "format": report.format, "elements": len(report.elements),
                      "issues": sorted({item.code for item in report.issues}), "output": str(args.destination.resolve())}, ensure_ascii=False))
except MaterialParseError as error:
    print(json.dumps({"status": "failed", "code": error.code, "message": str(error)}, ensure_ascii=False))
    raise SystemExit(1)

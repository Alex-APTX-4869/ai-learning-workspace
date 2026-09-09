"""启动入口：python -m uvicorn backend.main:app --reload。"""
from pathlib import Path
import sys

# 兼容此前在 backend 文件夹运行 uvicorn main:app 的方式。
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import create_app

app = create_app()

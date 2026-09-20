import os
from pathlib import Path
from uuid import UUID

PROJECT = Path(__file__).resolve().parents[2]

def root() -> Path:
    location = Path(os.environ.get("MATERIAL_STORAGE_DIR", str(PROJECT / ".material-storage"))).resolve()
    location.mkdir(parents=True, exist_ok=True, mode=0o700)
    return location

def original(file) -> Path:
    return root() / str(UUID(file.id)) / ("original" + file.suffix)

def process_dir(file_id: str, process_id: str) -> Path:
    return root() / str(UUID(file_id)) / "processes" / str(UUID(process_id))

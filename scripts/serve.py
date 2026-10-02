"""Load .env without adding a runtime dependency; then run one Uvicorn worker."""

import os
import sys
from pathlib import Path

# Running a file makes scripts/ the import root. Resolve app/ from project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_env(path=Path(".env")):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    import uvicorn

    load_env()
    uvicorn.run(
        "app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")), workers=1
    )

"""Start a disposable real server, run TCP checks, and export its OpenAPI schema."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp:
        env = {
            **os.environ,
            "DATA_DIR": temp,
            "PORT": "8770",
            "PROVIDER": "demo",
            "API_KEYS": "dev-student-key",
        }
        with (root / "docs/evidence/runtime.log").open("w") as log:
            server = subprocess.Popen(
                [sys.executable, "scripts/serve.py"], cwd=root, env=env, stdout=log, stderr=log
            )
            base = "http://127.0.0.1:8770"
            try:
                for _ in range(100):
                    try:
                        if httpx.get(base + "/health", trust_env=False, timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        time.sleep(0.05)
                subprocess.run(
                    [sys.executable, "scripts/smoke_http.py"],
                    cwd=root,
                    env={**env, "BASE_URL": base},
                    check=True,
                )
                schema = httpx.get(base + "/openapi.json", trust_env=False).json()
                (root / "docs/openapi.json").write_text(
                    json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print("TCP smoke and OpenAPI export PASS")
            finally:
                server.terminate()
                server.wait(timeout=20)


if __name__ == "__main__":
    main()

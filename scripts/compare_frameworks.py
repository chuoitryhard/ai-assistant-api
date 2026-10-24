"""Independent learning experiment. Not part of the product runtime."""

import argparse
import asyncio
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx


def serve(kind, port):
    if kind == "fastapi":
        import uvicorn
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/wait")
        async def wait():
            await asyncio.sleep(0.08)
            return {"ok": True}

        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    else:
        from flask import Flask

        app = Flask(__name__)

        @app.get("/wait")
        def wait():
            time.sleep(0.08)
            return {"ok": True}

        # Flask development server with threads, not a production benchmark.
        app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


async def measure(base, concurrency, count=100):
    semaphore = asyncio.Semaphore(concurrency)
    samples = []
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        for _ in range(3):
            await client.get(base + "/wait")

        async def one():
            async with semaphore:
                start = time.perf_counter()
                response = await client.get(base + "/wait")
                response.raise_for_status()
                samples.append((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(count)))
        elapsed = time.perf_counter() - start
    ordered = sorted(samples)
    return {
        "concurrency": concurrency,
        "requests": count,
        "total_s": round(elapsed, 3),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[int(len(ordered) * 0.95) - 1], 3),
        "requests_per_s": round(count / elapsed, 2),
        "raw_latency_ms": samples,
    }


def main():
    rows = []
    for kind, port in [("fastapi", 8761), ("flask", 8762)]:
        with open(os.devnull, "w") as log:
            process = subprocess.Popen(
                [sys.executable, __file__, "--serve", kind, "--port", str(port)], stdout=log, stderr=log
            )
            try:
                base = f"http://127.0.0.1:{port}"
                for _ in range(100):
                    try:
                        if httpx.get(base + "/wait", timeout=1, trust_env=False).status_code == 200:
                            break
                    except httpx.HTTPError:
                        time.sleep(0.05)
                for concurrency in (1, 10, 30):
                    row = asyncio.run(measure(base, concurrency))
                    row["framework"] = kind
                    rows.append(row)
                    print({k: v for k, v in row.items() if k != "raw_latency_ms"}, flush=True)
            finally:
                process.terminate()
                process.wait(timeout=10)
    output = {
        "environment": {
            "python": platform.python_version(),
            "os": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "method": "Local HTTP, 80 ms simulated wait, 100 requests per case, no LLM. Flask threaded development server; Uvicorn one process.",
        "results": rows,
    }
    Path("docs/evidence/framework-comparison.json").write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", choices=["fastapi", "flask"])
    parser.add_argument("--port", type=int, default=8761)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve, args.port)
    else:
        main()

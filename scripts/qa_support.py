"""Isolated local server for browser review; never uses the user's live database."""
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_server(port=8766):
    application_root = Path(os.environ.get("QA_PROJECT_DIR", str(ROOT))).resolve()
    temp = ROOT / "tmp/qa"
    temp.mkdir(parents=True, exist_ok=True)
    output = ROOT / "output/verification"
    output.mkdir(parents=True, exist_ok=True)
    db = temp / f"review-{uuid4().hex}.db"
    opener = build_opener(ProxyHandler({}))
    url = f"http://127.0.0.1:{port}"
    with (output / "review-server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-X", "utf8", "run.py", "--port", str(port), "--db", str(db)],
                                   cwd=application_root, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            for _ in range(80):
                if process.poll() is not None: raise RuntimeError("Review server exited; check port availability")
                try:
                    with opener.open(url + "/api/health", timeout=.5) as response:
                        if response.status == 200: break
                except OSError: time.sleep(.1)
            else: raise TimeoutError("Review server startup timed out")
            yield url
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)

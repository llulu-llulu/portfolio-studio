"""Create a reviewable source package using an explicit file allowlist."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ["README.md", "PLAN.md", "DESIGN.md", "VERIFY.md", "DELIVERY.md", "REVIEW.md",
              "run.py", ".gitignore", ".gitattributes", "requirements.txt", "requirements.lock",
              "requirements-dev.txt", "requirements-qa.txt"]
FOLDERS = ["backend", "frontend", "tests", "scripts", "attachments", "output/playwright", "output/verification"]


def package():
    files = [ROOT / name for name in ROOT_FILES]
    for folder in FOLDERS:
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".db", ".zip"})
    files = sorted(set(files))
    for path in files:
        if not path.is_file(): raise FileNotFoundError(path)
    manifest = {"packaged_at": datetime.now(timezone.utc).isoformat(),
                "file_count": len(files),
                "sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    target = ROOT / "output/portfolio-submission.zip"
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in files: archive.write(path, "portfolio-studio/" + path.relative_to(ROOT).as_posix())
        archive.writestr("portfolio-studio/SUBMISSION.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert not any(any(bad in name for bad in [".venv/", "node_modules/", "__pycache__/", "data/plans.db"]) for name in archive.namelist())
    print(json.dumps({"archive":str(target),"files":len(files)+1,"bytes":target.stat().st_size,
                      "sha256":hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False,indent=2))


if __name__ == "__main__": package()

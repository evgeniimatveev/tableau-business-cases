# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Repo hygiene checks that need no raw data: manifest completeness, control keys, README links.

Run: uv run scripts/check_repo.py   (prints a markdown report, exit code 1 on any problem)
"""
import re
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")  # emoji in the report; Windows consoles default to cp1252
ROOT = Path(__file__).resolve().parent.parent
problems = []
passed = []

# 1. manifest: every raw file documents where it came from and under which license
manifest = yaml.safe_load((ROOT / "data" / "manifest.yaml").read_text(encoding="utf-8"))
required = ("file", "bytes", "sha256_16", "origin", "license", "license_status")
for entry in manifest["files"]:
    missing = [k for k in required if entry.get(k) in (None, "")]
    if missing:
        problems.append(f"manifest: `{entry.get('file')}` lacks {', '.join(missing)}")
    elif "TODO" in str(entry):
        problems.append(f"manifest: `{entry['file']}` still has a TODO")
passed.append(f"manifest lists {len(manifest['files'])} files with origin, license and checksum")

# 2. controls.yaml: every case has its expected values
controls = yaml.safe_load((ROOT / "controls.yaml").read_text(encoding="utf-8"))
for key in ("olympics", "olist_cohort", "lebron", "worldbank", "jordan"):
    if not controls.get(key):
        problems.append(f"controls.yaml: section `{key}` is missing or empty")
passed.append("controls.yaml has the 5 case sections")

# 3. every case folder has a README, and every local link/image in any README resolves
cases = sorted(p for p in (ROOT / "cases").iterdir() if p.is_dir())
for case in cases:
    if not (case / "README.md").exists():
        problems.append(f"cases/{case.name}: README.md is missing")
link = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
checked = 0
for md in [ROOT / "README.md", *(c / "README.md" for c in cases if (c / "README.md").exists())]:
    for target in link.findall(md.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        checked += 1
        if not (md.parent / target.split("#")[0]).exists():
            problems.append(f"{md.relative_to(ROOT).as_posix()}: broken link `{target}`")
passed.append(f"{checked} local links and images in READMEs resolve")

print("## Repo checks\n")
for p in passed:
    print(f"- ✅ {p}")
for p in problems:
    print(f"- ❌ {p}")
sys.exit(1 if problems else 0)

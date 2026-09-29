#!/usr/bin/env python3
"""Run the bash fences in README.md.

Every ```bash fence must sit inside a pair of markers:

    <!-- ci-commands: cpu -->
    ```bash
    ...
    ```
    <!-- /ci-commands -->

CI calls this with --section cpu or --section ros. A fence outside a marker
fails the check, so a command added to the README is either run here or rejected.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

OPEN = re.compile(r"^<!-- ci-commands:\s*([A-Za-z0-9_-]+)\s*-->\s*$")
CLOSE = re.compile(r"^<!-- /ci-commands -->\s*$")


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    buf: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if in_fence:
            if line.startswith("```"):
                sections.setdefault(current, []).append("\n".join(buf))
                buf = []
                in_fence = False
            else:
                buf.append(line)
            continue
        opened = OPEN.match(line)
        if opened:
            if current is not None:
                raise SystemExit(f"README.md:{lineno}: nested ci-commands marker")
            current = opened.group(1)
            sections.setdefault(current, [])
            continue
        if CLOSE.match(line):
            if current is None:
                raise SystemExit(f"README.md:{lineno}: closing marker without an open marker")
            current = None
            continue
        if line.startswith("```bash"):
            if current is None:
                raise SystemExit(
                    f"README.md:{lineno}: bash fence is outside a ci-commands marker"
                )
            in_fence = True
            continue
    if in_fence:
        raise SystemExit("README.md: unclosed bash fence")
    if current is not None:
        raise SystemExit("README.md: unclosed ci-commands marker")
    return sections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", required=True)
    parser.add_argument("--list", action="store_true", help="print commands and exit")
    args = parser.parse_args()

    sections = parse_sections(README.read_text())
    if args.section not in sections:
        known = ", ".join(sorted(sections)) or "(none)"
        raise SystemExit(f"no ci-commands section {args.section!r}; have {known}")
    blocks = sections[args.section]
    if not blocks:
        raise SystemExit(f"section {args.section!r} has no bash fences")
    script = "set -eo pipefail\n" + "\n".join(blocks) + "\n"
    if args.list:
        sys.stdout.write(script)
        return 0
    print(f"== README commands: {args.section} ==", flush=True)
    completed = subprocess.run(["bash", "-lc", script], cwd=ROOT)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

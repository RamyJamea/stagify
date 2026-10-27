"""Check documented Python, public-reference coverage, and included offline examples."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import stagify

ROOT = Path(__file__).resolve().parents[1]
GEMINI_EXAMPLES = {
    "examples/gemini.py",
    "examples/analysis_with_cleaner.py",
    "examples/long_tool_loop.py",
}
SNIPPET = re.compile(r'^\s*--8<-- "([^"]+)"\s*$', re.MULTILINE)
PYTHON_FENCE = re.compile(r"^```python[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def main() -> None:
    examples: set[str] = set()
    fences = 0
    for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        source = path.read_text(encoding="utf-8")
        for block in re.finditer(r"^```json[^\n]*\n(.*?)^```", source, re.MULTILINE | re.DOTALL):
            json.loads(block[1])
        for match in SNIPPET.finditer(source):
            relative = match[1]
            target = (ROOT / relative).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                raise RuntimeError(f"Invalid include in {path}: {relative}")
            if target.suffix == ".py":
                examples.add(relative)
        for block in PYTHON_FENCE.finditer(source):
            expanded = SNIPPET.sub(
                lambda match: (ROOT / match[1]).read_text(encoding="utf-8"), block[1]
            )
            ast.parse(
                expanded,
                filename=f"{path.relative_to(ROOT)}:{source[: block.start()].count(chr(10)) + 1}",
            )
            fences += 1

    references = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "docs/reference").glob("*.md")
    )
    documented = set(
        re.findall(r"^::: stagify\.([A-Za-z_][A-Za-z_0-9]*)\s*$", references, re.MULTILINE)
    )
    missing = set(stagify.__all__) - documented
    if missing:
        raise RuntimeError(f"Public API missing from reference: {sorted(missing)}")
    if not GEMINI_EXAMPLES <= examples:
        raise RuntimeError("Gemini simulation list must match documented includes")
    for relative in sorted(examples):
        command = [sys.executable]
        if relative in GEMINI_EXAMPLES:
            command.append(str(ROOT / "scripts/simulate_gemini.py"))
        command.append(str(ROOT / relative))
        subprocess.run(command, cwd=ROOT, check=True, timeout=60)
        print(f"Verified example: {relative}", flush=True)
    print(f"Parsed {fences} Python fences; documented {len(stagify.__all__)} public exports.")
    print("Gemini examples verified with simulated Interactions HTTP responses; no live calls.")


if __name__ == "__main__":
    main()

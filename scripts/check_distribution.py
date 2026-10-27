"""Verify built archives and import the wheel away from the project source tree."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath


def check(dist: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    expected = project["version"]
    wheels = list(dist.glob("*.whl"))
    sources = list(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise RuntimeError("Expected one wheel and one source archive in dist.")
    wheel = wheels[0].resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        required = {"stagify/__init__.py", "stagify/py.typed"}
        if not required <= names:
            raise RuntimeError(f"Missing package files: {sorted(required - names)}")
        metadata_root = f"stagify-{expected}.dist-info/"
        if any(
            not name.startswith(("stagify/", metadata_root)) for name in names
        ):
            raise RuntimeError("Wheel contains files outside the package/metadata.")
        if not any(name.endswith("/LICENSE") for name in names):
            raise RuntimeError("Wheel is missing its license.")

    with tarfile.open(sources[0], mode="r:gz") as archive:
        members = archive.getnames()
        prefixes = {PurePosixPath(name).parts[0] for name in members}
        if len(prefixes) != 1:
            raise RuntimeError("Source archive must have one root directory.")
        relative = {
            str(PurePosixPath(*PurePosixPath(name).parts[1:])) for name in members
        }
        required = {
            "pyproject.toml", "README.md", "LICENSE",
            "src/stagify/__init__.py", "src/stagify/py.typed",
        }
        if not required <= relative:
            raise RuntimeError(f"Source archive is missing {sorted(required - relative)}")

    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv must be available on PATH.")
    probe = (
        "import importlib.metadata as m; "
        "import importlib.resources as r; "
        "import stagify; "
        f"assert m.version('stagify') == {expected!r}; "
        "assert r.files('stagify').joinpath('py.typed').is_file(); "
        "assert m.metadata('stagify')['License-Expression'] == 'MIT'; "
        "print('Isolated wheel import OK:', m.version('stagify'))"
    )
    with tempfile.TemporaryDirectory(prefix="stagify-wheel-") as directory:
        subprocess.run(
            [
                uv, "run", "--isolated", "--no-project", "--no-config",
                "--python", sys.executable, "--with", str(wheel),
                "--", "python", "-I", "-c", probe,
            ],
            cwd=directory,
            check=True,
        )
    print("Wheel and source archive checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dist",
    )
    check(parser.parse_args().dist)

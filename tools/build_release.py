"""Build deterministic installable and distribution archives; no AP install needed."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Archipelago-Source" / "strikers"


def archive(destination, files):
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path, name in sorted(files, key=lambda item: item[1]):
            info = zipfile.ZipInfo(name, (2026, 10, 22, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            output.writestr(info, path.read_bytes())
    with zipfile.ZipFile(temporary) as check:
        if check.testzip() is not None:
            raise RuntimeError("Archive verification failed")
    temporary.replace(destination)


def files_under(directory):
    return [
        path
        for path in directory.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in (".pyc", ".pyo")
    ]


def main():
    version = json.loads((SOURCE / "archipelago.json").read_text(encoding="utf-8-sig"))[
        "world_version"
    ]
    package = ROOT / "Archipelago" / "strikers.apworld"
    package.parent.mkdir(exist_ok=True)
    archive(
        package,
        [(path, "strikers/" + path.relative_to(SOURCE).as_posix()) for path in files_under(SOURCE)],
    )
    manifest = ROOT / "release-manifest.json"
    component_names = (
        "Archipelago/strikers.apworld",
        "Riivolution/Riivolution/StrikersAP/main.dol",
        "Riivolution/Riivolution/riivolution/StrikersAP.xml",
    )
    manifest.write_text(
        json.dumps(
            {
                "version": version,
                "sha256": {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in component_names
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    files = [
        manifest,
        ROOT / "README.txt",
        ROOT / "DEVELOPING.md",
        ROOT / "Strikers.yaml",
        ROOT / "pyproject.toml",
        package,
    ]
    for directory in ("Archipelago-Source", "Riivolution", "tools", "tests", "examples"):
        files.extend(files_under(ROOT / directory))
    release = ROOT / f"Super-Mario-Strikers-Archipelago-Mod-{version}.zip"
    archive(release, [(path, path.relative_to(ROOT).as_posix()) for path in files])
    for path in (package, release):
        print(
            f"{path.name}: {path.stat().st_size} bytes; SHA256 {hashlib.sha256(path.read_bytes()).hexdigest()}"
        )


if __name__ == "__main__":
    main()

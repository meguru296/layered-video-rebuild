#!/usr/bin/env python3
"""Build and verify the skill-only release archive using an explicit allowlist."""
import argparse
import hashlib
from pathlib import Path
import re
import zipfile

SKILL_NAME = "layered-video-rebuild"
SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/analysis-and-motion.md",
    "references/art-and-compositing.md",
    "references/records-and-audits.md",
    "references/render-and-qa.md",
    "references/troubleshooting-and-handoff.md",
    "references/type-and-effects.md",
    "scripts/audit_project.py",
)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v1.0.0")
    parser.add_argument("--output", type=Path, default=root.parent / "release-assets")
    args = parser.parse_args()
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?", args.version):
        parser.error("Use a version such as v1.0.0.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"{SKILL_NAME}-{args.version}.zip"
    contents = {}
    for name in SKILL_FILES:
        source = root / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Expected regular skill file: {name}")
        contents[f"{SKILL_NAME}/{name}"] = source.read_bytes()

    # Fixed timestamps and permissions avoid leaking local filesystem metadata.
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(contents):
            raise ValueError("Release archive failed its entry or CRC checks.")
        for name, data in contents.items():
            if archive.read(name) != data:
                raise ValueError(f"Release archive content mismatch: {name}")
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(".zip.sha256")
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="ascii")
    print(f"Verified {len(contents)} skill files.")
    print(f"{digest}  {archive_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

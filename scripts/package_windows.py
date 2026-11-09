"""Assemble deterministic, architecture-specific Windows FFmpeg runtime archives."""

import argparse
import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path

from build_windows import REQUIRED_CONFIG, SPEC, sha256, verify_config

DLLS = set(SPEC["dlls"])
FILES = DLLS | {
    "FFmpeg-LICENSE.txt", "FFmpeg-CREDITS.txt", "config.h",
    "config_components.h", "manifest.json",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_pe(path, expected_machine):
    data = Path(path).read_bytes()
    require(len(data) >= 0x40 and data[:2] == b"MZ", f"Invalid PE DOS header: {path.name}")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    require(offset <= len(data) - 6 and data[offset:offset + 4] == b"PE\0\0",
            f"Invalid PE signature: {path.name}")
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    require(machine == expected_machine,
            f"Wrong PE machine for {path.name}: {machine:#06x} != {expected_machine:#06x}")


def archive_directory(directory, output):
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            info = zipfile.ZipInfo(path.name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 0
            info.external_attr = 0x20
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def assemble(staging, output):
    require({path.name for path in staging.iterdir()} == set(SPEC["architectures"]),
            "Staging must contain exactly the ARM64 and x64 builds")
    require(not output.exists() or not any(output.iterdir()),
            f"Package output must be new or empty; preserve existing files: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for architecture, target in SPEC["architectures"].items():
        directory = staging / architecture
        require({path.name for path in directory.iterdir()} == FILES,
                f"Unexpected or missing staged files for {architecture}")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        require(manifest["artifact"] == SPEC["artifact"] and manifest["version"] == SPEC["version"]
                and manifest["architecture"] == architecture
                and manifest["pe_machine"] == target["machine"]
                and manifest["source_sha256"] == SPEC["source_sha256"]
                and manifest["components"] == list(REQUIRED_CONFIG)
                and set(manifest["dlls"]) == DLLS,
                f"Build provenance mismatch: {architecture}")
        require(re.fullmatch(r"[0-9a-f]{40}", manifest["build_commit"]) is not None,
                "Release packages require a full CI build commit")
        verify_config((directory / "config.h").read_text(encoding="utf-8"),
                      (directory / "config_components.h").read_text(encoding="utf-8"))
        for name in DLLS:
            path = directory / name
            verify_pe(path, target["machine"])
            metadata = manifest["dlls"][name]
            require(metadata["sha256"] == sha256(path) and metadata["bytes"] == path.stat().st_size,
                    f"DLL provenance mismatch: {architecture}/{name}")
        output_file = output / f"{SPEC['artifact']}-{architecture}-{SPEC['version']}.zip"
        archive_directory(directory, output_file)
    return sorted(output.glob("*.zip"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    packages = assemble(args.staging, args.out)
    print(json.dumps({path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in packages}, sort_keys=True))


if __name__ == "__main__":
    main()

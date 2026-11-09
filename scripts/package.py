"""Strict, deterministic Prefab schema-2 AAR assembly (Python standard library)."""

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

from common import MODULES, ROOT, SPEC, REPOSITORY, aar_filename, require, sha256, verify_archive
from common import verify_config, write_json


def zip_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content)
    return output.getvalue()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def assemble(staging, commit):
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Expected full build commit SHA")
    require({p.name for p in staging.iterdir()} == set(SPEC["abis"]), "Incomplete or extra ABIs")
    manifest = {"spec": SPEC, "build_commit": commit, "build_repository": REPOSITORY, "abis": {}}
    files = {
        "AndroidManifest.xml": (
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
            'package="dev.redraincast.ffmpeg"><uses-sdk android:minSdkVersion="30"/>'
            "</manifest>\n"
        ).encode(),
        "prefab/prefab.json": json_bytes({
            "schema_version": 2, "name": SPEC["prefab_name"],
            "version": SPEC["prefab_version"], "dependencies": [],
        }),
        "META-INF/NOTICE": (ROOT / "NOTICE").read_bytes(),
    }
    for module in MODULES:
        files[f"prefab/modules/{module}/module.json"] = json_bytes({
            "export_libraries": [":avutil", "-lm"] if module == "swresample" else ["-lm"],
        })
    for abi, target in SPEC["abis"].items():
        stage = staging / abi
        metadata = json.loads((stage / "manifest.json").read_text())
        require(metadata["spec"] == SPEC, f"Package contract mismatch: {abi}")
        require(metadata["abi"] == abi and metadata["api"] == SPEC["api"]
                and metadata["ndk"] == SPEC["ndk"] and metadata["stl"] == "none"
                and metadata["static"] is True, f"ABI provenance mismatch: {abi}")
        require(metadata["elf_machine"] == target["machine"], "ELF provenance mismatch")
        actual = {p.relative_to(stage).as_posix(): sha256(p)
                  for p in stage.rglob("*") if p.is_file() and p.name != "manifest.json"}
        require(actual == metadata["files"], f"Staging integrity mismatch: {abi}")
        verify_config((stage / "config/config.h").read_text())
        require(metadata["smoke"]["whole_archive"] and metadata["smoke"]["no_undefined"]
                and metadata["smoke"]["load_alignments"]
                and all(a >= 16384 for a in metadata["smoke"]["load_alignments"]),
                f"Missing smoke validation: {abi}")
        manifest["abis"][abi] = metadata
        for module in MODULES:
            base = f"prefab/modules/{module}/libs/android.{abi}"
            library = stage / "lib" / f"lib{module}.a"
            require(verify_archive(library, target["machine"]) == metadata["object_counts"][module],
                    "Object count mismatch")
            files[f"{base}/lib{module}.a"] = library.read_bytes()
            files[f"{base}/abi.json"] = json_bytes({
                "abi": abi, "api": SPEC["api"], "ndk": 27, "stl": "none", "static": True,
            })
            headers = sorted((stage / "include" / f"lib{module}").glob("*.h"))
            require(headers, f"Missing installed headers: {abi}/{module}")
            if module == "avutil":
                require(any(p.name == "avconfig.h" for p in headers), "Missing avconfig.h")
            for path in headers:
                files[f"{base}/include/lib{module}/{path.name}"] = path.read_bytes()
        for path in sorted((stage / "config").iterdir()):
            files[f"META-INF/build/{abi}/{path.name}"] = path.read_bytes()
        for path in sorted((stage / "licenses").iterdir()):
            name = f"META-INF/licenses/{path.name}"
            require(name not in files or files[name] == path.read_bytes(), "License mismatch")
            files[name] = path.read_bytes()
    files["META-INF/provenance.json"] = json_bytes(manifest)
    return zip_bytes(files), manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    payload, manifest = assemble(args.staging, args.commit)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / aar_filename()).write_bytes(payload)
    write_json(args.out / "provenance.json", manifest)


if __name__ == "__main__":
    main()

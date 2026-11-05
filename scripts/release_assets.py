"""Create deterministic compliance archive and checksums after consumer validation."""

import argparse
import gzip
import io
import json
import tarfile
import zipfile
from pathlib import Path

from common import ROOT, SPEC, require, sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    dist = args.dist
    source = dist / f"ffmpeg-{SPEC['source_version']}.tar.xz"
    require(sha256(source) == SPEC["source_sha256"], "Release source checksum mismatch")
    results = json.loads((dist / "consumer-validation.json").read_text())
    require(set(results) == set(SPEC["abis"]), "Missing consumer validations")
    require(all(r["prefab_cmake_link"] == "passed" for r in results.values()),
            "Consumer validation failed")
    contents = {
        "NOTICE": (ROOT / "NOTICE").read_bytes(),
        "provenance.json": (dist / "provenance.json").read_bytes(),
        "consumer-validation.json": (dist / "consumer-validation.json").read_bytes(),
    }
    with zipfile.ZipFile(dist / f"{SPEC['tag']}.aar") as aar:
        for name in aar.namelist():
            if name.startswith(("META-INF/licenses/", "META-INF/build/")):
                contents[name] = aar.read(name)
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed,
                       mtime=SPEC["source_date_epoch"]) as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for name, data in sorted(contents.items()):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                entry.mode = 0o644
                entry.mtime = SPEC["source_date_epoch"]
                archive.addfile(entry, io.BytesIO(data))
    (dist / f"{SPEC['tag']}-compliance.tar.gz").write_bytes(compressed.getvalue())
    assets = sorted(p for p in dist.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (dist / "SHA256SUMS").write_text(
        "".join(f"{sha256(p)}  {p.name}\n" for p in assets), encoding="utf-8")


if __name__ == "__main__":
    main()

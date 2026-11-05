"""Build only the two public FFmpeg libraries on an isolated Linux runner."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from common import MODULES, ROOT, SPEC, require, sha256, verify_archive, verify_config
from common import verify_load_alignment, write_json

WORK = Path("/tmp/redrain-ffmpeg")


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    abi = sys.argv[1]
    target = SPEC["abis"][abi]
    ndk = WORK / "ndk"
    properties = (ndk / "source.properties").read_text()
    require(f"Pkg.Revision = {SPEC['ndk']}" in properties, "Wrong NDK revision")
    os.environ["SOURCE_DATE_EPOCH"] = str(SPEC["source_date_epoch"])
    tarball = WORK / f"ffmpeg-{SPEC['source_version']}.tar.xz"
    urllib.request.urlretrieve(SPEC["source_url"], tarball)
    require(sha256(tarball) == SPEC["source_sha256"], "FFmpeg source SHA256 mismatch")
    with tarfile.open(tarball) as archive:
        archive.extractall(WORK, filter="data")
    source = WORK / f"ffmpeg-{SPEC['source_version']}"
    build = WORK / "build"
    build.mkdir()
    tools = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    cc = tools / f"{target['triple']}{SPEC['api']}-clang"
    prefix = WORK / "install"
    flags = [
        *SPEC["configure_flags"], f"--arch={target['arch']}",
        f"--cc={cc}", f"--ar={tools / 'llvm-ar'}",
        f"--ranlib={tools / 'llvm-ranlib'}", f"--strip={tools / 'llvm-strip'}",
        f"--nm={tools / 'llvm-nm'}", f"--prefix={prefix}",
        f"--extra-cflags={SPEC['extra_cflags']}",
    ]
    run([source / "configure", *flags], cwd=build)
    config = (build / "config.h").read_text()
    verify_config(config)
    run(["make", f"-j{os.cpu_count() or 2}",
         "libavutil/libavutil.a", "libswresample/libswresample.a"], cwd=build)
    run(["make", "install-libavutil-headers", "install-libswresample-headers",
         "install-libavutil-static", "install-libswresample-static"], cwd=build)
    stage = WORK / "stage" / abi
    shutil.copytree(prefix, stage)
    object_counts = {}
    for module in MODULES:
        library = stage / "lib" / f"lib{module}.a"
        object_counts[module] = verify_archive(library, target["machine"])
        headers = run([tools / "llvm-readelf", "-h", library],
                      capture_output=True, text=True).stdout
        require(headers.count("Machine:") == object_counts[module], "ELF inspection incomplete")
    require((stage / "include/libavutil/avconfig.h").is_file(), "Missing generated avconfig.h")
    smoke = WORK / "test.so"
    run([cc, "-shared", "-fPIC", "-I", stage / "include", ROOT / "tests/smoke.c",
         "-Wl,--whole-archive", stage / "lib/libswresample.a", stage / "lib/libavutil.a",
         "-Wl,--no-whole-archive", "-lm", "-Wl,--no-undefined",
         "-Wl,-z,max-page-size=16384", "-Wl,-z,common-page-size=16384", "-o", smoke])
    segments = run([tools / "llvm-readelf", "-lW", smoke], capture_output=True, text=True).stdout
    alignments = verify_load_alignment(segments)
    dynamic = run([tools / "llvm-readelf", "-dW", smoke], capture_output=True, text=True).stdout
    require("libavutil.so" not in dynamic and "libswresample.so" not in dynamic,
            "Unexpected dynamic FFmpeg dependency")
    config_dir = stage / "config"
    config_dir.mkdir()
    for name in ("config.h", "config_components.h", "ffbuild/config.mak"):
        shutil.copyfile(build / name, config_dir / Path(name).name)
    licenses = stage / "licenses"
    licenses.mkdir()
    for path in sorted(source.glob("COPYING*")):
        shutil.copyfile(path, licenses / path.name)
    for name in ("LICENSE.md", "CREDITS"):
        shutil.copyfile(source / name, licenses / name)
    manifest = {
        "abi": abi, "api": SPEC["api"], "ndk": SPEC["ndk"], "stl": "none", "static": True,
        "spec": SPEC, "configure_arguments": flags, "elf_machine": target["machine"],
        "compiler": run([cc, "--version"], capture_output=True, text=True).stdout.splitlines()[0],
        "smoke": {"whole_archive": True, "no_undefined": True, "load_alignments": alignments},
        "object_counts": object_counts,
        "files": {p.relative_to(stage).as_posix(): sha256(p)
                  for p in sorted(stage.rglob("*")) if p.is_file()},
    }
    write_json(stage / "manifest.json", manifest)
    # Only this explicit staging directory is uploaded; never config.log or an environment dump.
    print(json.dumps({"abi": abi, "smoke": "passed", "object_counts": object_counts}))


if __name__ == "__main__":
    main()

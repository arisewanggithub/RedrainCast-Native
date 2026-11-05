"""Exercise the real Google Prefab CLI and NDK CMake consumer for every ABI."""

import argparse
import json
import subprocess
import zipfile
from pathlib import Path

from common import ROOT, SPEC, require, verify_load_alignment, write_json


def run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--aar", required=True, type=Path)
    parser.add_argument("--ndk", required=True, type=Path)
    parser.add_argument("--prefab-cli", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    args.work.mkdir(parents=True)
    with zipfile.ZipFile(args.aar) as archive:
        archive.extractall(args.work / "aar")
    results = {}
    for abi in SPEC["abis"]:
        generated = args.work / abi / "prefab"
        build = args.work / abi / "build"
        try:
            run(["java", "-jar", args.prefab_cli, "--build-system", "cmake",
                 "--platform", "android", "--abi", abi, "--os-version", str(SPEC["api"]),
                 "--ndk-version", "27", "--stl", "none", "--output", generated,
                 args.work / "aar/prefab"])
            run(["cmake", "-S", ROOT / "tests/consumer", "-B", build,
                 f"-DCMAKE_TOOLCHAIN_FILE={args.ndk}/build/cmake/android.toolchain.cmake",
                 f"-DANDROID_ABI={abi}", f"-DANDROID_PLATFORM=android-{SPEC['api']}",
                 "-DANDROID_STL=none", f"-DCMAKE_FIND_ROOT_PATH={generated}"])
            run(["cmake", "--build", build, "--parallel", "2"])
            tools = args.ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
            headers = run([tools / "llvm-readelf", "-lW", build / "libtest.so"]).stdout
            dynamic = run([tools / "llvm-readelf", "-dW", build / "libtest.so"]).stdout
            require("libavutil.so" not in dynamic and "libswresample.so" not in dynamic,
                    "Consumer unexpectedly links shared FFmpeg")
            results[abi] = {"prefab_cmake_link": "passed", "api": SPEC["api"],
                            "load_alignments": verify_load_alignment(headers)}
        except subprocess.CalledProcessError as error:
            # Only public compiler/tool output, never the environment or configure logs.
            print(error.stdout)
            print(error.stderr)
            raise
    write_json(args.report, results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

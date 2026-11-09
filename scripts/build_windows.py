"""Build a minimal FFmpeg Windows decoder runtime for RedrainCast."""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "windows.json").read_text(encoding="utf-8"))
REQUIRED_CONFIG = (
    "CONFIG_AVCODEC", "CONFIG_AVUTIL", "CONFIG_SWRESAMPLE",
    "CONFIG_H264_DECODER", "CONFIG_HEVC_DECODER", "CONFIG_AAC_DECODER",
    "CONFIG_OPUS_DECODER", "CONFIG_D3D11VA",
    "CONFIG_H264_D3D11VA_HWACCEL", "CONFIG_H264_D3D11VA2_HWACCEL",
    "CONFIG_HEVC_D3D11VA_HWACCEL", "CONFIG_HEVC_D3D11VA2_HWACCEL",
)
REQUIRED_LIBRARY_CONFIG = ("CONFIG_AVCODEC", "CONFIG_AVUTIL", "CONFIG_SWRESAMPLE", "CONFIG_D3D11VA")
REQUIRED_COMPONENT_CONFIG = tuple(name for name in REQUIRED_CONFIG if name not in REQUIRED_LIBRARY_CONFIG)
FORBIDDEN_CONFIG = (
    "CONFIG_GPL", "CONFIG_NONFREE", "CONFIG_VERSION3", "CONFIG_AVFORMAT",
    "CONFIG_AVDEVICE", "CONFIG_AVFILTER", "CONFIG_SWSCALE", "CONFIG_POSTPROC",
    "CONFIG_NETWORK", "CONFIG_FFMPEG", "CONFIG_FFPLAY", "CONFIG_FFPROBE",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(args, *, cwd, env):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def run_msys(args, *, cwd, env, capture_output=False, text=False):
    command = shlex.join(str(arg) for arg in args)
    return subprocess.run(["sh", "-c", command], cwd=cwd, env=env, check=True,
                          capture_output=capture_output, text=text)


def verify_config(config, components):
    for name in REQUIRED_LIBRARY_CONFIG:
        require(f"#define {name} 1" in config, f"Required FFmpeg component disabled: {name}")
    for name in FORBIDDEN_CONFIG:
        require(f"#define {name} 0" in config, f"Unexpected FFmpeg component enabled: {name}")
    enabled = set(re.findall(r"^#define (CONFIG_\w+_(?:DECODER|HWACCEL)) 1$", components, re.MULTILINE))
    expected = set(REQUIRED_COMPONENT_CONFIG)
    require(enabled == expected, f"Unexpected decoder/hardware components: {sorted(enabled)}")


def verify_dll_dependencies(output, filename):
    dependencies = re.findall(r"^\s*DLL Name:\s*(\S+)", output, re.MULTILINE | re.IGNORECASE)
    require(dependencies, f"No PE imports found for {filename}")
    allowed = {
        "avcodec-61.dll", "avutil-59.dll", "swresample-5.dll",
        "advapi32.dll", "bcrypt.dll", "cfgmgr32.dll", "combase.dll",
        "comctl32.dll", "crypt32.dll", "d3d11.dll", "dwmapi.dll",
        "dxgi.dll", "dxguid.dll", "gdi32.dll", "imm32.dll", "iphlpapi.dll",
        "kernel32.dll", "kernelbase.dll", "msvcrt.dll", "ntdll.dll",
        "ole32.dll", "oleaut32.dll", "rpcrt4.dll", "secur32.dll",
        "setupapi.dll", "shell32.dll", "shlwapi.dll", "user32.dll",
        "userenv.dll", "uuid.dll", "version.dll", "winhttp.dll",
        "winmm.dll", "wintrust.dll", "ws2_32.dll", "ucrtbase.dll",
    }
    unexpected = [name for name in dependencies
                  if name.lower() not in allowed
                  and not name.lower().startswith(("api-ms-win-", "ext-ms-win-"))]
    require(not unexpected, f"Unpackaged PE dependencies in {filename}: {unexpected}")


def build(architecture, work):
    target = SPEC["architectures"][architecture]
    require(os.environ.get("MSYSTEM") == target["msystem"],
            f"{architecture} build requires MSYS2 {target['msystem']}, got {os.environ.get('MSYSTEM')!r}")

    work = Path(work).resolve()
    require(not work.exists(), f"Build directory already exists; preserve it: {work}")
    work.mkdir(parents=True)
    source_archive = work / f"ffmpeg-{SPEC['source_version']}.tar.xz"
    urllib.request.urlretrieve(SPEC["source_url"], source_archive)
    require(sha256(source_archive) == SPEC["source_sha256"], "FFmpeg source SHA256 mismatch")
    with tarfile.open(source_archive) as archive:
        archive.extractall(work, filter="data")

    source = work / f"ffmpeg-{SPEC['source_version']}"
    build_dir = work / "build"
    prefix = work / "install"
    stage = work / "stage" / architecture
    build_dir.mkdir()
    tools = Path(target["prefix"]) / "bin"
    cc = tools / target["compiler"]
    flags = [
        *SPEC["configure_flags"], f"--arch={target['arch']}",
        f"--cc={cc}", f"--ar={tools / target['ar']}",
        f"--ranlib={tools / target['ranlib']}", f"--strip={tools / target['strip']}",
        f"--nm={tools / target['nm']}", f"--prefix={prefix}",
        f"--extra-cflags={SPEC['extra_cflags']}",
        f"--extra-ldflags={SPEC['extra_ldflags']}",
    ]
    env = {
        "PATH": os.pathsep.join((str(tools), "/usr/bin")),
        "HOME": str(work / "home"),
        "TMPDIR": str(work / "tmp"),
        "LC_ALL": "C",
        "SOURCE_DATE_EPOCH": str(SPEC["source_date_epoch"]),
        "MSYSTEM": target["msystem"],
        "MINGW_PREFIX": target["prefix"],
    }
    for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC"):
        if key in os.environ:
            env[key] = os.environ[key]
    Path(env["HOME"]).mkdir()
    Path(env["TMPDIR"]).mkdir()
    run(["sh", source / "configure", *flags], cwd=build_dir, env=env)
    config = (build_dir / "config.h").read_text(encoding="utf-8")
    components = (build_dir / "config_components.h").read_text(encoding="utf-8")
    verify_config(config, components)
    run(["make", f"-j{max(2, os.cpu_count() or 2)}"], cwd=build_dir, env=env)
    run(["make", "install"], cwd=build_dir, env=env)

    dll_dir = prefix / "bin"
    stage.mkdir(parents=True)
    for name in SPEC["dlls"]:
        dll = dll_dir / name
        require(dll.is_file() and dll.stat().st_size > 0, f"Missing generated runtime DLL: {name}")
        imports = run_msys([tools / target["objdump"], "-p", dll],
                           cwd=build_dir, env=env, capture_output=True, text=True).stdout
        verify_dll_dependencies(imports, name)
        shutil.copy2(dll, stage / name)
    shutil.copy2(source / "COPYING.LGPLv2.1", stage / "FFmpeg-LICENSE.txt")
    shutil.copy2(source / "CREDITS", stage / "FFmpeg-CREDITS.txt")
    shutil.copy2(build_dir / "config.h", stage / "config.h")
    shutil.copy2(build_dir / "config_components.h", stage / "config_components.h")

    smoke = work / "smoke.exe"
    run_msys([cc, f"-I{prefix / 'include'}", ROOT / "tests/smoke_windows.c",
              f"-L{prefix / 'lib'}", "-lavcodec", "-lswresample", "-lavutil",
              "-o", smoke], cwd=build_dir, env=env)
    smoke_env = dict(env)
    smoke_env["PATH"] = os.pathsep.join((str(dll_dir), smoke_env["PATH"]))
    run([smoke], cwd=build_dir, env=smoke_env)

    manifest = {
        "artifact": SPEC["artifact"],
        "version": SPEC["version"],
        "architecture": architecture,
        "pe_machine": target["machine"],
        "msystem": target["msystem"],
        "source_version": SPEC["source_version"],
        "source_sha256": SPEC["source_sha256"],
        "build_commit": os.environ.get("GITHUB_SHA", "local"),
        "compiler_version": run_msys([cc, "--version"], cwd=build_dir, env=env,
                                     capture_output=True, text=True).stdout.splitlines()[0],
        "configure_arguments": flags,
        "components": list(REQUIRED_CONFIG),
        "dlls": {
            name: {"sha256": sha256(stage / name), "bytes": (stage / name).stat().st_size}
            for name in SPEC["dlls"]
        },
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                         encoding="utf-8")
    print(json.dumps({"architecture": architecture, "dlls": manifest["dlls"]}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("architecture", choices=SPEC["architectures"])
    parser.add_argument("--work", type=Path, default=ROOT / "out/windows-build")
    args = parser.parse_args()
    build(args.architecture, args.work)


if __name__ == "__main__":
    main()

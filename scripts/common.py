"""Shared immutable package contract and binary validation."""

import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "package.json").read_text())
MODULES = ("avutil", "swresample")
REPOSITORY = "https://github.com/arisewanggithub/RedrainCast-Native"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_archive(path, machine):
    """Verify every ELF object, not just the first member of an ar archive."""
    data = Path(path).read_bytes()
    require(data.startswith(b"!<arch>\n"), f"Not a regular static archive: {path.name}")
    offset, count = 8, 0
    while offset < len(data):
        header = data[offset:offset + 60]
        require(len(header) == 60 and header[58:60] == b"`\n", "Invalid ar header")
        size = int(header[48:58].decode("ascii").strip())
        name = header[:16].decode("ascii").strip()
        body = data[offset + 60:offset + 60 + size]
        require(len(body) == size, "Truncated ar member")
        if name not in ("/", "//", "/SYM64/"):
            require(body.startswith(b"\x7fELF") and len(body) >= 20, "Non-ELF archive object")
            require(body[5] == 1, "Expected little-endian ELF")
            require(struct.unpack_from("<H", body, 16)[0] == 1, "Expected relocatable ELF")
            require(struct.unpack_from("<H", body, 18)[0] == machine, "Wrong ELF machine")
            count += 1
        offset += 60 + size + size % 2
    require(offset == len(data) and count > 0, "Empty or malformed static archive")
    return count


def verify_load_alignment(output):
    loads = [line.split() for line in output.splitlines() if line.strip().startswith("LOAD ")]
    require(loads, "No ELF LOAD segments found")
    alignments = [int(fields[-1], 16) for fields in loads]
    require(all(value >= 16384 for value in alignments), "ELF LOAD alignment is below 16 KiB")
    return alignments


def verify_config(text):
    expected = {
        "CONFIG_GPL": 0, "CONFIG_NONFREE": 0, "CONFIG_VERSION3": 0,
        "CONFIG_AVCODEC": 0, "CONFIG_AVFORMAT": 0, "CONFIG_AVDEVICE": 0,
        "CONFIG_AVFILTER": 0, "CONFIG_SWSCALE": 0, "CONFIG_POSTPROC": 0,
        "CONFIG_NETWORK": 0, "CONFIG_SHARED": 0, "CONFIG_STATIC": 1,
        "CONFIG_AVUTIL": 1, "CONFIG_SWRESAMPLE": 1,
        "CONFIG_FFMPEG": 0, "CONFIG_FFPLAY": 0, "CONFIG_FFPROBE": 0,
    }
    for key, value in expected.items():
        require(re.search(rf"^#define {key} {value}$", text, re.MULTILINE),
                f"Unexpected configuration: {key}")
    require('#define FFMPEG_LICENSE "LGPL version 2.1 or later"' in text,
            "Unexpected FFmpeg license")
    # --disable-asm clears architecture implementations, not compiler capability probes.
    architectures = re.findall(r"^#define (ARCH_\w+) (\d+)$", text, re.MULTILINE)
    require(architectures, "Missing architecture configuration")
    for key, value in architectures:
        require(value == "0", f"Assembly architecture enabled: {key}")
    require(not re.search(r"^#define HAVE_X86ASM 1$", text, re.MULTILINE),
            "Standalone x86 assembly enabled")

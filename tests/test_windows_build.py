import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_windows
import package_windows


def config_text():
    values = {
        "CONFIG_AVCODEC": 1,
        "CONFIG_AVUTIL": 1,
        "CONFIG_SWRESAMPLE": 1,
        "CONFIG_D3D11VA": 1,
        "CONFIG_GPL": 0,
        "CONFIG_NONFREE": 0,
        "CONFIG_VERSION3": 0,
        "CONFIG_AVFORMAT": 0,
        "CONFIG_AVDEVICE": 0,
        "CONFIG_AVFILTER": 0,
        "CONFIG_SWSCALE": 0,
        "CONFIG_POSTPROC": 0,
        "CONFIG_NETWORK": 0,
        "CONFIG_FFMPEG": 0,
        "CONFIG_FFPLAY": 0,
        "CONFIG_FFPROBE": 0,
    }
    return "".join(f"#define {name} {value}\n" for name, value in values.items())


def components_text(names):
    return "".join(f"#define {name} 1\n" for name in names)


class WindowsBuildTests(unittest.TestCase):
    def test_contract_limits_ffmpeg_to_application_codecs_and_hwaccels(self):
        flags = build_windows.SPEC["configure_flags"]
        self.assertEqual(build_windows.SPEC["artifact"], "redraincast-ffmpeg-windows-decoders")
        self.assertEqual(build_windows.SPEC["tag"],
                         "redraincast-ffmpeg-7.1.3-r2")
        self.assertIn("--disable-everything", flags)
        self.assertIn("--enable-decoder=h264", flags)
        self.assertIn("--enable-decoder=hevc", flags)
        self.assertIn("--enable-decoder=aac", flags)
        self.assertIn("--enable-decoder=opus", flags)
        self.assertIn("--enable-d3d11va", flags)
        self.assertIn("--disable-avformat", flags)
        self.assertIn("--disable-avfilter", flags)
        self.assertIn("--disable-gpl", flags)
        self.assertIn("--disable-nonfree", flags)
        self.assertIn("--disable-version3", flags)
        self.assertEqual(set(build_windows.SPEC["dlls"]),
                         {"avcodec-61.dll", "avutil-59.dll", "swresample-5.dll"})
        for architecture, target in build_windows.SPEC["architectures"].items():
            self.assertEqual(target["machine"], 0xAA64 if architecture == "arm64" else 0x8664)

    def test_config_accepts_only_required_decoder_and_hwaccel_components(self):
        expected = sorted(name for name in build_windows.REQUIRED_CONFIG
                          if name.endswith(("_DECODER", "_HWACCEL")))
        build_windows.verify_config(config_text(), components_text(expected))
        with self.assertRaisesRegex(ValueError, "Unexpected decoder/hardware"):
            build_windows.verify_config(config_text(),
                                         components_text(expected + ["CONFIG_VP9_DECODER"]))

    def test_only_system_and_bundled_ffmpeg_dll_imports_are_accepted(self):
        output = "DLL Name: avutil-59.dll\n DLL Name: KERNEL32.dll\n DLL Name: api-ms-win-core-synch-l1-2-0.dll"
        build_windows.verify_dll_dependencies(output, "avcodec-61.dll")
        with self.assertRaisesRegex(ValueError, "Unpackaged PE dependencies"):
            build_windows.verify_dll_dependencies(
                output + "\n DLL Name: libwinpthread-1.dll", "avcodec-61.dll")

    def test_pe_architecture_is_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "probe.dll"
            image = bytearray(0x80)
            image[:2] = b"MZ"
            image[0x3C:0x40] = (0x40).to_bytes(4, "little")
            image[0x40:0x44] = b"PE\0\0"
            image[0x44:0x46] = (0xAA64).to_bytes(2, "little")
            path.write_bytes(image)
            package_windows.verify_pe(path, 0xAA64)
            with self.assertRaisesRegex(ValueError, "Wrong PE machine"):
                package_windows.verify_pe(path, 0x8664)

    def test_architecture_archives_are_complete_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            for architecture, target in build_windows.SPEC["architectures"].items():
                directory = stage / architecture
                directory.mkdir(parents=True)
                dll_hashes = {}
                for name in build_windows.SPEC["dlls"]:
                    image = bytearray(0x80)
                    image[:2] = b"MZ"
                    image[0x3C:0x40] = (0x40).to_bytes(4, "little")
                    image[0x40:0x44] = b"PE\0\0"
                    image[0x44:0x46] = target["machine"].to_bytes(2, "little")
                    (directory / name).write_bytes(image)
                    dll_hashes[name] = {
                        "sha256": hashlib.sha256(image).hexdigest(),
                        "bytes": len(image),
                    }
                for name, contents in {
                    "FFmpeg-LICENSE.txt": "LGPL",
                    "FFmpeg-CREDITS.txt": "credits",
                    "config.h": config_text(),
                    "config_components.h": components_text([
                        name for name in build_windows.REQUIRED_CONFIG
                        if name.endswith(("_DECODER", "_HWACCEL"))
                    ]),
                }.items():
                    (directory / name).write_text(contents, encoding="utf-8")
                manifest = {
                    "artifact": build_windows.SPEC["artifact"],
                    "version": build_windows.SPEC["version"],
                    "architecture": architecture,
                    "pe_machine": target["machine"],
                    "source_sha256": build_windows.SPEC["source_sha256"],
                    "build_commit": "a" * 40,
                    "components": list(build_windows.REQUIRED_CONFIG),
                    "dlls": dll_hashes,
                }
                (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            first = package_windows.assemble(stage, root / "first")
            second = package_windows.assemble(stage, root / "second")
            self.assertEqual([path.read_bytes() for path in first],
                             [path.read_bytes() for path in second])
            with zipfile.ZipFile(first[0]) as archive:
                self.assertEqual(set(archive.namelist()), package_windows.FILES)


if __name__ == "__main__":
    unittest.main()

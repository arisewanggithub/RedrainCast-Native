import importlib.util
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import MODULES, SPEC, aar_filename, sha256, verify_archive, verify_config, verify_load_alignment
from common import write_json

loader = importlib.util.spec_from_file_location("packager", Path(__file__).resolve().parents[1]
                                              / "scripts/package.py")
packager = importlib.util.module_from_spec(loader)
loader.loader.exec_module(packager)


def archive_bytes(machine):
    body = bytearray(64)
    body[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<HH", body, 16, 1, machine)
    header = f"{'test.o/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(body):<10}`\n".encode()
    return b"!<arch>\n" + header + body


def config_text():
    disabled = ("GPL", "NONFREE", "VERSION3", "AVCODEC", "AVFORMAT", "AVDEVICE",
                "AVFILTER", "SWSCALE", "POSTPROC", "NETWORK", "SHARED",
                "FFMPEG", "FFPLAY", "FFPROBE")
    return ("".join(f"#define CONFIG_{key} 0\n" for key in disabled)
            + "".join(f"#define CONFIG_{key} 1\n" for key in ("STATIC", "AVUTIL", "SWRESAMPLE"))
            + '#define FFMPEG_LICENSE "LGPL version 2.1 or later"\n'
            + "#define ARCH_AARCH64 0\n#define ARCH_ARM 0\n#define ARCH_X86 0\n"
            + "#define HAVE_INLINE_ASM 1\n#define HAVE_X86ASM 0\n")


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stage = Path(self.temp.name)
        for abi, target in SPEC["abis"].items():
            root = self.stage / abi
            for directory in ("lib", "include/libavutil", "include/libswresample", "config", "licenses"):
                (root / directory).mkdir(parents=True, exist_ok=True)
            for module in MODULES:
                (root / "lib" / f"lib{module}.a").write_bytes(archive_bytes(target["machine"]))
                (root / f"include/lib{module}/{module}.h").write_text("/* fixture */\n")
            (root / "include/libavutil/avconfig.h").write_text("#define AV_HAVE_BIGENDIAN 0\n")
            (root / "config/config.h").write_text(config_text())
            (root / "licenses/COPYING.LGPLv2.1").write_text("license fixture\n")
            self.metadata = {
                "spec": SPEC, "abi": abi, "api": 30, "ndk": SPEC["ndk"],
                "stl": "none", "static": True, "elf_machine": target["machine"],
                "object_counts": {module: 1 for module in MODULES},
                "smoke": {"whole_archive": True, "no_undefined": True, "load_alignments": [16384]},
                "files": {p.relative_to(root).as_posix(): sha256(p)
                          for p in root.rglob("*") if p.is_file()},
            }
            write_json(root / "manifest.json", self.metadata)

    def assemble(self):
        return packager.assemble(self.stage, "a" * 40)[0]

    def test_aar_asset_name_is_independent_of_release_tag(self):
        self.assertEqual(aar_filename(), f"{SPEC['artifact']}-{SPEC['version']}.aar")
        self.assertEqual(aar_filename(), "ffmpeg-pcm-android-7.1.3-r2.aar")

    def test_deterministic_schema_and_contents(self):
        first = self.assemble()
        self.assertEqual(first, self.assemble())
        aar = self.stage / "test.aar"
        aar.write_bytes(first)
        with zipfile.ZipFile(aar) as archive:
            prefab = json.loads(archive.read("prefab/prefab.json"))
            self.assertEqual(prefab, {"schema_version": 2, "name": "redrain_ffmpeg",
                                     "version": "7.1.3.2", "dependencies": []})
            for abi in SPEC["abis"]:
                for module in MODULES:
                    base = f"prefab/modules/{module}/libs/android.{abi}"
                    metadata = json.loads(archive.read(f"{base}/abi.json"))
                    self.assertEqual(metadata, {"abi": abi, "api": 30, "ndk": 27,
                                                "stl": "none", "static": True})
                    self.assertIn(f"{base}/lib{module}.a", archive.namelist())
                self.assertIn(f"prefab/modules/avutil/libs/android.{abi}/include/libavutil/avconfig.h",
                              archive.namelist())
            swr = json.loads(archive.read("prefab/modules/swresample/module.json"))
            self.assertEqual(swr["export_libraries"], [":avutil", "-lm"])
            self.assertFalse(any(n.endswith((".so", ".dex", ".class", ".jar"))
                                 for n in archive.namelist()))

    def test_missing_abi_rejected(self):
        (self.stage / "x86_64").rename(self.stage / "wrong")
        with self.assertRaisesRegex(ValueError, "ABIs"):
            self.assemble()

    def test_tampering_rejected(self):
        (self.stage / "x86_64/lib/libavutil.a").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.assemble()

    def test_wrong_version_rejected(self):
        path = self.stage / "x86_64/manifest.json"
        value = json.loads(path.read_text())
        value["spec"]["ndk"] = "28"
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, "contract"):
            self.assemble()

    def test_wrong_elf_rejected(self):
        path = self.stage / "wrong.a"
        path.write_bytes(archive_bytes(40))
        with self.assertRaisesRegex(ValueError, "machine"):
            verify_archive(path, 183)

    def test_all_archive_members_verified(self):
        path = self.stage / "mixed.a"
        path.write_bytes(archive_bytes(183) + archive_bytes(40)[8:])
        with self.assertRaisesRegex(ValueError, "machine"):
            verify_archive(path, 183)

    def test_bad_alignment_rejected(self):
        self.assertEqual(verify_load_alignment(" LOAD 0x0 0x0 0x0 0x1 0x1 R E 0x4000"), [16384])
        for output in ("", " LOAD 0x0 0x0 0x0 0x1 0x1 R E 0x1000"):
            with self.assertRaises(ValueError):
                verify_load_alignment(output)

    def test_license_and_configuration_rejected(self):
        verify_config(config_text())
        for key in ("CONFIG_GPL", "CONFIG_NONFREE", "CONFIG_VERSION3", "CONFIG_AVCODEC"):
            with self.assertRaises(ValueError):
                verify_config(config_text().replace(f"{key} 0", f"{key} 1"))
        for key in ("ARCH_AARCH64", "ARCH_ARM", "ARCH_X86", "HAVE_X86ASM"):
            with self.assertRaises(ValueError):
                verify_config(config_text().replace(f"{key} 0", f"{key} 1"))

    def test_manifest_has_no_mutable_build_run_identity(self):
        _, manifest = packager.assemble(self.stage, "b" * 40)
        self.assertEqual(manifest["build_commit"], "b" * 40)
        self.assertNotIn("run_id", manifest)


if __name__ == "__main__":
    unittest.main()

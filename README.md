# RedrainCast native dependencies

Public build materials for **FFmpeg 7.1.3**. The Android package builds
unmodified upstream PCM utilities; the separate Windows runtime builds a
minimal decoder feature set from the same upstream source. The Android AAR
contains no application code, JNI implementation, Java, Kotlin, codec, network
support, DEX, or runtime fallback. Its small C smoke test is only a build-time
linker probe and is not shipped in the AAR.

## Immutable package contract

New Native releases use platform- and payload-specific tags:
`redraincast-ffmpeg-<platform>-<payload>-<version>`. Existing published release
tags are immutable and remain valid; the Android package's current `r1` release
therefore retains its original `ffmpeg-pcm-android-7.1.3-r1` tag and artifact
name.

| Property | Value |
|---|---|
| Current Android release tag (legacy immutable name) | `ffmpeg-pcm-android-7.1.3-r1` |
| Asset / Gradle version | `ffmpeg-pcm-android-7.1.3-r1.aar` / `7.1.3-r1` |
| Prefab package / schema | `redrain_ffmpeg` / `2` |
| Prefab numeric version | `7.1.3.1` (schema requires a CMake-compatible numeric version) |
| Targets | `redrain_ffmpeg::swresample`, `redrain_ffmpeg::avutil` |
| ABIs | `arm64-v8a`, `armeabi-v7a`, `x86_64` |
| Minimum Android API / NDK | `30` / `27.2.12479018` (Prefab major `27`) |
| Linkage / STL | static PIC / none |
| FFmpeg source SHA256 | `f0bf043299db9e3caacb435a712fc541fbb07df613c4b893e8b77e67baf3adbe` |

Credential-free download:

https://github.com/arisewanggithub/RedrainCast-Native/releases/download/ffmpeg-pcm-android-7.1.3-r1/ffmpeg-pcm-android-7.1.3-r1.aar

Download `SHA256SUMS` from the same release and verify the AAR before accepting
an update. Releases are protected by GitHub release immutability. The workflow
refuses an existing release or tag; it never replaces published assets.

## Android consumer

In `settings.gradle.kts`, within `dependencyResolutionManagement.repositories`:

```kotlin
ivy {
    name = "redrainNativeReleases"
    url = uri("https://github.com/arisewanggithub/RedrainCast-Native/releases/download")
    patternLayout {
        artifact("ffmpeg-pcm-android-[revision]/[artifact]-[revision].[ext]")
    }
    metadataSources { artifact() }
    content { includeModule("dev.redraincast.native", "ffmpeg-pcm-android") }
}
```

In the consuming Android module:

```kotlin
android {
    ndkVersion = "27.2.12479018"
    defaultConfig {
        minSdk = 30
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64") }
    }
    buildFeatures { prefab = true }
}
dependencies {
    implementation("dev.redraincast.native:ffmpeg-pcm-android:7.1.3-r1@aar")
}
```

The application retains its **own** small JNI wrapper:

```cmake
find_package(redrain_ffmpeg CONFIG REQUIRED)
target_link_libraries(your_jni_target PRIVATE
    redrain_ffmpeg::swresample redrain_ffmpeg::avutil)
target_link_options(your_jni_target PRIVATE
    -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384)
```

`swresample` exports the Prefab intra-package dependency `:avutil` and `-lm`.
`avutil` also exports `-lm`. Public include paths are platform-specific so each
ABI gets its own generated `libavutil/avconfig.h`. Do not manually add FFmpeg
header or archive paths. These static archives do not themselves have LOAD
segments; the consuming shared object must set its own 16 KiB alignment.

## Build, validate, release

Only the manually dispatched [Android release workflow](.github/workflows/release.yml)
builds the AAR libraries. Three separate Ubuntu 24.04 runners build the ABI matrix.
The [package contract](package.json) pins source, SHA, NDK, API and all feature
flags. Only `libavutil.a`, `libswresample.a` and their installed public headers
are staged. Assembly is deliberately disabled for parity with the tested
source-build configuration. The assembly check verifies disabled architecture
implementations; FFmpeg's `HAVE_INLINE_ASM` compiler capability probe can remain
true under the specified `--disable-asm` flag. No extra configuration flags
are added to change that capability probe. No local or application repository
build is needed.

1. Run `python3 -m unittest discover -s tests -v`, `bash -n scripts/build.sh`
   and `shellcheck scripts/build.sh` for changes.
2. Push reviewed build materials to this public repository.
3. Ensure repository **immutable releases** are enabled. An administrator can
   verify with `gh api repos/arisewanggithub/RedrainCast-Native/immutable-releases`.
   This settings endpoint requires administration access, unavailable to the
   built-in Actions token; no administrator credential is stored in the pipeline.
   The workflow separately asserts the published release's `immutable` field.
4. Run `gh workflow run release.yml --repo arisewanggithub/RedrainCast-Native`.
5. Inspect all matrix and packaging jobs. The workflow checks every archive
   object's ELF machine, disabled licensing/features, installed headers, and
   whole-archive shared-object linkage without undefined symbols.
6. Packaging is deterministic (sorted ZIP entries, fixed times/permissions,
   stored data); a second assembly is byte-compared. Google's checksum-pinned
   Prefab 2.1.0 CLI parses schema 2 and generates CMake integrations. Actual
   NDK links using the documented target names run for every ABI and verify
   16 KiB LOAD segment alignment before publication.
7. Only then does a narrowly permissioned job draft a release with all assets,
   publish it, and verify GitHub reports it immutable.

The build helper runs configure/make under a minimal environment with only an
explicit public tool path, fixed temporary workspace, HOME, locale, source
epoch and the Windows process variables needed by compiler subprocesses.
It never uploads configure logs, environment dumps, SDK credentials, or
checkout authentication. Artifacts use explicit staging allowlists. Generated
`config.h`, `config_components.h` and `config.mak` contain only these sanitized
build settings. Paths in those settings refer to the documented fixed
`/tmp/redrain-ffmpeg` runner workspace, never a developer machine.

Every Android AAR release contains:

* The deterministic AAR (six static libraries, ABI-specific public headers,
  Prefab metadata, upstream license/author notices and configuration/provenance).
* Original checksum-pinned `ffmpeg-7.1.3.tar.xz`: full corresponding source.
* `*-build-materials.tar.gz`: this exact repository revision, including workflow,
  build/packaging scripts, tests and instructions.
* `*-compliance.tar.gz`: upstream licenses/CREDITS, configurations, provenance,
  notices and consumer validation results.
* `provenance.json`, `consumer-validation.json`, `SHA256SUMS`.

To rebuild, extract the build materials on a **fresh** Ubuntu 24.04 runner with
Python 3.12+, bash, GNU make, host C compiler, and Android SDK command-line
tools. Install with
`"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" "ndk;27.2.12479018"` and invoke
`bash scripts/build.sh ABI "$ANDROID_HOME/ndk/27.2.12479018"` separately for
each ABI on separate runners. Follow the workflow for merging, CLI validation
and compliance assets. FFmpeg source is downloaded/verified afresh. Generated
config files are supplied for inspection and relinking; regenerate them using
the helper rather than moving a configured build tree between machines.

Changing the NDK, API, source, flags, packaging, or static dependency contract
requires a **new package revision and tag** (for example `7.1.3-r2`, numeric
Prefab version `7.1.3.2`). Use a tag such as
`redraincast-ffmpeg-android-pcm-7.1.3-r2` for a new Android package revision;
keep the `ffmpeg-pcm-android` artifact coordinate and asset filename expected
by Gradle. The Android consumer supports both the original release path and
the new platform-specific release path. Update the contract and every
version-pinned workflow and consumer example together. Never rebuild/replace
`r1` under its old URL.
Archive contents are deterministic for identical build inputs; runner/compiler
changes can affect rebuilt binary bytes, so pin/retain the recorded toolchain
and use the released checksums as the artifact identity.

## Minimal Windows decoder runtime

[`windows.json`](windows.json) separately defines the Windows shared-library
build. It uses the same checksum-pinned FFmpeg 7.1.3 source but disables all
features by default and enables only H.264, HEVC, AAC and Opus decoders,
resampling, and D3D11VA H.264/HEVC hardware configurations. GPL, nonfree,
version3, format/demuxer, filter, network and program support remain disabled.
The ARM64 and x64 builds preserve the FFmpeg 7.1 ABI consumed by
`FFmpeg.AutoGen` 7.1.1.
Its release tag is
`redraincast-ffmpeg-windows-decoders-7.1.3-r1`; its ZIP assets and build
materials use the matching `redraincast-ffmpeg-windows-decoders` prefix.

The manually dispatched
[Windows release workflow](.github/workflows/release-windows.yml) builds each
architecture on its native Windows runner, runs a codec/D3D11VA/ABI smoke test,
validates PE architecture and configuration, and assembles separate deterministic
ZIP files. It creates a **draft** release candidate with the matching FFmpeg
source, exact build materials, generated configuration, LGPL notice, provenance
and checksums. Test those exact draft assets in the Windows app before publishing:
download them with `gh release download <tag> --repo arisewanggithub/RedrainCast-Native`
and verify `SHA256SUMS`. If consumer testing fails, delete the draft and its tag,
fix the build, and create a new candidate revision. After consumer testing passes,
publish the draft with `gh release edit <tag> --repo arisewanggithub/RedrainCast-Native --draft=false`.
GitHub permits deleting a published immutable release, but its tag name can
never be reused; a failed public release would require a new revision and tag.
Draft candidates avoid burning a release tag during consumer testing.
Until a Windows release passes app validation, consumers should continue using
their existing pinned runtime.

The Android app remains pinned to the existing Android AAR coordinate and
checksum. Adding the separately tagged Windows decoder release does not change
that package, so it requires no Android app update. If a future Android AAR
revision is published, update the app's dependency coordinate and checksum
together; the app already supports both legacy and platform-specific tag paths.
The Maven/Ivy artifact coordinate remains tied to the AAR's existing
`ffmpeg-pcm-android` module name.

For a local build, use MSYS2 `CLANGARM64` with the ARM64 toolchain or `MINGW64`
with the x64 toolchain, plus `make`, `nasm` and `python`; run
`python scripts/build_windows.py arm64` or `python scripts/build_windows.py x64`
from the repository root. The script refuses a mismatched MSYS2 environment or
an existing build directory. Run `python -m unittest discover -s tests -v`
before changing the build contract or release workflow.

## Licensing

Original packager materials are [MIT](LICENSE). FFmpeg retains its upstream
copyright/author notices and **LGPL-2.1-or-later** terms; it is not relicensed.
GPL, nonfree and version3 are explicitly disabled and checked in `config.h`.
See [NOTICE](NOTICE) and the accompanying full upstream source and licenses.
Applications statically linking these libraries must separately meet their
LGPL notice/source/relink obligations; this package is not a waiver.

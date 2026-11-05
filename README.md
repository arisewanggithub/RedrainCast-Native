# RedrainCast native dependencies

Public, standalone build materials for **unmodified FFmpeg 7.1.3** PCM utilities.
There is no application code, JNI implementation, Java, Kotlin, codec, network
support, DEX, or runtime fallback in this repository/package. The small C smoke
test is only a build-time linker probe and is not shipped in the AAR.

## Immutable package contract

| Property | Value |
|---|---|
| Release tag | `ffmpeg-pcm-android-7.1.3-r1` |
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

Only the manually dispatched [release workflow](.github/workflows/release.yml)
builds the libraries. Three separate Ubuntu 24.04 runners build the ABI matrix.
The [package contract](package.json) pins source, SHA, NDK, API and all feature
flags. Only `libavutil.a`, `libswresample.a` and their installed public headers
are staged. Assembly is deliberately disabled for parity with the tested
source-build configuration. No local or application repository build is needed.

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

The build helper runs configure/make under `env -i` with only an explicit
public tool path, fixed temporary workspace, HOME, locale and source epoch.
It never uploads configure logs, environment dumps, SDK credentials, or
checkout authentication. Artifacts use explicit staging allowlists. Generated
`config.h`, `config_components.h` and `config.mak` contain only these sanitized
build settings. Paths in those settings refer to the documented fixed
`/tmp/redrain-ffmpeg` runner workspace, never a developer machine.

Every release contains:

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
Prefab version `7.1.3.2`). Update the contract and every version-pinned workflow
and consumer example together. Never rebuild/replace `r1` under its old URL.
Archive contents are deterministic for identical build inputs; runner/compiler
changes can affect rebuilt binary bytes, so pin/retain the recorded toolchain
and use the released checksums as the artifact identity.

## Licensing

Original packager materials are [MIT](LICENSE). FFmpeg retains its upstream
copyright/author notices and **LGPL-2.1-or-later** terms; it is not relicensed.
GPL, nonfree and version3 are explicitly disabled and checked in `config.h`.
See [NOTICE](NOTICE) and the accompanying full upstream source and licenses.
Applications statically linking these libraries must separately meet their
LGPL notice/source/relink obligations; this package is not a waiver.

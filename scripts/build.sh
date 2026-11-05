#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 ]]; then
    echo "Usage: build.sh ABI NDK_DIRECTORY" >&2
    exit 2
fi
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
work=/tmp/redrain-ffmpeg
mkdir -p "$work/home" "$work/tmp"
if [[ -e "$work/ndk" ]]; then
    echo "Build workspace already contains an NDK; use a fresh runner." >&2
    exit 1
fi
ln -s "$(realpath "$2")" "$work/ndk"
# FFmpeg configure records its environment. Do not pass the runner environment.
exec env -i \
    PATH="$work/ndk/toolchains/llvm/prebuilt/linux-x86_64/bin:/usr/bin:/bin" \
    HOME="$work/home" TMPDIR="$work/tmp" LC_ALL=C \
    python3 "$root/scripts/build.py" "$1"

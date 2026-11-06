#!/usr/bin/env sh
# Build benchmark fixtures outside the source tree.  The output is intentionally
# not committed; SHA256SUMS identifies the compiler-pinned reference result.
set -eu

out=${1:?usage: build.sh OUTPUT_DIRECTORY}
cc=${CC:-cc}
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$out"
"$cc" -O2 -fno-pie -no-pie -fno-ident -Wl,--build-id=none \
  "$root/fixture.c" -o "$out/native-bench-fixture"
sha256sum "$out/native-bench-fixture"

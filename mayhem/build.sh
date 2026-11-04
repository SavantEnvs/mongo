#!/usr/bin/env bash
#
# mayhem/build.sh — build the MongoDB BSON/JSON/BSONColumn/KeyString fuzz harnesses.
#
# Upstream builds with Bazel, whose hermetic toolchain and external repositories need the network, so
# this builds the needed subset with a generated ninja file (mayhem/gen_ninja.py): upstream's own
# BUILD.bazel source lists, its own code generators (error codes, IDL, config.h, releases.h) and the
# vendored src/third_party. Everything resolves from the image; nothing is fetched.
#
# Outputs: /mayhem/<fuzzer> and /mayhem/<fuzzer>-standalone (sanitized), and build/oracle/out/selftest
# (the project's normal flags, no sanitizers) which mayhem/test.sh runs.
set -euo pipefail

# clang rejects SOURCE_DATE_EPOCH='' (empty) — it must be unset or a valid integer.
[ -n "${SOURCE_DATE_EPOCH:-}" ] || unset SOURCE_DATE_EPOCH

: "${SANITIZER_FLAGS=-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer}"
: "${DEBUG_FLAGS:=-g -gdwarf-3}"
: "${CC:=clang}" ; : "${CXX:=clang++}" ; : "${LIB_FUZZING_ENGINE:=-fsanitize=fuzzer}"
: "${MAYHEM_JOBS:=$(nproc)}"
: "${COVERAGE_FLAGS=}"
: "${STANDALONE_FUZZ_MAIN:=/opt/mayhem/StandaloneFuzzTargetMain.c}"
export SANITIZER_FLAGS DEBUG_FLAGS CC CXX LIB_FUZZING_ENGINE MAYHEM_JOBS COVERAGE_FLAGS STANDALONE_FUZZ_MAIN

cd "$SRC"

# 1) Sanitized fuzz + standalone binaries (the project's code is compiled with $SANITIZER_FLAGS,
#    $DEBUG_FLAGS and -fsanitize=fuzzer-no-link; mayhem/lsan_off.cc turns LeakSanitizer off).
python3 mayhem/gen_ninja.py
ninja -f build/build.ninja -j"$MAYHEM_JOBS" fuzzers
for f in build/out/*; do cp -f "$f" "/mayhem/$(basename "$f")"; done

# 2) The test oracle: same sources, normal flags (no sanitizers, no -gdwarf-3), in its own tree.
ORACLE=1 python3 mayhem/gen_ninja.py
ninja -f build/oracle/build.ninja -j"$MAYHEM_JOBS" selftest

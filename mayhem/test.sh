#!/usr/bin/env bash
#
# mayhem/test.sh — RUN the known-answer self-test that mayhem/build.sh built (normal flags, no
# sanitizers): fromjson -> exact BSON bytes, validateBSON accept/reject, BSONColumn build/decode
# round-trip, KeyString encoding. Parses its own "SUMMARY: N tests run; F failed" line, so a neutered
# binary (no output) fails loudly instead of passing on its exit status.
set -uo pipefail
[ -n "${SOURCE_DATE_EPOCH:-}" ] || unset SOURCE_DATE_EPOCH
cd "$SRC"

emit_ctrf() {
  local tool="$1" passed="$2" failed="$3" skipped="${4:-0}" pending="${5:-0}" other="${6:-0}"
  local tests=$(( passed + failed + skipped + pending + other ))
  cat > "${CTRF_REPORT:-$SRC/ctrf-report.json}" <<JSON
{
  "results": {
    "tool": { "name": "$tool" },
    "summary": {
      "tests": $tests,
      "passed": $passed,
      "failed": $failed,
      "pending": $pending,
      "skipped": $skipped,
      "other": $other
    }
  }
}
JSON
  printf 'CTRF {"results":{"tool":{"name":"%s"},"summary":{"tests":%d,"passed":%d,"failed":%d,"pending":%d,"skipped":%d,"other":%d}}}\n' \
    "$tool" "$tests" "$passed" "$failed" "$pending" "$skipped" "$other"
  [ "$failed" -eq 0 ]
}

RUNNER="$SRC/build/oracle/out/selftest"
if [ ! -x "$RUNNER" ]; then
  echo "test runner $RUNNER missing (mayhem/build.sh should have built it)" >&2
  emit_ctrf "mongo-selftest" 0 1
  exit 1
fi

out="$("$RUNNER" 2>&1)"; rc=$?
printf '%s\n' "$out"
line="$(printf '%s\n' "$out" | sed -n 's/^SUMMARY: \([0-9]*\) tests run; \([0-9]*\) failed$/\1 \2/p' | tail -1)"
if [ -z "$line" ]; then
  echo "no SUMMARY line from $RUNNER" >&2
  emit_ctrf "mongo-selftest" 0 1
  exit 1
fi
run="${line% *}"; failed="${line#* }"
[ "$rc" -eq 0 ] || [ "$failed" -gt 0 ] || failed=1
emit_ctrf "mongo-selftest" $(( run - failed )) "$failed"

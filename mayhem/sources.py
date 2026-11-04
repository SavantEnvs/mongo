#!/usr/bin/env python3

# Executed by gen_ninja.py (shares its namespace).
EXCL = re.compile(r"(_test|_benchmark|_testing|_mock|_tester|test_|_bench|mock_|examples|/testing/|gmock|gtest|_test_)")


def keep_c(srcs, exts=(".c", ".cc", ".cpp")):
    return [s for s in srcs if s.endswith(exts) and "windows" not in s and "win32" not in s]


# ---- third party -----------------------------------------------------------------------------
absl = []
for d in ("base", "container", "crc", "debugging", "hash", "numeric", "profiling", "strings", "synchronization", "time", "types"):
    for f in sorted(glob.glob(f"src/third_party/abseil-cpp/dist/absl/{d}/**/*.cc", recursive=True)):
        if not EXCL.search(f[len("src/third_party/abseil-cpp/dist/") :]):
            absl.append(f)
compile_group("absl", absl, "3p")

compile_group("murmur", ["src/third_party/murmurhash3/MurmurHash3.cpp"], "3p")
compile_group("fmt", keep_c(target_srcs("src/third_party/fmt/BUILD.bazel", "fmt")), "3p")

compile_group(
    "pcre2",
    keep_c(target_srcs("src/third_party/pcre2/BUILD.bazel", "pcre2")),
    "3p",
    "-DPCRE2_CODE_UNIT_WIDTH=8 -DHAVE_CONFIG_H -Isrc/third_party/pcre2/build_posix",
)

INTEL_DEFS = (
    "-DDECIMAL_CALL_BY_REFERENCE=0 -DDECIMAL_GLOBAL_ROUNDING=0 -DDECIMAL_GLOBAL_EXCEPTION_FLAGS=0 "
    "-DUSE_COMPILER_F128_TYPE=0 -DUSE_COMPILER_F80_TYPE=0 -DUSE_NATIVE_QUAD_TYPE=0 -DLINUX=1 -Dlinux=1 "
    "-DUNCHANGED_BINARY_STATUS_FLAGS=0 -Defi2=1 -DEFI2=1 -Dgcc=1"
)
compile_group(
    "intel",
    keep_c(target_srcs("src/third_party/IntelRDFPMathLib20U1/BUILD.bazel", "intel_decimal128")),
    "nosan",
    INTEL_DEFS,
)

BOOST_BUILD = "src/third_party/boost/BUILD.bazel"
boost = []
for t in ("boost_system", "boost_filesystem", "boost_program_options", "boost_iostreams"):
    boost += keep_c(target_srcs(BOOST_BUILD, t))
boost += ["src/third_party/boost/libs/thread/src/future.cpp", "src/third_party/boost/libs/thread/src/pthread/once.cpp", "src/third_party/boost/libs/thread/src/pthread/thread.cpp"]
boost += keep_c(target_srcs(BOOST_BUILD, "boost_log"))
boost += ["src/third_party/boost/libs/log/src/syslog_backend.cpp"]
compile_group(
    "boost",
    sorted(set(boost)),
    "3p",
    "-DBOOST_THREAD_BUILD_LIB -DBOOST_THREAD_PTHREAD -DBOOST_LOG_USE_COMPILER_TLS -DBOOST_LOG_USE_STD_REGEX "
    "-DBOOST_LOG_WITHOUT_DEFAULT_FACTORIES -DBOOST_LOG_WITHOUT_IPC -DBOOST_LOG_WITHOUT_SETTINGS_PARSERS",
)

# ---- mongo -----------------------------------------------------------------------------------
base = target_srcs("src/mongo/BUILD.bazel", "base")
base = [s for s in base if s.endswith(".cpp")]
base += [
    "src/mongo/util/stacktrace_posix.cpp",
    "src/mongo/platform/shared_library_posix.cpp",
    "src/mongo/platform/stack_locator_linux.cpp",
    "src/mongo/stdx/set_terminate_internals.cpp",
    "src/mongo/util/boost_assert_shim.cpp",
    "src/mongo/util/debugger.cpp",
]
mongo_gen = [f"{GEN}/mongo/base/error_codes.cpp"]

compile_group("mongo", base + mongo_gen, "mongo")
TP = [archive(n, n) for n in ("absl", "murmur", "fmt", "pcre2", "intel", "boost")]
emit("build third_party: phony " + " ".join(TP))
emit(f"build {B}/third_party.stamp: phony third_party")

# ---- fuzz targets ----------------------------------------------------------------------------
BSON = "src/mongo/bson"
column = target_srcs(f"{BSON}/column/BUILD.bazel", "column")
validate = [f"{BSON}/bson_validate.cpp"]
shim = ["mayhem/idl_shim.cpp"]
KS = "src/mongo/db/storage/key_string"
COL = f"{BSON}/column"
GROUPS = {
    "column": column,
    "validate": validate + shim,
    "fuzzimpl": [f"{COL}/bsoncolumn_fuzzer_impl.cpp"],
    "keystring": [f"{KS}/key_string.cpp"],
    "oldvalidate": [f"{BSON}/bson_validate_old.cpp"],
    "lsan": ["mayhem/lsan_off.cc"],
    "colutil": [f"{COL}/bsoncolumn_test_util.cpp"],
    "colfuzzutil": [f"{COL}/bsoncolumn_fuzzer_util.cpp"],
}
# The libraries the newer fuzzers pull in (sbe_values for bsoncolumn_test_util.h, date_time_support,
# document_value, ...) go into one archive so each fuzzer links only the objects it references.
extra_srcs = [
    s
    for s in target_srcs("src/mongo/db/BUILD.bazel", "sbe_values_base") + target_srcs("src/mongo/db/BUILD.bazel", "sbe_values_ts_block")
    if s.endswith(".cpp")
]
extra_srcs += [
    "src/mongo/db/query/collation/collator_interface.cpp",
    "src/mongo/db/query/collation/collation_index_key.cpp",
    "src/mongo/db/query/datetime/date_time_support.cpp",
    f"{GEN}/mongo/db/basic_types_gen.cpp",
    "src/mongo/idl/idl_parser.cpp",
    "src/mongo/db/exec/convert_utils.cpp",
    "src/mongo/db/pipeline/field_path.cpp",
    "src/mongo/db/query/util/validate_id.cpp",
]
extra_srcs += target_srcs("src/mongo/db/exec/document_value/BUILD.bazel", "document_value")
timelib = keep_c([s for s in target_srcs("src/third_party/timelib/BUILD.bazel", "timelib") if s.endswith(".c")])
FUZZERS = {
    "simple8b_fuzzer": ([f"{COL}/simple8b_fuzzer.cpp"], ["column"]),
    "date_time_support_fuzzer": (["src/mongo/db/query/datetime/date_time_support_fuzzer.cpp"], []),
    "convert_string_to_object_fuzzer": (["src/mongo/db/exec/convert_string_to_object_fuzzer.cpp"], ["column", "validate"]),
    "bsoncolumn_decompress_fuzzer": ([f"{COL}/bsoncolumn_decompress_fuzzer.cpp"], ["column", "validate", "colutil", "keystring"]),
    "bsoncolumn_decompress_paths_fuzzer": ([f"{COL}/bsoncolumn_decompress_paths_fuzzer.cpp"], ["column", "validate", "colutil", "keystring"]),
    "bsoncolumn_builder_fuzzer": ([f"{COL}/bsoncolumn_builder_fuzzer.cpp"], ["column", "validate", "colutil", "colfuzzutil", "keystring"]),
    "fromjson_fuzzer": ([f"{BSON}/fromjson_fuzzer.cpp"], ["column", "validate"]),
    "bson_validate_fuzzer": ([f"{BSON}/bson_validate_fuzzer.cpp"], ["column", "validate", "oldvalidate"]),
    "bson_column_validate_fuzzer": ([f"{COL}/bson_column_validate_fuzzer.cpp"], ["column", "validate"]),
    "bsoncolumnbuilder_reopen_fuzzer": ([f"{COL}/bsoncolumnbuilder_reopen_fuzzer.cpp"], ["column", "validate", "fuzzimpl"]),
    "key_string_to_bson_fuzzer": ([f"{KS}/key_string_to_bson_fuzzer.cpp"], ["column", "validate", "keystring"]),
}
if ORACLE:
    idl_closure(column + validate + shim + ["mayhem/selftest.cpp"])
    for g in ("column", "validate", "keystring"):
        compile_group(g, GROUPS[g], "mongo")
    compile_group("selftest", ["mayhem/selftest.cpp"], "mongo")
    objs = objs_by_group["selftest"] + objs_by_group["mongo"] + objs_by_group["column"] + objs_by_group["validate"] + objs_by_group["keystring"]
    LIBS = f"{B}/libabsl.a {B}/libmurmur.a {B}/libfmt.a {B}/libpcre2.a {B}/libintel.a {B}/libboost.a -lpthread -ldl -lrt -lm"
    emit(f"build {B}/out/selftest: link {' '.join(objs)} | {B}/third_party.stamp")
    emit(f"  libs = {LIBS} {DBG}")
    emit("build selftest: phony " + f"{B}/out/selftest")
    FUZZERS = {}
else:
    idl_closure([f for g in GROUPS.values() for f in g] + extra_srcs + [h for h, _ in FUZZERS.values() for h in h])
    for g, srcs in GROUPS.items():
        compile_group(g, srcs, "mongo")
    compile_group("extra", extra_srcs, "mongo")
    compile_group("timelib", timelib, "3p", "-DHAVE_GETTIMEOFDAY -DHAVE_STRING_H -DHAVE_DIRENT_H -DHAVE_SYS_TIME_H -DHAVE_UNISTD_H -D_GNU_SOURCE")
    objs_by_group["extra"] += objs_by_group["timelib"]
    EXTRA_A = archive("extra", "extra")
    emit(f"build {OBJ}/standalone_main.o: cc_mongo {STANDALONE}")
    STANDALONE_EXTRA = ""
    if "address" not in SAN:
        # without the ASan runtime nothing defines the SanCov callbacks the instrumented objects reference
        emit(f"build {OBJ}/sancov_stub.o: cc_mongo mayhem/sancov_stub.c")
        STANDALONE_EXTRA = f"{OBJ}/sancov_stub.o"

    LIBS = f"{B}/libabsl.a {B}/libmurmur.a {B}/libfmt.a {B}/libpcre2.a {B}/libintel.a {B}/libboost.a -lpthread -ldl -lrt -lm"
    for name, (harness, groups) in FUZZERS.items():
        compile_group(name, harness, "mongo")
        objs = objs_by_group[name] + objs_by_group["mongo"] + objs_by_group["lsan"]
        for g in groups:
            objs += objs_by_group[g]
        emit(f"build {B}/out/{name}: link {' '.join(objs)} | {B}/third_party.stamp {EXTRA_A}")
        emit(f"  libs = {ENGINE} {EXTRA_A} {LIBS}")
        emit(f"build {B}/out/{name}-standalone: link {' '.join(objs)} {OBJ}/standalone_main.o {STANDALONE_EXTRA} | {B}/third_party.stamp {EXTRA_A}")
        emit(f"  libs = {EXTRA_A} {LIBS}")
    FUZZ_OUT = [f"{B}/out/{n}{sfx}" for n in FUZZERS for sfx in ("", "-standalone")]
    emit("build fuzzers: phony " + " ".join(FUZZ_OUT))

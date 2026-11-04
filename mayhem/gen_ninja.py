#!/usr/bin/env python3
"""Emit build/build.ninja: a Bazel-free build of the MongoDB bson/bsoncolumn fuzz harnesses.

Reads the source lists from upstream's BUILD.bazel files where practical so upstream additions to a
library are picked up; the curated parts are the library set, the Linux defines and the include roots.
"""
import glob
import os
import re
import sys

SRC = os.environ.get("SRC", os.getcwd())
os.chdir(SRC)
ORACLE = os.environ.get("ORACLE") == "1"  # clean build with the project's normal flags, for mayhem/test.sh
B = "build/oracle" if ORACLE else "build"
GEN = f"{B}/gen"
OBJ = f"{B}/obj"
OUT = os.environ.get("MAYHEM_OUT", "/mayhem")

CC = os.environ.get("CC", "clang")
CXX = os.environ.get("CXX", "clang++")
SAN = "" if ORACLE else os.environ.get("SANITIZER_FLAGS", "")
DBG = os.environ.get("COVERAGE_FLAGS", "") if ORACLE else os.environ.get("DEBUG_FLAGS", "-g -gdwarf-3")
COV = "" if ORACLE else "-fsanitize=fuzzer-no-link"
ENGINE = os.environ.get("LIB_FUZZING_ENGINE", "-fsanitize=fuzzer")
STANDALONE = os.environ.get("STANDALONE_FUZZ_MAIN", "/opt/mayhem/StandaloneFuzzTargetMain.c")
# Third-party code gets ASan only: UBSan findings in boost/abseil are not this project's defects.
SAN_3P = SAN.replace("address,undefined", "address").replace("undefined,address", "address")

# ---- BUILD.bazel parsing -------------------------------------------------------------------


def _block(path, name):
    txt = open(path).read()
    m = re.search(r'name\s*=\s*"%s"\s*,' % re.escape(name), txt)
    if not m:
        raise SystemExit(f"target {name} not found in {path}")
    start = txt.rfind("(", 0, m.start())
    depth = 0
    for i in range(start, len(txt)):
        if txt[i] == "(":
            depth += 1
        elif txt[i] == ")":
            depth -= 1
            if depth == 0:
                return txt[start : i + 1]
    raise SystemExit("unbalanced " + name)


def _list_attr(block, attr):
    m = re.search(r"\b%s\s*=\s*\[" % attr, block)
    if not m:
        return []
    i = m.end()
    depth = 1
    j = i
    while depth:
        if block[j] == "[":
            depth += 1
        elif block[j] == "]":
            depth -= 1
        j += 1
    return re.findall(r'"([^"]+)"', block[i : j - 1])


def target_srcs(build_file, name):
    """Plain (non-select) srcs of a rule, as repo-relative paths; ':x_gen'/'x_source' labels kept as-is."""
    d = os.path.dirname(build_file)
    out = []
    for s in _list_attr(_block(build_file, name), "srcs"):
        if s.startswith("//"):
            pkg, _, f = s[2:].partition(":")
            out.append(f"{pkg}/{f}" if "." in f else s)
        elif s.startswith(":"):
            out.append(s)
        else:
            out.append(f"{d}/{s}")
    return out


# ---- ninja plumbing ------------------------------------------------------------------------

lines = []
objs_by_group = {}


def emit(s=""):
    lines.append(s)


def obj_path(src):
    return f"{OBJ}/{src.replace('/', '__')}.o"


def compile_group(group, srcs, kind, extra=""):
    out = objs_by_group.setdefault(group, [])
    for s in srcs:
        o = obj_path(s)
        rule = "cc" if s.endswith(".c") else "cxx"
        emit(f"build {o}: {rule}_{kind} {s}")
        if extra:
            emit(f"  extra = {extra}")
        out.append(o)


def archive(name, group):
    emit(f"build {B}/lib{name}.a: ar {' '.join(objs_by_group[group])}")
    return f"{B}/lib{name}.a"


# ---- flags ---------------------------------------------------------------------------------

BOOST_LIBS = [d for d in glob.glob("src/third_party/boost/libs/*/include") + glob.glob("src/third_party/boost/libs/*/*/include")]
INCLUDES = (
    ["src", GEN, "src/third_party/boost"]
    + sorted(BOOST_LIBS)
    + [
        "src/third_party/abseil-cpp/dist",
        "src/third_party/fmt/dist/include",
        "src/third_party/pcre2/src",
        "src/third_party/SafeInt",
        "src/third_party/IntelRDFPMathLib20U1/LIBRARY/src",
        "src/third_party/immer/dist",
        "src/third_party/murmurhash3",
        "src/third_party/croaring/dist",
        "src/third_party/zlib/dist",
        "src/third_party/zstandard/zstd/lib",
        "src/third_party/snappy/dist",
        "src/third_party/libstemmer_c/dist/include",
        "src/third_party/timelib/dist",
        "src/third_party/nlohmann-json/include",
    ]
)
INC = " ".join(f"-I{i}" for i in INCLUDES if os.path.isdir(i) or i == GEN)

BOOST_DEFS = [
    "BOOST_ENABLE_ASSERT_DEBUG_HANDLER",
    "BOOST_FILESYSTEM_NO_CXX20_ATOMIC_REF",
    "BOOST_LOG_NO_SHORTHAND_NAMES",
    "BOOST_LOG_WITHOUT_THREAD_ATTR",
    "BOOST_MATH_NO_LONG_DOUBLE_MATH_FUNCTIONS",
    "BOOST_SYSTEM_NO_DEPRECATED",
    "BOOST_THREAD_USES_DATETIME",
    "BOOST_THREAD_VERSION=5",
    "BOOST_LOG_USE_NATIVE_SYSLOG",
    "BOOST_BIND_GLOBAL_PLACEHOLDERS",
]
MONGO_DEFS = BOOST_DEFS + ["ABSL_FORCE_ALIGNED_ACCESS", "PCRE2_STATIC", "SAFEINT_USE_INTRINSICS=0"]
if "address" in SAN:
    MONGO_DEFS.append("ADDRESS_SANITIZER")
if "undefined" in SAN:
    MONGO_DEFS.append("UNDEFINED_BEHAVIOR_SANITIZER")
MONGO_D = " ".join(f"-D{d}" for d in MONGO_DEFS)

OPT = "-O1"
COMMON = f"{OPT} -fPIC {DBG} -w -pthread"
emit(f"builddir = {B}")
emit(f"cxxbase = -std=c++20 {COMMON} {MONGO_D} {INC}")
emit(f"cbase = {COMMON} {MONGO_D} {INC}")
emit(f"san = {SAN} {COV}")
emit(f"san3p = {SAN_3P}")
emit(f"dbg = {DBG}")
emit("")
for kind, san in (("mongo", "$san"), ("3p", "$san3p")):
    emit(f"rule cxx_{kind}")
    emit(f"  command = {CXX} -MMD -MF $out.d $cxxbase {san} $extra -c $in -o $out")
    emit("  depfile = $out.d")
    emit("  deps = gcc")
    emit(f"rule cc_{kind}")
    emit(f"  command = {CC} -MMD -MF $out.d $cbase {san} $extra -c $in -o $out")
    emit("  depfile = $out.d")
    emit("  deps = gcc")
emit("rule cc_nosan")
emit(f"  command = {CC} -MMD -MF $out.d $cbase $extra -c $in -o $out")
emit("  depfile = $out.d")
emit("  deps = gcc")
emit("rule ar")
emit("  command = rm -f $out && ar rcs $out $in")
emit("rule link")
emit(f"  command = {CXX} {SAN} $dbg $in $libs -o $out")
emit("")

# ---- generated sources (produced eagerly; ninja only compiles) ---------------------------------

import subprocess


def run(cmd):
    subprocess.check_call(cmd, shell=True)


os.makedirs(f"{GEN}/mongo/base", exist_ok=True)
for ext in ("h", "cpp"):
    run(
        f"python3 src/mongo/base/generate_error_codes.py src/mongo/base/error_codes.yml "
        f"src/mongo/base/error_codes.tpl.{ext} {GEN}/mongo/base/error_codes.{ext}"
    )
run(f"python3 mayhem/gen_config.py src/mongo/config.h.in {GEN}/mongo/config.h")

MONGO_VERSION = re.search(r"MONGO_VERSION=(\S+)", open(".bazelrc.target_mongo_version").read()).group(1)
os.makedirs(f"{GEN}/mongo/util/version", exist_ok=True)
run(
    f"python3 buildscripts/cheetah_source_generator.py -o {GEN}/mongo/util/version/releases.h "
    f"src/mongo/util/version/releases.tpl.h src/mongo/util/version/releases.yml {MONGO_VERSION}"
)

INC_RE = re.compile(r'^\s*#\s*include\s+"(mongo/[^"]+)"', re.M)
_seen = {}


def includes_of(path):
    if path not in _seen:
        try:
            _seen[path] = INC_RE.findall(open(path, errors="replace").read())
        except OSError:
            _seen[path] = []
    return _seen[path]


def idl_closure(roots):
    """Generate the IDL headers reachable from `roots` via #include; return the set of IDL paths."""
    todo, done, idls = list(roots), set(), set()
    while todo:
        f = todo.pop()
        if f in done:
            continue
        done.add(f)
        for inc in includes_of(f):
            if inc.endswith("_gen.h"):
                idl = "src/" + inc[: -len("_gen.h")] + ".idl"
                if idl not in idls and os.path.exists(idl):
                    idls.add(idl)
                    h, c = f"{GEN}/{inc}", f"{GEN}/{inc[:-2]}.cpp"
                    os.makedirs(os.path.dirname(h), exist_ok=True)
                    run(f"python3 buildscripts/idl/idlc.py --include src --base_dir {GEN} --header {h} --output {c} {idl}")
                    todo.append(h)
                continue
            for root in ("src/", GEN + "/"):
                if os.path.exists(root + inc):
                    todo.append(root + inc)
                    break
    return idls


exec(open("mayhem/sources.py").read())
open(f"{B}/build.ninja", "w").write("\n".join(lines) + "\n")

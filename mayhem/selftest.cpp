// Known-answer checks over the BSON / JSON / BSONColumn / KeyString code the fuzz targets exercise.
#include "mongo/bson/bson_validate.h"
#include "mongo/bson/bsonobjbuilder.h"
#include "mongo/bson/column/bsoncolumn.h"
#include "mongo/bson/column/bsoncolumnbuilder.h"
#include "mongo/bson/json.h"
#include "mongo/db/storage/key_string/key_string.h"

#include <cstdio>
#include <string>

using namespace mongo;

static int g_run = 0, g_failed = 0;

#define CHECK(name, cond)                                  \
    do {                                                   \
        ++g_run;                                           \
        if (!(cond)) {                                     \
            ++g_failed;                                    \
            std::printf("FAIL %s (line %d)\n", name, __LINE__); \
        } else {                                           \
            std::printf("ok   %s\n", name);                \
        }                                                  \
    } while (0)

static std::string hex(const char* p, size_t n) {
    static const char* d = "0123456789abcdef";
    std::string s;
    for (size_t i = 0; i < n; ++i) {
        s += d[(unsigned char)p[i] >> 4];
        s += d[(unsigned char)p[i] & 15];
    }
    return s;
}

int main() {
    // fromjson -> exact BSON bytes
    BSONObj o = fromjson(R"({"a":1,"b":"x"})");
    CHECK("fromjson bytes", hex(o.objdata(), o.objsize()) == "150000001061000100000002620002000000780000");
    CHECK("fromjson int type", o["a"].type() == BSONType::numberInt && o["a"].numberInt() == 1);
    CHECK("fromjson string", o["b"].type() == BSONType::string && o["b"].String() == "x");

    BSONObj big = fromjson(R"({"n":{"$numberLong":"5000000000"},"arr":[1,2,{"k":null}]})");
    CHECK("fromjson numberLong", big["n"].type() == BSONType::numberLong && big["n"].numberLong() == 5000000000LL);
    CHECK("fromjson array", big["arr"].Array().size() == 3 && big["arr"].Array()[2].Obj()["k"].isNull());

    bool threw = false;
    try {
        fromjson("{\"a\":");
    } catch (const DBException&) {
        threw = true;
    }
    CHECK("fromjson rejects truncated json", threw);

    // validateBSON accepts well-formed, rejects corrupted
    CHECK("validate ok", validateBSON(o.objdata(), o.objsize()).isOK());
    CHECK("validate big ok", validateBSON(big.objdata(), big.objsize()).isOK());
    CHECK("validate rejects short buffer", !validateBSON(o.objdata(), o.objsize() - 1).isOK());
    std::string bad(o.objdata(), o.objsize());
    bad[bad.size() - 1] = 1;
    CHECK("validate rejects missing terminator", !validateBSON(bad.data(), bad.size()).isOK());
    std::string badType(o.objdata(), o.objsize());
    badType[4] = (char)0x6f;
    CHECK("validate rejects unknown type", !validateBSON(badType.data(), badType.size()).isOK());

    // BSONColumn: build -> exact decode
    BSONColumnBuilder<> cb;
    for (int i = 0; i < 20; ++i)
        cb.append(BSON("" << i * 3).firstElement());
    BSONBinData bin = cb.finalize();
    CHECK("column validate", validateBSONColumn((const char*)bin.data, bin.length).isOK());
    BSONColumn col((const char*)bin.data, bin.length);
    int idx = 0;
    bool same = true;
    for (auto&& e : col) {
        same = same && e.type() == BSONType::numberInt && e.numberInt() == idx * 3;
        ++idx;
    }
    CHECK("column roundtrip", same && idx == 20);

    // KeyString: exact encoding and decode
    key_string::Builder ks(key_string::Version::V1, BSON("" << 1), Ordering::make(BSONObj()));
    auto v = ks.getView();
    CHECK("keystring bytes", hex(v.data(), v.size()) == "2b0204");

    std::printf("SUMMARY: %d tests run; %d failed\n", g_run, g_failed);
    return g_failed ? 1 : 0;
}

// Definitions of the bson_validate.idl server parameters, so bson_validate links without server_base.
#include "mongo/bson/bson_validate_gen.h"

namespace mongo {
int bsonTestValidationVersion = 2;
Atomic<long long> bsonMaxExpandedMemUsage{209715200};
}  // namespace mongo

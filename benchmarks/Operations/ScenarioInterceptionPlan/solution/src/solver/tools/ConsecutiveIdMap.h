////////////////////////////////
/// usage:	1.	map arbitrary identifiers to zero-based consecutive integers.
/// 
/// note:	1.	no removal but insertion only.
////////////////////////////////

#ifndef CN_HUST_HAFV_UTIL_CONSECUTIVE_ID_MAP_H
#define CN_HUST_HAFV_UTIL_CONSECUTIVE_ID_MAP_H


#include <vector>
#include <unordered_map>

#include "./Typedef.h"


namespace goal {

template<typename ArbitraryId = int, typename ConsecutiveId = int>
class ConsecutiveIdMap {
public:
    static constexpr ConsecutiveId InvalidId = -1;

    ConsecutiveIdMap(ConsecutiveId idNumHint, ConsecutiveId bucketNumHint)
        : count(0), idMap(bucketNumHint) {
        idList.reserve(sCast<size_t>(idNumHint));
    }
    ConsecutiveIdMap(ConsecutiveId idNumHint) : ConsecutiveIdMap(idNumHint, idNumHint) {}
    ConsecutiveIdMap() : count(0) {}


    // track a new arbitrary ID or return the sequence of a tracked one.
    ConsecutiveId toConsecutiveId(ArbitraryId arbitraryId) {
        auto iter = idMap.find(arbitraryId);
        if (iter != idMap.end()) { return iter->second; }
        idList.push_back(arbitraryId);
        return idMap[arbitraryId] = (count++);
    }

    ConsecutiveId getConsecutiveId(ArbitraryId arbitraryId) const {
        auto iter = idMap.find(arbitraryId);
        return (iter != idMap.end()) ? iter->second : InvalidId;
    }

    // return the consecutiveId_th tracked arbitrary ID.
    ArbitraryId toArbitraryId(ConsecutiveId consecutiveId) const { return idList[consecutiveId]; } // TODO[szx][0]: rename it to `getArbitraryId`.


    // number of tracked IDs.
    ConsecutiveId count;
    // idList[consecutiveId] == arbitraryId.
    std::vector<ArbitraryId> idList;
    // idMap[arbitraryId] == consecutiveId.
    std::unordered_map<ArbitraryId, ConsecutiveId> idMap;
};

}


#endif // SZX_CPPUTILIBS_ZERO_BASED_CONSECUTIVE_ID_MAP_H

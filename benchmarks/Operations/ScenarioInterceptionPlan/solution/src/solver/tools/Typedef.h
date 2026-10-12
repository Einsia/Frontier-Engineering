////////////////////////////////
/// usage : 1.	type aliases for simple types.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_TYPEDEF_H
#define CN_HUST_GOAL_COMMON_TYPEDEF_H


#include <string>
#include <array>
#include <vector>
#include <set>
#include <map>
#include <unordered_map>
#include <unordered_set>
#include <functional>
#include <cstring>


namespace goal {

// zero-based consecutive integer identifier.
using ID = long long;

// real-world time for running state recording.
using Millisecond = long long;

// number of performed neighborhood moves in local search.
using Iteration = int;

// counter or other value without unit.
using Int = long long;
using Real = double;

using Str = std::string;
using StrPos = Str::size_type;

template<typename T, size_t Size>
using Arr = std::array<T, Size>;

template<typename T>
using Vec = std::vector<T>;

template<typename T>
using Set = std::set<T>;

template<typename T>
using HashSet = std::unordered_set<T>;

template<typename Key, typename Value>
using Map = std::map<Key, Value>;

template<typename Key, typename Value>
using HashMap = std::unordered_map<Key, Value>;


template<typename Prototype>
using Func = std::function<Prototype>;


struct Void {};


template<typename NewType, typename OldType>
constexpr NewType sCast(OldType obj) { return static_cast<NewType>(obj); }

template<typename T>
const char* toBytes(const T *ptr) { return reinterpret_cast<const char*>(ptr); }

template<typename T>
char* toBytes(T *ptr) { return reinterpret_cast<char*>(ptr); }

// shallow compare of object.
template<typename T>
bool eq(const T& l, const T& r) { return std::memcmp(&l, &r, sizeof(T)) == 0; }


static constexpr ID InvalidId = -1;

}


#endif // CN_HUST_GOAL_COMMON_TYPEDEF_H

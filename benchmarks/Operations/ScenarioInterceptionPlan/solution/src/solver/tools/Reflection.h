////////////////////////////////
/// usage : 1.	basic runtime reflection utility for debugging.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_REFLECTION
#define CN_HUST_GOAL_COMMON_REFLECTION


#include "./Typedef.h"
#include "./Preprocessor.h"
#include "./Log.h"

#define RegisterVarName(name)  Reflection::varNameMap[&name] = #name "@" __FILE__ "#" RESOLVED_STRINGIFY(__LINE__)
#define UnregisterVarName(name)  if (Reflection::hasVar(&name)) { Reflection::varNameMap.erase(&name); }
#define GetVarName(name)  (Reflection::hasVar(&name) ? Reflection::varNameMap[&name] : "")
#define PrintVarName(name)  if (Reflection::hasVar(&name)) { Log(Log::Level::Debug) << Reflection::varNameMap[&name] << std::endl; }

#define UnregisterThisVarName  if (Reflection::hasVar(this)) { Reflection::varNameMap.erase(this); }
#define ThisVarName  (Reflection::hasVar(this) ? Reflection::varNameMap[this] : "")
#define PrintThisVarName  if (Reflection::hasVar(this)) { Log(Log::Level::Debug) << Reflection::varNameMap[this] << std::endl; }


namespace goal {

struct Reflection {
    static bool hasVar(void *ptr) { return varNameMap.find(ptr) != varNameMap.end(); }

    static Map<void*, const char*> varNameMap;
};

}


#endif // CN_HUST_GOAL_COMMON_REFLECTION

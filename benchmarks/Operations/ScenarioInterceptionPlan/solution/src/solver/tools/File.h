////////////////////////////////
/// usage : 1.	file i/o utilities.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_FILE_H
#define CN_HUST_GOAL_COMMON_FILE_H


#include <vector>

#include "./Typedef.h"


namespace goal {
namespace file {

struct Lines : public Vec<char*> {
    Str charBuf;
};

Str readAllText(const Str& path);
Lines readAllLines(const Str& path);

}
}


#endif // CN_HUST_GOAL_COMMON_FILE_H

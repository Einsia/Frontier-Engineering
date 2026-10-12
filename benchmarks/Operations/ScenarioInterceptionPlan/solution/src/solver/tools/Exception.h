////////////////////////////////
/// usage : 1.	some useful exceptions.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_EXCEPTION_H
#define CN_HUST_GOAL_COMMON_EXCEPTION_H


#include "./Flag.h"

#include <exception>


namespace goal {

struct NotImplementedException : public std::exception {
    virtual const char* what() const noexcept override {
        return "not implemented yet.";
    }
};

struct IndexOutOfRangeException : public std::exception {
    virtual const char* what() const noexcept override {
        return "index out of range.";
    }
};

struct DuplicateItemException : public std::exception {
    virtual const char* what() const noexcept override {
        return "duplicate item.";
    }
};

struct ItemNotExistException : public std::exception {
    virtual const char* what() const noexcept override {
        return "item not exist.";
    }
};

}


#endif // CN_HUST_GOAL_COMMON_EXCEPTION_H

////////////////////////////////
/// usage : 1.	predefine macros for third party lib configuration.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_PREPROCESSOR_H
#define CN_HUST_GOAL_COMMON_PREPROCESSOR_H


namespace goal {

// if there is "#define x  y", VERBATIM_STRINGIFY(x) will get "x".
#define VERBATIM_STRINGIFY(x)  #x
// if there is "#define x  y", RESOLVED_STRINGIFY(x) will get "y".
#define RESOLVED_STRINGIFY(x)  VERBATIM_STRINGIFY(x)


#define VERBATIM_CONCAT(a,b)  a##b
#define VERBATIM_CONCAT2(a,b,c)  a##b##c
#define VERBATIM_CONCAT3(a,b,c,d)  a##b##c##d
#define RESOLVED_CONCAT(a,b)  VERBATIM_CONCAT(a,b)
#define RESOLVED_CONCAT2(a,b,c)  VERBATIM_CONCAT2(a,b,c)
#define RESOLVED_CONCAT3(a,b,c,d)  VERBATIM_CONCAT3(a,b,c,d)


#define SEE(x)  #x "=" << x

}


#endif // CN_HUST_GOAL_COMMON_PREPROCESSOR_H

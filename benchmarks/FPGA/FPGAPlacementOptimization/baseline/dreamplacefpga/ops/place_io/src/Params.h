/*************************************************************************
    > File Name: Params.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_PARAMS_H
#define DREAMPLACE_PARAMS_H

#include <string>
#include <vector>
#include <set>
#include <limbo/programoptions/ProgramOptions.h>

#include "Enums.h"

DREAMPLACE_BEGIN_NAMESPACE

/// placement solution format 
enum SolutionFileFormat 
{
    BOOKSHELF, // write placement solution .plx in bookshlef format
    BOOKSHELFALL // write .nodes, .nets, ... in bookshlef format
};

/// convert enums to string 
extern std::string toString(SolutionFileFormat ff);

DREAMPLACE_END_NAMESPACE

#endif

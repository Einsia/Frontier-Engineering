/*************************************************************************
    > File Name: Params.cpp
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#include "Params.h"
#include "Util.h"
#include <iostream>
#include <fstream>
#include <boost/bind.hpp>
#include <boost/algorithm/string.hpp>
#include <limbo/string/String.h>

DREAMPLACE_BEGIN_NAMESPACE

std::string toString(SolutionFileFormat ff)
{
    switch (ff)
    {
        case BOOKSHELF: return "BOOKSHELF";
        case BOOKSHELFALL: return "BOOKSHELFALL";
        default: return "UNKNOWN";
    }
}

DREAMPLACE_END_NAMESPACE

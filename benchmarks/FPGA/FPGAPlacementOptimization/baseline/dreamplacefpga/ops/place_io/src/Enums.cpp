/*************************************************************************
    > File Name: Enums.cpp
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#include "Enums.h"

DREAMPLACE_BEGIN_NAMESPACE

#ifndef ENUM2STR
#define ENUM2STR(map, var) \
    map[enum_wrap_type::var] = #var
#endif

#ifndef STR2ENUM
#define STR2ENUM(map, var) \
    map[#var] = enum_wrap_type::var
#endif

std::string InstBlk::enum2Str(InstBlk::enum_type const& e) const
{
    static std::map<enum_type, std::string> mEnum2Str;
    static bool init = true;

    if (init)
    {   
        ENUM2STR(mEnum2Str, LUT0); 
        ENUM2STR(mEnum2Str, LUT1); 
        ENUM2STR(mEnum2Str, LUT2); 
        ENUM2STR(mEnum2Str, LUT3); 
        ENUM2STR(mEnum2Str, LUT4); 
        ENUM2STR(mEnum2Str, LUT5); 
        ENUM2STR(mEnum2Str, LUT6); 
        ENUM2STR(mEnum2Str, LUT6_2); 
        ENUM2STR(mEnum2Str, FDRE); 
        ENUM2STR(mEnum2Str, DSP48E2); 
        ENUM2STR(mEnum2Str, RAMB36E2); 
        ENUM2STR(mEnum2Str, BUFGCE); 
        ENUM2STR(mEnum2Str, IBUF); 
        ENUM2STR(mEnum2Str, OBUF); 
        ENUM2STR(mEnum2Str, UNKNOWN); 
        init = false;
    }

    return mEnum2Str.at(e);
}

InstBlk::enum_type InstBlk::str2Enum(std::string const& s) const
{
    static std::map<std::string, enum_type> mStr2Enum;
    static bool init = true;

    if (init)
    {   
        STR2ENUM(mStr2Enum, LUT0);
        STR2ENUM(mStr2Enum, LUT1); 
        STR2ENUM(mStr2Enum, LUT2); 
        STR2ENUM(mStr2Enum, LUT3); 
        STR2ENUM(mStr2Enum, LUT4); 
        STR2ENUM(mStr2Enum, LUT5); 
        STR2ENUM(mStr2Enum, LUT6); 
        STR2ENUM(mStr2Enum, LUT6_2); 
        STR2ENUM(mStr2Enum, FDRE); 
        STR2ENUM(mStr2Enum, DSP48E2); 
        STR2ENUM(mStr2Enum, RAMB36E2); 
        STR2ENUM(mStr2Enum, BUFGCE); 
        STR2ENUM(mStr2Enum, IBUF); 
        STR2ENUM(mStr2Enum, OBUF); 
        STR2ENUM(mStr2Enum, UNKNOWN); 
        init = false;
    }

    std::map<std::string, enum_type>::const_iterator found = mStr2Enum.find(s);
    if (found == mStr2Enum.end())
    {
        dreamplacePrint(kWARN, "%s unknown enum type %s, set to UNKNOWN\n", __func__, s.c_str());
        return enum_wrap_type::UNKNOWN; 
    }
    else 
    {
        return found->second;
    }
}

std::string Site::enum2Str(Site::enum_type const& e) const
{
    static std::map<enum_type, std::string> mEnum2Str;
    static bool init = true;

    if (init)
    {
        ENUM2STR(mEnum2Str, IO); 
        ENUM2STR(mEnum2Str, SLICE); 
        ENUM2STR(mEnum2Str, DSP); 
        ENUM2STR(mEnum2Str, BRAM); 
        ENUM2STR(mEnum2Str, UNKNOWN); 
        init = false;
    }

    return mEnum2Str.at(e);
}

Site::enum_type Site::str2Enum(std::string const& s) const
{
    static std::map<std::string, enum_type> mStr2Enum;
    static bool init = true;

    if (init)
    {
        STR2ENUM(mStr2Enum, IO); 
        STR2ENUM(mStr2Enum, SLICE); 
        STR2ENUM(mStr2Enum, DSP); 
        STR2ENUM(mStr2Enum, BRAM); 
        STR2ENUM(mStr2Enum, UNKNOWN); 
        init = false;
    }

    std::map<std::string, enum_type>::const_iterator found = mStr2Enum.find(s);
    if (found == mStr2Enum.end())
    {
        dreamplacePrint(kWARN, "%s unknown enum type %s, set to UNKNOWN\n", __func__, s.c_str());
        return enum_wrap_type::UNKNOWN; 
    }
    else 
    {
        return found->second;
    }
}

DREAMPLACE_END_NAMESPACE

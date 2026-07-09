/*************************************************************************
    > File Name: Enums.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_ENUMS_H
#define DREAMPLACE_ENUMS_H

#include <string>
#include <map>
#include <ostream>
#include "Util.h"

DREAMPLACE_BEGIN_NAMESPACE

/// base class for enumeration types 
/// these types are not recommended for storage, since they takes larger memory 
template <typename EnumType>
class EnumExt
{
	public:
        typedef EnumType enum_type;
		EnumExt() {}
		EnumExt& operator=(EnumExt const& rhs)
		{
			if (this != &rhs)
				m_value = rhs.m_value;
			return *this;
		}
		EnumExt& operator=(enum_type const& rhs)
		{
			m_value = rhs;
			return *this;
		}
		EnumExt& operator=(std::string const& rhs)
        {
            m_value = str2Enum(rhs);
            return *this;
        }
		virtual operator std::string() const
        {
            return enum2Str(m_value);
        }
        operator int() const 
        {
            return value(); 
        }
        enum_type value() const 
        {
            return m_value;
        }

		bool operator==(EnumExt const& rhs) const {return m_value == rhs.m_value;}
		bool operator==(enum_type const& rhs) const {return m_value == rhs;}
		bool operator==(std::string const& rhs) const {return *this == EnumExt(rhs);}
		bool operator!=(EnumExt const& rhs) const {return m_value != rhs.m_value;}
		bool operator!=(enum_type const& rhs) const {return m_value != rhs;}
		bool operator!=(std::string const& rhs) const {return *this != EnumExt(rhs);}

		friend std::ostream& operator<<(std::ostream& os, const EnumExt& rhs)
		{
			rhs.print(os);
			return os;
		}
	protected:
		virtual void print(std::ostream& os) const {os << this->enum2Str(m_value);}

        virtual std::string enum2Str(enum_type const&) const = 0;
        virtual enum_type str2Enum(std::string const&) const = 0;

        enum_type m_value;
};

/// class InstBlk denotes Instance type 
struct InstBlkEnum
{
    enum InstBlkType 
    {
		LUT0 = 0, 
        LUT1 = 0, 
        LUT2 = 1, 
        LUT3 = 2, 
        LUT4 = 3, 
        LUT5 = 4, 
        LUT6 = 5, 
        LUT6_2 = 5, 
        FDRE = 6, 
        DSP48E2 = 7, 
        RAMB36E2 = 8, 
        BUFGCE = 9, 
        IBUF = 10, 
        OBUF = 11, 
        UNKNOWN = 12 
    };
};
class InstBlk : public EnumExt<InstBlkEnum::InstBlkType>
{
	public:
        typedef InstBlkEnum enum_wrap_type;
        typedef enum_wrap_type::InstBlkType enum_type;
        typedef EnumExt<enum_type> base_type;

		InstBlk() : base_type() {m_value = enum_wrap_type::UNKNOWN;}
		InstBlk(InstBlk const& rhs) : base_type() {m_value = rhs.m_value;}
		InstBlk(enum_type const& rhs) : base_type() {m_value = rhs;}
		InstBlk(std::string const& rhs) : base_type() {m_value = str2Enum(rhs);}
		InstBlk& operator=(InstBlk const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}
		InstBlk& operator=(enum_type const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}
		InstBlk& operator=(std::string const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}

	protected:
        virtual std::string enum2Str(enum_type const& e) const;
        virtual enum_type str2Enum(std::string const& s) const;
};


/// class Site denotes Site type 
struct SiteEnum
{
    enum SiteType 
    {
        IO = 0, 
        SLICE = 1, 
        DSP = 2, 
        BRAM = 3, 
        UNKNOWN = 4 
    };
};
class Site : public EnumExt<SiteEnum::SiteType>
{
	public:
        typedef SiteEnum enum_wrap_type;
        typedef enum_wrap_type::SiteType enum_type;
        typedef EnumExt<enum_type> base_type;

		Site() : base_type() {m_value = enum_wrap_type::UNKNOWN;}
		Site(Site const& rhs) : base_type() {m_value = rhs.m_value;}
		Site(enum_type const& rhs) : base_type() {m_value = rhs;}
		Site(std::string const& rhs) : base_type() {m_value = str2Enum(rhs);}
		Site& operator=(Site const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}
		Site& operator=(enum_type const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}
		Site& operator=(std::string const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}

	protected:
        virtual std::string enum2Str(enum_type const& e) const;
        virtual enum_type str2Enum(std::string const& s) const;
};

/// class RegionEnumType denotes the region type defined in DEF 
struct RegionTypeEnum
{
    enum RegionEnumType
    {
        FENCE = 0, 
        GUIDE = 1, 
        UNKNOWN = 2
    };
};

class RegionType : public EnumExt<RegionTypeEnum::RegionEnumType>
{
	public:
        typedef RegionTypeEnum enum_wrap_type;
        typedef enum_wrap_type::RegionEnumType enum_type;
        typedef EnumExt<enum_type> base_type;

		RegionType() : base_type() {m_value = enum_wrap_type::UNKNOWN;}
		RegionType(RegionType const& rhs) : base_type() {m_value = rhs.m_value;}
		RegionType(enum_type const& rhs) : base_type() {m_value = rhs;}
		RegionType(std::string const& rhs) : base_type() {m_value = str2Enum(rhs);}
		RegionType& operator=(RegionType const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}
		RegionType& operator=(enum_type const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}
		RegionType& operator=(std::string const& rhs)
		{
            this->base_type::operator=(rhs);
			return *this;
		}

	protected:
        virtual std::string enum2Str(enum_type const& e) const;
        virtual enum_type str2Enum(std::string const& s) const;
};


DREAMPLACE_END_NAMESPACE

#endif

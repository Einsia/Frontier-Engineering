/*************************************************************************
    > File Name: Net.cpp
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#include "Net.h"

DREAMPLACE_BEGIN_NAMESPACE

Net::Net() 
    : Net::base_type()
    , m_name("")
    , m_id(std::numeric_limits<Net::index_type>::max())
    , m_weight(1)
    , m_vPinId()
{
}
Net::Net(Net const& rhs)
    : Net::base_type(rhs)
{
    copy(rhs);
}
Net& Net::operator=(Net const& rhs)
{
    if (this != &rhs)
    {
        this->base_type::operator=(rhs);
        copy(rhs);
    }
    return *this;
}
void Net::copy(Net const& rhs)
{
    m_name = rhs.m_name;
    m_id = rhs.m_id;
    m_weight = rhs.m_weight; 
    m_vPinId = rhs.m_vPinId;
}

DREAMPLACE_END_NAMESPACE

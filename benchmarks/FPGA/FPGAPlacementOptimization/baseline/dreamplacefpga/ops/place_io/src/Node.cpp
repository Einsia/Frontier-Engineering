/*************************************************************************
    > File Name: Node.cpp
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#include "Node.h"

DREAMPLACE_BEGIN_NAMESPACE

Node::Node() 
    : Node::base_type()
    , m_name("")
    , m_typeName("")
    , m_id(std::numeric_limits<Node::index_type>::max())
    , m_libCellId(std::numeric_limits<Node::index_type>::max())
    , m_type(std::numeric_limits<Node::index_type>::max())
    , m_cType(InstBlkEnum::UNKNOWN)
    , m_x(0.0)
    , m_y(0.0)
    , m_z(0)
    , m_fixed(false)
    , m_vPinId()
{
}
Node::Node(Node const& rhs)
    : Node::base_type(rhs)
{
    copy(rhs);
}
Node& Node::operator=(Node const& rhs)
{
    if (this != &rhs)
    {
        this->base_type::operator=(rhs);
        copy(rhs);
    }
    return *this;
}
void Node::copy(Node const& rhs)
{
    m_name = rhs.m_name;
    m_typeName = rhs.m_typeName;
    m_id = rhs.m_id;
    m_libCellId = rhs.m_libCellId;
    m_type = rhs.m_type;
    m_cType = rhs.m_cType;
    m_x = rhs.m_x;
    m_y = rhs.m_y;
    m_z = rhs.m_z;
    m_fixed = rhs.m_fixed;
    m_vPinId = rhs.m_vPinId;
}

DREAMPLACE_END_NAMESPACE

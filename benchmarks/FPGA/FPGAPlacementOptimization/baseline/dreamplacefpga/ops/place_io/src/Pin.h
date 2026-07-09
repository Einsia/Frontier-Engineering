/*************************************************************************
    > File Name: Pin.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_PIN_H
#define DREAMPLACE_PIN_H

#include <string>
#include "Object.h"

DREAMPLACE_BEGIN_NAMESPACE

class Pin : public Object
{
    public:
        typedef Object base_type;
        typedef base_type::coordinate_type coordinate_type;
        typedef coordinate_traits<coordinate_type>::index_type index_type;

        /// default constructor 
        Pin();
        explicit Pin(const std::string &name) : m_name(name) {}
        /// copy constructor
        Pin(Pin const& rhs);
        /// assignment
        Pin& operator=(Pin const& rhs);

    // Getters
    const std::string &                 name() const                                 { return m_name; }
    index_type                          id() const                                   { return m_id; }
    index_type                          nodeId() const                               { return m_nodeId; }
    index_type                          netId() const                                { return m_netId; }

    // Setters
    void                                setId(index_type id)                         { m_id = id; }
    void                                setNodeId(index_type nodeId)                 { m_nodeId = nodeId; }
    void                                setNetId(index_type netId)                   { m_netId = netId; }

    protected:
        void copy(Pin const& rhs);

        std::string m_name; ///< index to the macro pin list of corresponding macro 
        index_type m_id; ///< index to the macro pin list of corresponding macro 
        index_type m_nodeId; ///< corresponding node  
        index_type m_netId; ///< corresponding net 
};

inline Pin::Pin() 
    : Pin::base_type()
    , m_name("")
    , m_id(std::numeric_limits<Pin::index_type>::max())
    , m_nodeId(std::numeric_limits<Pin::index_type>::max())
    , m_netId(std::numeric_limits<Pin::index_type>::max())
{
}
inline Pin::Pin(Pin const& rhs)
    : Pin::base_type(rhs)
{
    copy(rhs);
}
inline Pin& Pin::operator=(Pin const& rhs)
{
    if (this != &rhs)
    {
        this->base_type::operator=(rhs);
        copy(rhs);
    }
    return *this;
}
inline void Pin::copy(Pin const& rhs)
{
    m_name = rhs.m_name;
    m_id = rhs.m_id;
    m_nodeId = rhs.m_nodeId; 
    m_netId = rhs.m_netId; 
}


DREAMPLACE_END_NAMESPACE

#endif

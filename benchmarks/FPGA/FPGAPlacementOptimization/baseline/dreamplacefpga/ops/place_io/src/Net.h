/*************************************************************************
    > File Name: Net.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_NET_H
#define DREAMPLACE_NET_H

#include <vector>
#include "Pin.h"
#include "Box.h"

DREAMPLACE_BEGIN_NAMESPACE

class Net : public Object
{
    public:
        typedef Object base_type;
        typedef base_type::coordinate_type coordinate_type;
        typedef coordinate_traits<coordinate_type>::index_type index_type;
        typedef coordinate_traits<coordinate_type>::weight_type weight_type;

        /// default constructor 
        Net();
        explicit Net(const std::string &name) : m_name(name) {}
        /// copy constructor
        Net(Net const& rhs);
        /// assignment
        Net& operator=(Net const& rhs);


    void                                addPin(index_type pinId)                     { m_vPinId.push_back(pinId); }

    // Getters
    const std::string &                 name() const                                 { return m_name; }
    index_type                           id() const                                  { return m_id; }
    weight_type                         weight() const                               { return m_weight; }

    const std::vector<index_type> &     pinIdArray() const                           { return m_vPinId; }
    std::vector<index_type> &           pinIdArray()                                 { return m_vPinId; }
    index_type                          pinId(index_type i) const                    { return m_vPinId.at(i); }
    index_type                          numPins() const                              { return m_vPinId.size(); }

    // Setters
    void                                setId(index_type id)                         { m_id = id; }
    void                                setWeight(weight_type w)                     { m_weight = w; }

    protected:
        void copy(Net const& rhs);

        std::string m_name;
        index_type m_id;
        weight_type m_weight; ///< weight of net 
        std::vector<index_type> m_vPinId; ///< index of pins, the first one is source  
};

DREAMPLACE_END_NAMESPACE

#endif

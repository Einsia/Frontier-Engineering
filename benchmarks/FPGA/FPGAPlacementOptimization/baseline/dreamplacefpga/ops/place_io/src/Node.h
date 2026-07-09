/*************************************************************************
    > File Name: Node.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_NODE_H
#define DREAMPLACE_NODE_H

#include <vector>
#include "Pin.h"
#include "Enums.h"

DREAMPLACE_BEGIN_NAMESPACE

/// class Node denotes an instantiation of a standard cell 
class Node : public Object
{
	public:
        typedef Object base_type;
        typedef base_type::coordinate_type coordinate_type;
        typedef coordinate_traits<coordinate_type>::index_type index_type;

        /// default constructor 
        Node();
        explicit Node(const std::string &name) : m_name(name) {}
        explicit Node(const std::string &name, const std::string &type) : m_name(name), m_typeName(type) {}
        /// copy constructor
        Node(Node const& rhs);
        /// assignment
        Node& operator=(Node const& rhs);

        InstBlkEnum::InstBlkType cellType() const {return (InstBlkEnum::InstBlkType)m_cType;}
        void setCellType(InstBlkEnum::InstBlkType s) {m_cType = s; m_type = (index_type)s;}
        void setCellType(InstBlk const& s) {m_cType = s; m_type = (index_type)s;}

    void                                addPin(index_type pinId)                     { m_vPinId.push_back(pinId); }

    // Getters
    const std::string &                 name() const                                 { return m_name; }
    index_type                          id() const                                   { return m_id; }
    index_type                          typeId() const                               { return m_type; }
    index_type                          macroId() const                              { return m_libCellId; }

    const std::string &                 typeName() const                             { return m_typeName; }
    float                               x() const                                    { return m_x; }
    float                               y() const                                    { return m_y; }
    index_type                          z() const                                    { return m_z; }
    bool                                fixed() const                                { return (m_type > 8) ? true : false; }
    const std::vector<index_type> &     pinIdArray() const                           { return m_vPinId; }
    std::vector<index_type> &           pinIdArray()                                 { return m_vPinId; }
    index_type                          pinId(index_type i) const                    { return m_vPinId.at(i); }
    index_type                          numPins() const                              { return m_vPinId.size(); }

    // Setters
    void                                setId(index_type id)                          { m_id = id; }
    void                                setLibCellId(index_type lId)                  { m_libCellId = lId; }
    void                                setX(float x)                                 { m_x = x; }
    void                                setY(float y)                                 { m_y = y; }
    void                                setZ(index_type z)                            { m_z = z; }
    void                                setFixed(bool b)                              { m_fixed = b; }

    bool                                isLUT6() const                                { return (m_type == 5) ? true : false; }
    bool                                isLUT() const                                 { return (m_type < 6) ? true : false; }
    bool                                isFF() const                                  { return (m_type == 6) ? true : false; }
    bool                                isDSP() const                                 { return (m_type == 7) ? true : false; }
    bool                                isRAM() const                                 { return (m_type == 8) ? true : false; }


    protected:
        void copy(Node const& rhs);

        std::string m_name;
        std::string m_typeName;
        index_type m_id, m_libCellId, m_type;
        char m_cType;
        float m_x, m_y;
        index_type m_z;
        bool m_fixed;
        std::vector<index_type> m_vPinId; ///< index of pins 

};

DREAMPLACE_END_NAMESPACE

#endif

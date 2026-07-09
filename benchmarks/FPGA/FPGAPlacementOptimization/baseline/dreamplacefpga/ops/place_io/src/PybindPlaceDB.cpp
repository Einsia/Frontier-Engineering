/**
 * @file   PybindPlaceDB.cpp
 * @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Mar 2021
 * @brief  Python binding for PlaceDB 
 */

#include "PyPlaceDB.h"

PYBIND11_MAKE_OPAQUE(std::vector<bool>);
PYBIND11_MAKE_OPAQUE(std::vector<double>);
PYBIND11_MAKE_OPAQUE(std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type>);
PYBIND11_MAKE_OPAQUE(std::vector<std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> >);
//PYBIND11_MAKE_OPAQUE(std::vector<long>);
//PYBIND11_MAKE_OPAQUE(std::vector<unsigned long>);
//PYBIND11_MAKE_OPAQUE(std::vector<float>);
//PYBIND11_MAKE_OPAQUE(std::vector<double>);
PYBIND11_MAKE_OPAQUE(std::vector<std::string>);
//PYBIND11_MAKE_OPAQUE(std::vector<std::pair<int, int>>);

PYBIND11_MAKE_OPAQUE(DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type);

PYBIND11_MAKE_OPAQUE(std::vector<DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>>);
PYBIND11_MAKE_OPAQUE(std::vector<DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>>);
//PYBIND11_MAKE_OPAQUE(std::vector<DREAMPLACE_NAMESPACE::Pin>);
//PYBIND11_MAKE_OPAQUE(std::vector<DREAMPLACE_NAMESPACE::Node>);
//PYBIND11_MAKE_OPAQUE(std::vector<DREAMPLACE_NAMESPACE::Net>);
PYBIND11_MAKE_OPAQUE(std::vector<DREAMPLACE_NAMESPACE::LibCell>);
//PYBIND11_MAKE_OPAQUE(std::vector<DREAMPLACE_NAMESPACE::clk_region>);

void bind_PlaceDB(pybind11::module& m) 
{
    pybind11::bind_vector<std::vector<bool> >(m, "VectorBool");
    pybind11::bind_vector<std::vector<double> >(m, "VectorCoordinate", pybind11::buffer_protocol());
    pybind11::bind_vector<std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> >(m, "VectorIndex", pybind11::buffer_protocol());
    //pybind11::bind_vector<std::vector<std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> > >(m, "2DVectorIndex", pybind11::buffer_protocol());
    //pybind11::bind_vector<std::vector<long> >(m, "VectorLong", pybind11::buffer_protocol());
    //pybind11::bind_vector<std::vector<unsigned long> >(m, "VectorULong", pybind11::buffer_protocol());
    //pybind11::bind_vector<std::vector<float> >(m, "VectorFloat", pybind11::buffer_protocol());
    //pybind11::bind_vector<std::vector<double> >(m, "VectorDouble", pybind11::buffer_protocol());
    pybind11::bind_vector<std::vector<std::string> >(m, "VectorString");

    pybind11::bind_map<DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type>(m, "MapString2Index");

    // DREAMPLACE_NAMESPACE::Object.h
    pybind11::class_<DREAMPLACE_NAMESPACE::Object> (m, "Object")
        .def(pybind11::init<>())
        .def("id", &DREAMPLACE_NAMESPACE::Object::id)
        .def("__str__", &DREAMPLACE_NAMESPACE::Object::toString)
        ;

    // Box.h
    pybind11::class_<DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>> (m, "BoxCoordinate")
        .def(pybind11::init<>())
        .def(pybind11::init<DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::coordinate_type, DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::coordinate_type, DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::coordinate_type, DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::coordinate_type>())
        .def("xl", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::xl)
        .def("yl", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::yl)
        .def("xh", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::xh)
        .def("yh", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::yh)
        .def("width", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::width)
        .def("height", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::height)
        .def("area", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::area)
        .def("__str__", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>::toString)
        ;
    pybind11::class_<DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>> (m, "BoxIndex")
        .def(pybind11::init<>())
        .def(pybind11::init<DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::coordinate_type, DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::coordinate_type, DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::coordinate_type, DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::coordinate_type>())
        .def("xl", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::xl)
        .def("yl", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::yl)
        .def("xh", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::xh)
        .def("yh", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::yh)
        .def("width", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::width)
        .def("height", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::height)
        .def("area", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::area)
        .def("__str__", &DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>::toString)
        ;
    pybind11::bind_vector<std::vector<DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::coordinate_type>> >(m, "VectorBoxCoordinate");
    pybind11::bind_vector<std::vector<DREAMPLACE_NAMESPACE::Box<DREAMPLACE_NAMESPACE::Object::index_type>> >(m, "VectorBoxIndex");

    // DREAMPLACE_NAMESPACE::LibCell.h
    pybind11::class_<DREAMPLACE_NAMESPACE::LibCell, DREAMPLACE_NAMESPACE::Object> (m, "LibCell")
        .def(pybind11::init<>())
        .def("name", &DREAMPLACE_NAMESPACE::LibCell::name)
        .def("id", &DREAMPLACE_NAMESPACE::LibCell::id)
        .def("inputPinArray", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::LibCell::*)() const) &DREAMPLACE_NAMESPACE::LibCell::inputPinArray)
        .def("outputPinArray", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::LibCell::*)() const) &DREAMPLACE_NAMESPACE::LibCell::outputPinArray)
        .def("clkPinArray", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::LibCell::*)() const) &DREAMPLACE_NAMESPACE::LibCell::clkPinArray)
        .def("ctrlPinArray", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::LibCell::*)() const) &DREAMPLACE_NAMESPACE::LibCell::ctrlPinArray)
        .def("libCellPinName2Type", (DREAMPLACE_NAMESPACE::LibCell::string2index_map_type const& (DREAMPLACE_NAMESPACE::LibCell::*)() const) &DREAMPLACE_NAMESPACE::LibCell::libCellPinName2Type)
        ;
    pybind11::bind_vector<std::vector<DREAMPLACE_NAMESPACE::LibCell> >(m, "VectorLibCell");

    // DREAMPLACE_NAMESPACE::PlaceDB.h
    pybind11::class_<DREAMPLACE_NAMESPACE::PlaceDB> (m, "PlaceDB")
        .def(pybind11::init<>())
        .def("nodeNames", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeNames)
        .def("nodeName", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeName)
        .def("nodeTypes", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeTypes)
        .def("nodeType", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeType)
        .def("nodeXLocs", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeXLocs)
        .def("nodeX", (double const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeX)
        .def("nodeYLocs", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeYLocs)
        .def("nodeY", (double const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeY)
        .def("nodeZLocs", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeZLocs)
        .def("nodeZ", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeZ)
        .def("nodeXSizes", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeXSizes)
        .def("nodeXSize", (double const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeXSize)
        .def("nodeYSizes", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeYSizes)
        .def("nodeYSize", (double const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeYSize)
        .def("node2FenceRegionMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::node2FenceRegionMap)
        .def("nodeFenceRegion", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeFenceRegion)
        .def("node2OutPinId", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::node2OutPinId)
        .def("node2PinCount", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::node2PinCount)
        .def("node2PinCnt", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::node2PinCnt)
        .def("flopIndices", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flopIndices)
        .def("flopIndex", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::flopIndex)
        .def("lutIndices", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::lutIndices)
        .def("lutIndex", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::lutIndex)
        .def("lutTypes", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::lutTypes)
        .def("clusterlutTypes", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::clusterlutTypes)
        .def("node2OutPinCount", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::node2OutPinCount)
        .def("orgflatCCNodeMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgflatCCNodeMap)
        .def("orgflatCCNodeStartMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgflatCCNodeStartMap)
        .def("ccElementCount", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::ccElementCount)
        .def("node2CCIdMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::node2CCIdMap)
        .def("cc2nodeIdMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::cc2nodeIdMap)
        .def("isCCNode", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::isCCNode)
        //.def("flatCCInputPinsMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flatCCInputPinsMap)
        //.def("flatCCOutputPinsMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flatCCOutputPinsMap)
        //.def("flatCCInputPinStartMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flatCCInputPinStartMap)
        //.def("flatCCOutputPinStartMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flatCCOutputPinStartMap)
        //.def("overallCCInputPinStartMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::overallCCInputPinStartMap)
        //.def("overallCCOutputPinStartMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::overallCCOutputPinStartMap)
        .def("node2PinMap", (std::vector<std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> > const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::node2PinMap)
        .def("node2PinIdx", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type, DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::node2PinIdx)
        .def("netNames", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::netNames)
        .def("netName", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::netName)
        .def("net2PinCount", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::net2PinCount)
        .def("net2PinCnt", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::net2PinCnt)
        .def("net2PinMap", (std::vector<std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> > const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::net2PinMap)
        .def("net2PinIdx", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type, DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::net2PinIdx)
        .def("flatNet2PinMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flatNet2PinMap)
        .def("flatNet2PinStartMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flatNet2PinStartMap)
        .def("flatNode2PinMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flatNode2PinMap)
        .def("flatNode2PinStartMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::flatNode2PinStartMap)
        .def("pinNames", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::pinNames)
        .def("pinName", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::pinName)
        .def("pin2NetMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::pin2NetMap)
        .def("pin2NodeMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::pin2NodeMap)
        .def("pin2Node", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::pin2Node)
        .def("pin2NodeTypeMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::pin2NodeTypeMap)
        .def("pinTypes", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::pinTypes)
        .def("pinTypeIds", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::pinTypeIds)
        .def("pinOffsetX", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::pinOffsetX)
        .def("pinOffsetY", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::pinOffsetY)
        .def("orgNodeNames", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeNames)
        .def("orgNodeName", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeName)
        .def("orgNodeTypes", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeTypes)
        .def("orgNodeType", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeType)
        .def("orgNodeXSizes", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeXSizes)
        .def("orgNodeYSizes", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeYSizes)
        .def("orgFlatNode2PinMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgFlatNode2PinMap)
        .def("orgFlatNode2PinStartMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgFlatNode2PinStartMap)
        .def("orgPin2NodeMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgPin2NodeMap)
        .def("orgPin2NodeTypeMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgPin2NodeTypeMap)
        .def("orgNode2OutPinId", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNode2OutPinId)
        .def("orgNode2PinCount", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNode2PinCount)
        .def("orgFlopIndices", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgFlopIndices)
        .def("orgFlopIndex", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::orgFlopIndex)
        .def("orgLutTypes", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgLutTypes)
        .def("orgNode2OutPinCount", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNode2OutPinCount)
        .def("orgNode2FenceRegionMap", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNode2FenceRegionMap)
        .def("orgNodeCount", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeCount)
        .def("orgNode2CCIdMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNode2CCIdMap)
        .def("orgNodeMap", (int const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeMap)
        .def("isOrgCCNode", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::isOrgCCNode)
        .def("orgPinOffsetX", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgPinOffsetX)
        .def("orgPinOffsetY", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgPinOffsetY)
        .def("orgNodeName2Index", (DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeName2Index)
        .def("orgNodeXLocs", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeXLocs)
        .def("orgNodeYLocs", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeYLocs)
        .def("orgNodeZLocs", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::orgNodeZLocs)
        .def("new2OrgNodeMap", (std::vector<int> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::new2OrgNodeMap)
        .def("libCells", (std::vector<DREAMPLACE_NAMESPACE::LibCell> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::libCells)
        .def("libCell", (DREAMPLACE_NAMESPACE::LibCell const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::libCell)
        .def("siteRows", &DREAMPLACE_NAMESPACE::PlaceDB::siteRows)
        .def("siteCols", &DREAMPLACE_NAMESPACE::PlaceDB::siteCols)
        .def("siteVal", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type, DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::siteVal)
        .def("dieArea", &DREAMPLACE_NAMESPACE::PlaceDB::dieArea)
        .def("nodeName2Index", (DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::nodeName2Index)
        .def("libCellName2Index", (DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::libCellName2Index)
        .def("netName2Index", (DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::netName2Index)
        .def("site_types", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_types)
        .def("site_type", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::site_type)
        .def("site_resources_map", (std::vector<std::vector<std::string> > const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_resources_map)
        .def("site_resource", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type, DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::site_resource)
        .def("rsrc2site_map", (DREAMPLACE_NAMESPACE::PlaceDB::string2string_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc2site_map)
        .def("site_rsrc2count_map", (DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_rsrc2count_map)
        .def("rsrc_types", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_types)
        .def("rsrc_insts_map", (std::vector<std::vector<std::string> > const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_insts_map)
        .def("inst2rsrc_map", (DREAMPLACE_NAMESPACE::PlaceDB::string2string_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::inst2rsrc_map)
        .def("site_per_column", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_per_column)
        .def("site_widths", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_widths)
        .def("site_width", (double const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::site_width)
        .def("site_heights", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_heights)
        .def("site_height", (double const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::site_height)
        .def("rsrc_inst_types", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_inst_types)
        .def("rsrc_inst_type", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_inst_type)
        .def("site_out_coordinates", (std::vector<std::string> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_out_coordinates)
        .def("site_out_coordinate", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::site_out_coordinate)
        .def("site_out_values", (std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_out_values)
        .def("site_out_value", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::site_out_value)
        .def("rsrc_inst_widths", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_inst_widths)
        .def("rsrc_inst_width", (double const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_inst_width)
        .def("rsrc_inst_heights", (std::vector<double> const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_inst_heights)
        .def("rsrc_inst_height", (double const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_inst_height)
        .def("lut_fractures_map", (std::vector<std::vector<DREAMPLACE_NAMESPACE::PlaceDB::index_type> > const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::lut_fractures_map)
        .def("lut_fracture", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type, DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::lut_fracture)
        .def("site_type2index_map", (DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::site_type2index_map)
        .def("site_type2index", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(std::string) const) &DREAMPLACE_NAMESPACE::PlaceDB::site_type2index)
        .def("rsrc_type2index_map", (DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_type2index_map)
        .def("rsrc_type2index", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(std::string) const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_type2index)
        .def("rsrc_inst_type2index_map", (DREAMPLACE_NAMESPACE::PlaceDB::string2index_map_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::rsrc_inst_type2index_map)
        .def("slice_elements", (std::vector<std::pair<std::string, DREAMPLACE_NAMESPACE::PlaceDB::index_type> > const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::slice_elements)
        .def("slice_FF_ctrls", (std::vector<std::pair<std::string, DREAMPLACE_NAMESPACE::PlaceDB::index_type> > const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::slice_FF_ctrls)
        .def("slice_FF_ctrl_signal", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::slice_FF_ctrl_signal)
        .def("slice_FF_ctrl_count", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::slice_FF_ctrl_count)
        .def("sliceUnit_FF_ctrls", (std::vector<std::pair<std::string, DREAMPLACE_NAMESPACE::PlaceDB::index_type> > const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::sliceUnit_FF_ctrls)
        .def("sliceUnit_FF_ctrl_signal", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::sliceUnit_FF_ctrl_signal)
        .def("sliceUnit_FF_ctrl_count", (DREAMPLACE_NAMESPACE::PlaceDB::index_type const& (DREAMPLACE_NAMESPACE::PlaceDB::*)(DREAMPLACE_NAMESPACE::PlaceDB::index_type) const) &DREAMPLACE_NAMESPACE::PlaceDB::sliceUnit_FF_ctrl_count)
        .def("ff_ctrl_type", (std::string const& (DREAMPLACE_NAMESPACE::PlaceDB::*)() const) &DREAMPLACE_NAMESPACE::PlaceDB::ff_ctrl_type)
        .def("wl_weight_x", &DREAMPLACE_NAMESPACE::PlaceDB::wl_weight_x)
        .def("wl_weight_y", &DREAMPLACE_NAMESPACE::PlaceDB::wl_weight_y)
        .def("slice_ff_ctrl_mode", &DREAMPLACE_NAMESPACE::PlaceDB::slice_ff_ctrl_mode)
        .def("lut_shared_max_pins", &DREAMPLACE_NAMESPACE::PlaceDB::lut_shared_max_pins)
        .def("lut_type_in_sliceUnit", &DREAMPLACE_NAMESPACE::PlaceDB::lut_type_in_sliceUnit)
        .def("pin_route_cap", &DREAMPLACE_NAMESPACE::PlaceDB::pin_route_cap)
        .def("route_cap_h", &DREAMPLACE_NAMESPACE::PlaceDB::route_cap_h)
        .def("route_cap_v", &DREAMPLACE_NAMESPACE::PlaceDB::route_cap_v)
        .def("numMovable", &DREAMPLACE_NAMESPACE::PlaceDB::numMovable)
        .def("numOrgMovable", &DREAMPLACE_NAMESPACE::PlaceDB::numOrgMovable)
        .def("numFixed", &DREAMPLACE_NAMESPACE::PlaceDB::numFixed)
        .def("numLibCell", &DREAMPLACE_NAMESPACE::PlaceDB::numLibCell)
        .def("numLUT", &DREAMPLACE_NAMESPACE::PlaceDB::numLUT)
        .def("numFF", &DREAMPLACE_NAMESPACE::PlaceDB::numFF)
        .def("numCCNodes", &DREAMPLACE_NAMESPACE::PlaceDB::numCCNodes)
        .def("numNets", &DREAMPLACE_NAMESPACE::PlaceDB::numNets)
        .def("numPins", &DREAMPLACE_NAMESPACE::PlaceDB::numPins)
        .def("designName", &DREAMPLACE_NAMESPACE::PlaceDB::designName)
        .def("xl", &DREAMPLACE_NAMESPACE::PlaceDB::xl)
        .def("yl", &DREAMPLACE_NAMESPACE::PlaceDB::yl)
        .def("xh", &DREAMPLACE_NAMESPACE::PlaceDB::xh)
        .def("yh", &DREAMPLACE_NAMESPACE::PlaceDB::yh)
        .def("width", &DREAMPLACE_NAMESPACE::PlaceDB::width)
        .def("height", &DREAMPLACE_NAMESPACE::PlaceDB::height)
        ;
}


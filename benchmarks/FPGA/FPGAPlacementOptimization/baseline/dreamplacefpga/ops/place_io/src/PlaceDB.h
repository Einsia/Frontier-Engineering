/*************************************************************************
    > File Name: PlaceDB.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_PLACEDB_H
#define DREAMPLACE_PLACEDB_H

#include <limbo/parsers/bookshelf/bison/BookshelfDriver.h> // bookshelf parser 
#include <limbo/string/String.h>

#include "Node.h"
#include "Net.h"
#include "Pin.h"
#include "LibCell.h"
#include "Params.h"

DREAMPLACE_BEGIN_NAMESPACE

class PlaceDB;

//Introduce new struct for clk region information
struct clk_region
{
    int xl;
    int yl;
    int xm;
    int ym;
    int xh;
    int yh;
};

class PlaceDB : public BookshelfParser::BookshelfDataBase
{
    public:
        typedef Object::coordinate_type coordinate_type;
        typedef coordinate_traits<coordinate_type>::manhattan_distance_type manhattan_distance_type;
        typedef coordinate_traits<coordinate_type>::index_type index_type;
        typedef coordinate_traits<coordinate_type>::area_type area_type;
        typedef hashspace::unordered_map<std::string, index_type> string2index_map_type;
        typedef hashspace::unordered_map<std::string, std::string> string2string_map_type;
        typedef Box<coordinate_type> diearea_type;

        /// default constructor
        PlaceDB(); 

        /// destructor
        virtual ~PlaceDB() {}

        /// member functions 
        /// data access

        std::vector<std::string> const& nodeNames() const {return node_names;}
        std::vector<std::string>& nodeNames() {return node_names;}
        std::string const& nodeName(index_type id) const {return node_names.at(id);}
        std::string& nodeName(index_type id) {return node_names.at(id);}

        std::vector<std::string> const& nodeTypes() const {return node_types;}
        std::vector<std::string>& nodeTypes() {return node_types;}
        std::string const& nodeType(index_type id) const {return node_types.at(id);}
        std::string& nodeType(index_type id) {return node_types.at(id);}

        std::vector<double> const& nodeXLocs() const {return node_x;}
        std::vector<double>& nodeXLocs() {return node_x;}
        double const& nodeX(index_type id) const {return node_x.at(id);}
        double& nodeX(index_type id) {return node_x.at(id);}

        std::vector<double> const& nodeYLocs() const {return node_y;}
        std::vector<double>& nodeYLocs() {return node_y;}
        double const& nodeY(index_type id) const {return node_y.at(id);}
        double& nodeY(index_type id) {return node_y.at(id);}

        std::vector<index_type> const& nodeZLocs() const {return node_z;}
        std::vector<index_type>& nodeZLocs() {return node_z;}
        index_type const& nodeZ(index_type id) const {return node_z.at(id);}
        index_type& nodeZ(index_type id) {return node_z.at(id);}

        std::vector<double> const& nodeXSizes() const {return node_size_x;}
        std::vector<double>& nodeXSizes() {return node_size_x;}
        double const& nodeXSize(index_type id) const {return node_size_x.at(id);}
        double& nodeXSize(index_type id) {return node_size_x.at(id);}

        std::vector<double> const& nodeYSizes() const {return node_size_y;}
        std::vector<double>& nodeYSizes() {return node_size_y;}
        double const& nodeYSize(index_type id) const {return node_size_y.at(id);}
        double& nodeYSize(index_type id) {return node_size_y.at(id);}

        std::vector<index_type> const& node2FenceRegionMap() const {return node2fence_region_map;}
        std::vector<index_type>& node2FenceRegionMap() {return node2fence_region_map;}
        index_type const& nodeFenceRegion(index_type id) const {return node2fence_region_map.at(id);}
        index_type& nodeFenceRegion(index_type id) {return node2fence_region_map.at(id);}

        std::vector<index_type> const& node2OutPinId() const {return node2outpinIdx_map;}
        std::vector<index_type>& node2OutPinId() {return node2outpinIdx_map;}

        std::vector<index_type> const& node2PinCount() const {return node2pincount_map;}
        std::vector<index_type>& node2PinCount() {return node2pincount_map;}
        index_type const& node2PinCnt(index_type id) const {return node2pincount_map.at(id);}
        index_type& node2PinCnt(index_type id) {return node2pincount_map.at(id);}

        std::vector<index_type> const& flopIndices() const {return flop_indices;}
        std::vector<index_type>& flopIndices() {return flop_indices;}
        index_type const& flopIndex(index_type id) const {return flop_indices.at(id);}
        index_type& flopIndex(index_type id) {return flop_indices.at(id);}

        std::vector<index_type> const& lutIndices() const {return lut_indices;}
        std::vector<index_type>& lutIndices() {return lut_indices;}
        index_type const& lutIndex(index_type id) const {return lut_indices.at(id);}
        index_type& lutIndex(index_type id) {return lut_indices.at(id);}

        std::vector<index_type> const& lutTypes() const {return lut_type;}
        std::vector<index_type>& lutTypes() {return lut_type;}

        std::vector<index_type> const& clusterlutTypes() const {return cluster_lut_type;}
        std::vector<index_type>& clusterlutTypes() {return cluster_lut_type;}

        std::vector<index_type> const& node2OutPinCount() const {return node2outpinCount;}
        std::vector<index_type>& node2OutPinCount() {return node2outpinCount;}

        std::vector<std::vector<index_type> > const& node2PinMap() const {return node2pin_map;}
        std::vector<std::vector<index_type> >& node2PinMap() {return node2pin_map;}
        index_type const& node2PinIdx(index_type xloc, index_type yloc) const {return node2pin_map.at(xloc).at(yloc);}
        index_type& node2PinIdx(index_type xloc, index_type yloc) {return node2pin_map.at(xloc).at(yloc);}

        std::vector<index_type> const& node_count() const {return nodeCount;}
        std::vector<index_type>& node_count() {return nodeCount;}

        //Nodes part of Carry chain
        std::vector<index_type> const& ccElementCount() const {return cc_element_count;}
        std::vector<index_type>& ccElementCount() {return cc_element_count;}

        std::vector<int> const& node2CCIdMap() const {return node2ccId_map;}
        std::vector<int>& node2CCIdMap() {return node2ccId_map;}

        std::vector<int> const& cc2nodeIdMap() const {return cc2nodeId_map;}
        std::vector<int>& cc2nodeIdMap() {return cc2nodeId_map;}

        std::vector<index_type> const& isCCNode() const {return is_cc_node;}
        std::vector<index_type>& isCCNode() {return is_cc_node;}

        //std::vector<int> const& flatCCInputPinsMap() const {return flat_cc_input_pins_map;}
        //std::vector<int>& flatCCInputPinsMap() {return flat_cc_input_pins_map;}

        //std::vector<int> const& flatCCOutputPinsMap() const {return flat_cc_output_pins_map;}
        //std::vector<int>& flatCCOutputPinsMap() {return flat_cc_output_pins_map;}

        //std::vector<int> const& flatCCInputPinStartMap() const {return flat_cc_input_pin_start_map;}
        //std::vector<int>& flatCCInputPinStartMap() {return flat_cc_input_pin_start_map;}

        //std::vector<int> const& flatCCOutputPinStartMap() const {return flat_cc_output_pin_start_map;}
        //std::vector<int>& flatCCOutputPinStartMap() {return flat_cc_output_pin_start_map;}

        //std::vector<int> const& overallCCInputPinStartMap() const {return overall_cc_input_pin_start_map;}
        //std::vector<int>& overallCCInputPinStartMap() {return overall_cc_input_pin_start_map;}

        //std::vector<int> const& overallCCOutputPinStartMap() const {return overall_cc_output_pin_start_map;}
        //std::vector<int>& overallCCOutputPinStartMap() {return overall_cc_output_pin_start_map;}

        std::vector<std::string> const& netNames() const {return net_names;}
        std::vector<std::string>& netNames() {return net_names;}
        std::string const& netName(index_type id) const {return net_names.at(id);}
        std::string& netName(index_type id) {return net_names.at(id);}

        std::size_t numNets() const {return net_names.size();}

        std::vector<index_type> const& net2PinCount() const {return net2pincount_map;}
        std::vector<index_type>& net2PinCount() {return net2pincount_map;}
        index_type const& net2PinCnt(index_type id) const {return net2pincount_map.at(id);}
        index_type& net2PinCnt(index_type id) {return net2pincount_map.at(id);}

        std::vector<std::vector<index_type> > const& net2PinMap() const {return net2pin_map;}
        std::vector<std::vector<index_type> >& net2PinMap() {return net2pin_map;}
        index_type const& net2PinIdx(index_type xloc, index_type yloc) const {return net2pin_map.at(xloc).at(yloc);}
        index_type& net2PinIdx(index_type xloc, index_type yloc) {return net2pin_map.at(xloc).at(yloc);}

        std::vector<index_type> const& flatNet2PinMap() const {return flat_net2pin_map;}
        std::vector<index_type>& flatNet2PinMap() {return flat_net2pin_map;}

        std::vector<index_type> const& flatNet2PinStartMap() const {return flat_net2pin_start_map;}
        std::vector<index_type>& flatNet2PinStartMap() {return flat_net2pin_start_map;}

        std::vector<index_type> const& flatNode2PinStartMap() const {return flat_node2pin_start_map;}
        std::vector<index_type>& flatNode2PinStartMap() {return flat_node2pin_start_map;}

        std::vector<index_type> const& flatNode2PinMap() const {return flat_node2pin_map;}
        std::vector<index_type>& flatNode2PinMap() {return flat_node2pin_map;}

        std::vector<std::string> const& pinNames() const {return pin_names;}
        std::vector<std::string>& pinNames() {return pin_names;}
        std::string const& pinName(index_type id) const {return pin_names.at(id);}
        std::string& pinName(index_type id) {return pin_names.at(id);}

        std::size_t numPins() const {return pin_names.size();}

        std::vector<index_type> const& pin2NetMap() const {return pin2net_map;}
        std::vector<index_type>& pin2NetMap() {return pin2net_map;}

        std::vector<index_type> const& pin2NodeMap() const {return pin2node_map;}
        std::vector<index_type>& pin2NodeMap() {return pin2node_map;}
        index_type const& pin2Node(index_type id) const {return pin2node_map.at(id);}
        index_type& pin2Node(index_type id) {return pin2node_map.at(id);}

        std::vector<index_type> const& pin2NodeTypeMap() const {return pin2nodeType_map;}
        std::vector<index_type>& pin2NodeTypeMap() {return pin2nodeType_map;}

        std::vector<std::string> const& pinTypes() const {return pin_types;}
        std::vector<std::string>& pinTypes() {return pin_types;}

        std::vector<index_type> const& pinTypeIds() const {return pin_typeIds;}
        std::vector<index_type>& pinTypeIds() {return pin_typeIds;}

        std::vector<double> const& pinOffsetX() const {return pin_offset_x;}
        std::vector<double>& pinOffsetX() {return pin_offset_x;}

        std::vector<double> const& pinOffsetY() const {return pin_offset_y;}
        std::vector<double>& pinOffsetY() {return pin_offset_y;}

        std::vector<LibCell> const& libCells() const {return m_vLibCell;}
        std::vector<LibCell>& libCells() {return m_vLibCell;}
        LibCell const& libCell(index_type id) const {return m_vLibCell.at(id);}
        LibCell& libCell(index_type id) {return m_vLibCell.at(id);}

        std::size_t numLibCells() const {return m_vLibCell.size();}

        std::size_t siteRows() const {return m_siteDB.size();}
        std::size_t siteCols() const {return m_siteDB[0].size();}
        index_type const& siteVal(index_type xloc, index_type yloc) const {return m_siteDB.at(xloc).at(yloc);}
        index_type& siteVal(index_type xloc, index_type yloc) {return m_siteDB.at(xloc).at(yloc);}

        /// be careful to use die area because it is larger than the actual rowBbox() which is the placement area 
        /// it is safer to use rowBbox()
        diearea_type const& dieArea() const {return m_dieArea;}

        string2index_map_type const& libCellName2Index() const {return m_LibCellName2Index;}
        string2index_map_type& libCellName2Index() {return m_LibCellName2Index;}

        string2index_map_type const& nodeName2Index() const {return node_name2id_map;}
        string2index_map_type& nodeName2Index() {return node_name2id_map;}

        string2index_map_type const& netName2Index() const {return net_name2id_map;}
        string2index_map_type& netName2Index() {return net_name2id_map;}

        std::size_t numMovable() const {return node_names.size()-fixed_node_names.size();}
        std::size_t numFixed() const {return fixed_node_names.size();}

        std::vector<int> const& orgNode2CCIdMap() const {return org_node2ccId_map;}
        std::vector<int>& orgNode2CCIdMap() {return org_node2ccId_map;}

        std::vector<index_type> const& isOrgCCNode() const {return org_is_cc_node;}
        std::vector<index_type>& isOrgCCNode() {return org_is_cc_node;}

        std::vector<int> const& new2OrgNodeMap() const {return new2org_node_map;}
        std::vector<int>& new2OrgNodeMap() {return new2org_node_map;}
        int const& orgNodeMap(index_type id) const {return new2org_node_map.at(id);}
        int& orgNodeMap(index_type id) {return new2org_node_map.at(id);}

        std::size_t numOrgMovable() const {return org_node_names.size()-fixed_node_names.size();}

        string2index_map_type const& orgNodeName2Index() const {return org_node_name2id_map;}
        string2index_map_type& orgNodeName2Index() {return org_node_name2id_map;}

        std::vector<std::string> const& orgNodeNames() const {return org_node_names;}
        std::vector<std::string>& orgNodeNames() {return org_node_names;}
        std::string const& orgNodeName(index_type id) const {return org_node_names.at(id);}
        std::string& orgNodeName(index_type id) {return org_node_names.at(id);}

        std::vector<std::string> const& orgNodeTypes() const {return org_node_types;}
        std::vector<std::string>& orgNodeTypes() {return org_node_types;}
        std::string const& orgNodeType(index_type id) const {return org_node_types.at(id);}
        std::string& orgNodeType(index_type id) {return org_node_types.at(id);}

        std::vector<double> const& orgNodeXSizes() const {return org_node_size_x;}
        std::vector<double>& orgNodeXSizes() {return org_node_size_x;}

        std::vector<double> const& orgNodeYSizes() const {return org_node_size_y;}
        std::vector<double>& orgNodeYSizes() {return org_node_size_y;}

        std::vector<index_type> const& orgNode2FenceRegionMap() const {return org_node2fence_region_map;}
        std::vector<index_type>& orgNode2FenceRegionMap() {return org_node2fence_region_map;}

        std::vector<index_type> const& orgNodeCount() const {return org_nodeCount;}
        std::vector<index_type>& orgNodeCount() {return org_nodeCount;}

        std::vector<index_type> const& orgFlopIndices() const {return org_flop_indices;}
        std::vector<index_type>& orgFlopIndices() {return org_flop_indices;}
        index_type const& orgFlopIndex(index_type id) const {return org_flop_indices.at(id);}
        index_type& orgFlopIndex(index_type id) {return org_flop_indices.at(id);}

        std::vector<index_type> const& orgLutTypes() const {return org_lut_type;}
        std::vector<index_type>& orgLutTypes() {return org_lut_type;}

        std::vector<double> const& orgPinOffsetX() const {return org_pin_offset_x;}
        std::vector<double>& orgPinOffsetX() {return org_pin_offset_x;}

        std::vector<double> const& orgPinOffsetY() const {return org_pin_offset_y;}
        std::vector<double>& orgPinOffsetY() {return org_pin_offset_y;}

        std::vector<index_type> const& orgPin2NodeTypeMap() const {return org_pin2nodeType_map;}
        std::vector<index_type>& orgPin2NodeTypeMap() {return org_pin2nodeType_map;}

        std::vector<index_type> const& orgNode2PinCount() const {return org_node2pincount_map;}
        std::vector<index_type>& orgNode2PinCount() {return org_node2pincount_map;}

        std::vector<index_type> const& orgPin2NodeMap() const {return org_pin2node_map;}
        std::vector<index_type>& orgPin2NodeMap() {return org_pin2node_map;}

        std::vector<index_type> const& orgNode2OutPinCount() const {return org_node2outpinCount;}
        std::vector<index_type>& orgNode2OutPinCount() {return org_node2outpinCount;}

        std::vector<index_type> const& orgNode2OutPinId() const {return org_node2outpinIdx_map;}
        std::vector<index_type>& orgNode2OutPinId() {return org_node2outpinIdx_map;}

        std::vector<index_type> const& orgFlatNode2PinMap() const {return org_flat_node2pin_map;}
        std::vector<index_type>& orgFlatNode2PinMap() {return org_flat_node2pin_map;}

        std::vector<index_type> const& orgFlatNode2PinStartMap() const {return org_flat_node2pin_start_map;}
        std::vector<index_type>& orgFlatNode2PinStartMap() {return org_flat_node2pin_start_map;}

        std::vector<double> const& orgNodeXLocs() const {return org_node_x;}
        std::vector<double>& orgNodeXLocs() {return org_node_x;}

        std::vector<double> const& orgNodeYLocs() const {return org_node_y;}
        std::vector<double>& orgNodeYLocs() {return org_node_y;}

        std::vector<index_type> const& orgNodeZLocs() const {return org_node_z;}
        std::vector<index_type>& orgNodeZLocs() {return org_node_z;}

        std::vector<index_type> const& orgflatCCNodeMap() const {return org_flat_cc2node_map;}
        std::vector<index_type>& orgflatCCNodeMap() {return org_flat_cc2node_map;}

        std::vector<index_type> const& orgflatCCNodeStartMap() const {return org_flat_cc2node_start_map;}
        std::vector<index_type>& orgflatCCNodeStartMap() {return org_flat_cc2node_start_map;}

        //Site & Resources 
        std::vector<std::string> const& site_types() const {return siteTypes;}
        std::vector<std::string>& site_types() {return siteTypes;}
        std::string const& site_type(index_type id) const {return siteTypes.at(id);}
        std::string& site_type(index_type id) {return siteTypes.at(id);}

        std::vector<std::vector<std::string> > const& site_resources_map() const {return siteResources;}
        std::vector<std::vector<std::string> >& site_resources_map() {return siteResources;}
        std::string const& site_resource(index_type xloc, index_type yloc) const {return siteResources.at(xloc).at(yloc);}
        std::string& site_resource(index_type xloc, index_type yloc) {return siteResources.at(xloc).at(yloc);}

        string2string_map_type const& rsrc2site_map() const {return rsrc2SiteMap;}
        string2string_map_type& rsrc2site_map() {return rsrc2SiteMap;}
        std::string const& rsrc_type2site(std::string rsrcType) const {return rsrc2SiteMap.at(rsrcType);}
        std::string& rsrc_type2site(std::string rsrcType) {return rsrc2SiteMap.at(rsrcType);}

        string2index_map_type const& site_rsrc2count_map() const {return siteRsrcCountMap;}
        string2index_map_type& site_rsrc2count_map() {return siteRsrcCountMap;}

        std::vector<std::string> const& rsrc_types() const {return rsrcTypes;}
        std::vector<std::string>& rsrc_types() {return rsrcTypes;}
        std::string const& rsrc_type(index_type id) const {return rsrcTypes.at(id);}
        std::string& rsrc_type(index_type id) {return rsrcTypes.at(id);}

        std::vector<std::vector<std::string> > const& rsrc_insts_map() const {return rsrcInsts;}
        std::vector<std::vector<std::string> >& rsrc_insts_map() {return rsrcInsts;}

        string2string_map_type const& inst2rsrc_map() const {return inst2RsrcMap;}
        string2string_map_type& inst2rsrc_map() {return inst2RsrcMap;}

        index_type const& site_per_column() const {return sitePerColumn;}
        index_type& site_per_column() {return sitePerColumn;}

        std::vector<double> const& site_widths() const {return siteWidth;}
        std::vector<double>& site_widths() {return siteWidth;}
        double const& site_width(index_type id) const {return siteWidth.at(id);}
        double& site_width(index_type id) {return siteWidth.at(id);}

        std::vector<double> const& site_heights() const {return siteHeight;}
        std::vector<double>& site_heights() {return siteHeight;}
        double const& site_height(index_type id) const {return siteHeight.at(id);}
        double& site_height(index_type id) {return siteHeight.at(id);}

        std::vector<std::string> const& rsrc_inst_types() const {return rsrcInstTypes;}
        std::vector<std::string>& rsrc_inst_types() {return rsrcInstTypes;}
        std::string const& rsrc_inst_type(index_type id) const {return rsrcInstTypes.at(id);}
        std::string& rsrc_inst_type(index_type id) {return rsrcInstTypes.at(id);}

        std::vector<std::string> const& site_out_coordinates() const {return siteOutCoordinate;}
        std::vector<std::string>& site_out_coordinates() {return siteOutCoordinate;}
        std::string const& site_out_coordinate(index_type id) const {return siteOutCoordinate.at(id);}
        std::string& site_out_coordinate(index_type id) {return siteOutCoordinate.at(id);}

        std::vector<index_type> const& site_out_values() const {return siteOutValue;}
        std::vector<index_type>& site_out_values() {return siteOutValue;}
        index_type const& site_out_value(index_type id) const {return siteOutValue.at(id);}
        index_type& site_out_value(index_type id) {return siteOutValue.at(id);}

        std::vector<double> const& rsrc_inst_widths() const {return rsrcInstWidth;}
        std::vector<double>& rsrc_inst_widths() {return rsrcInstWidth;}
        double const& rsrc_inst_width(index_type id) const {return rsrcInstWidth.at(id);}
        double& rsrc_inst_width(index_type id) {return rsrcInstWidth.at(id);}

        std::vector<double> const& rsrc_inst_heights() const {return rsrcInstHeight;}
        std::vector<double>& rsrc_inst_heights() {return rsrcInstHeight;}
        double const& rsrc_inst_height(index_type id) const {return rsrcInstHeight.at(id);}
        double& rsrc_inst_height(index_type id) {return rsrcInstHeight.at(id);}

        std::vector<std::vector<index_type> > const& lut_fractures_map() const {return lutFractures;}
        std::vector<std::vector<index_type> >& lut_fractures_map() {return lutFractures;}
        index_type const& lut_fracture(index_type xloc, index_type yloc) const {return lutFractures.at(xloc).at(yloc);}
        index_type& lut_fracture(index_type xloc, index_type yloc) {return lutFractures.at(xloc).at(yloc);}

        string2index_map_type const& site_type2index_map() const {return siteType2IndexMap;}
        string2index_map_type& site_type2index_map() {return siteType2IndexMap;}
        index_type const& site_type2index(std::string siteType) const {return siteType2IndexMap.at(siteType);}
        index_type& site_type2index(std::string siteType) {return siteType2IndexMap.at(siteType);}

        string2index_map_type const& rsrc_type2index_map() const {return rsrcType2IndexMap;}
        string2index_map_type& rsrc_type2index_map() {return rsrcType2IndexMap;}
        index_type const& rsrc_type2index(std::string rsrcType) const {return rsrcType2IndexMap.at(rsrcType);}
        index_type& rsrc_type2index(std::string rsrcType) {return rsrcType2IndexMap.at(rsrcType);}

        string2index_map_type const& rsrc_inst_type2index_map() const {return rsrcInstType2IndexMap;}
        string2index_map_type& rsrc_inst_type2index_map() {return rsrcInstType2IndexMap;}

        std::vector<std::pair<std::string, index_type> > const& slice_elements() const {return sliceElements;}
        std::vector<std::pair<std::string, index_type> >& slice_elements() {return sliceElements;}

        std::vector<std::pair<std::string, index_type> > const& slice_FF_ctrls() const {return sliceFFCtrl;}
        std::vector<std::pair<std::string, index_type> >& slice_FF_ctrls() {return sliceFFCtrl;}
        std::string const& slice_FF_ctrl_signal(index_type idx) const {return sliceFFCtrl.at(idx).first;}
        std::string& slice_FF_ctrl_signal(index_type idx) {return sliceFFCtrl.at(idx).first;}
        index_type const& slice_FF_ctrl_count(index_type idx) const {return sliceFFCtrl.at(idx).second;}
        index_type& slice_FF_ctrl_count(index_type idx) {return sliceFFCtrl.at(idx).second;}

        std::vector<std::pair<std::string, index_type> > const& sliceUnit_FF_ctrls() const {return sliceFFUnitCtrl;}
        std::vector<std::pair<std::string, index_type> >& sliceUnit_FF_ctrls() {return sliceFFUnitCtrl;}
        std::string const& sliceUnit_FF_ctrl_signal(index_type idx) const {return sliceFFUnitCtrl.at(idx).first;}
        std::string& sliceUnit_FF_ctrl_signal(index_type idx) {return sliceFFUnitCtrl.at(idx).first;}
        index_type const& sliceUnit_FF_ctrl_count(index_type idx) const {return sliceFFUnitCtrl.at(idx).second;}
        index_type& sliceUnit_FF_ctrl_count(index_type idx) {return sliceFFUnitCtrl.at(idx).second;}

        std::string const& ff_ctrl_type() const {return ffCtrlType;}
        std::string& ff_ctrl_type() {return ffCtrlType;}

        double wl_weight_x() const {return wlXWeight;}
        double wl_weight_y() const {return wlYWeight;}
        std::string slice_ff_ctrl_mode() const {return sliceFF_ctrl_mode;}
        index_type lut_shared_max_pins() const {return lutMaxShared;}
        index_type lut_type_in_sliceUnit() const {return lutTypeInSliceUnit;}
        index_type pin_route_cap() const {return pinRouteCap;}
        index_type route_cap_h() const {return routeCapH;}
        index_type route_cap_v() const {return routeCapV;}

        //std::size_t numMovable() const {return num_movable_nodes;}
        //std::size_t numFixed() const {return num_fixed_nodes;}
        std::size_t numLibCell() const {return m_numLibCell;}
        std::size_t numLUT() const {return m_numLUT;}
        std::size_t numFF() const {return m_numFF;}
        std::size_t numCCNodes() const {return m_numCCs;}
        std::string designName() const {return m_designName;}

        /// \return die area information of layout 
        double xl() const {return m_dieArea.xl();}
        double yl() const {return m_dieArea.yl();}
        double xh() const {return m_dieArea.xh();}
        double yh() const {return m_dieArea.yh();}
        manhattan_distance_type width() const {return m_dieArea.width();}
        manhattan_distance_type height() const {return m_dieArea.height();}

        ///==== Bookshelf Callbacks ====
        virtual void add_bookshelf_node(std::string& name, std::string& type); //Updated for FPGA
        virtual void add_bookshelf_net(BookshelfParser::Net const& n);
        virtual void add_bookshelf_carry(BookshelfParser::CarryChain const& carry_chain);
        virtual void set_bookshelf_node_pos(std::string const& name, double x, double y, int z);
        virtual void resize_sites(int xSize, int ySize);
        virtual void site_info_update(int x, int y, std::string const& name);
        virtual void resize_clk_regions(int xReg, int yReg);
        virtual void add_clk_region(std::string const& name, int xl, int yl, int xh, int yh, int xm, int ym);
        virtual void add_lib_cell(std::string const& name);
        virtual void add_input_pin(std::string& pName);
        virtual void add_input_add_pin(std::string& pName);
        virtual void add_output_pin(std::string& pName);
        virtual void add_output_add_pin(std::string& pName);
        virtual void add_clk_pin(std::string& pName);
        virtual void add_ctrl_pin(std::string& pName);
        virtual void add_site(BookshelfParser::Site const& st);
        virtual void add_rsrc(BookshelfParser::Rsrc const& rsrc);
        virtual void set_site_per_column(int val);
        virtual void set_site_dimensions(std::string const& sName, double w, double h);
        virtual void set_slice_element(std::string const& sName, int cnt);
        virtual void set_cell_dimensions(std::string const& cName, double w, double h);
        virtual void set_lut_max_shared(int cnt);
        virtual void set_lut_type_in_sliceUnit(int cnt);
        virtual void set_lut_fractureability(BookshelfParser::LUTFract const& lutFract);
        virtual void set_sliceFF_ctrl_mode(std::string const& mode);
        virtual void set_sliceFF_ctrl(std::string const& sName, int cnt);
        virtual void set_sliceUnitFF_ctrl(std::string const& sName, int cnt);
        virtual void set_FFCtrl_type(std::string const& type);
        virtual void set_wl_weight_x(double wt);
        virtual void set_wl_weight_y(double wt);
        virtual void set_pin_route_cap(int pinCap);
        virtual void set_route_cap_H(int hRouteCap);
        virtual void set_route_cap_V(int vRouteCap);
        virtual void set_siteOut(BookshelfParser::SiteOut const& st);
        virtual void set_bookshelf_design(std::string& name);
        virtual void update_nodes(); 
        virtual void bookshelf_end(); 

        /// write placement solutions 
        virtual bool write(std::string const& filename) const;
        virtual bool write(std::string const& filename, float const* x = NULL, float const* y = NULL, index_type const* z = NULL) const;

        std::vector<std::vector<index_type> > m_siteDB; //FPGA Site Information
        std::vector<clk_region> m_clkRegionDB; //FPGA clkRegion Information
        std::vector<std::string> m_clkRegions; //FPGA clkRegion Names 
        int m_clkRegX;
        int m_clkRegY;
        std::vector<LibCell> m_vLibCell; ///< library definition for cell types
        diearea_type m_dieArea; ///< die area, it can be larger than actual placement area 
        string2index_map_type m_LibCellName2Index; ///< map name of lib cell to index of m_vLibCell

        //Temp storage for libcell name considered
        std::string m_libCellTemp;

        //Ensure correct node and pin_offset sizes for LUT/FF
        index_type lutId = 100000;
        index_type ffId = 100000;
        index_type ioId = 100000;
        index_type pllId = 100000;

        //Site & Resources Info
        index_type sitePerColumn = 0;
        std::vector<std::vector<std::string> > siteResources;
        std::vector<std::string> siteTypes;
        string2index_map_type siteType2IndexMap;
        std::vector<double> siteWidth;
        std::vector<double> siteHeight;
        string2index_map_type siteRsrcCountMap;
        string2string_map_type rsrc2SiteMap;

        std::vector<std::string> rsrcInstTypes;
        string2index_map_type rsrcInstType2IndexMap;
        std::vector<std::string> rsrcTypes;
        string2index_map_type rsrcType2IndexMap;
        std::vector<std::vector<std::string> > rsrcInsts;
        std::vector<double> rsrcInstWidth;
        std::vector<double> rsrcInstHeight;
        string2string_map_type inst2RsrcMap;

        std::vector<std::vector<index_type> > lutFractures;
        std::vector<std::pair<std::string, index_type> > sliceElements;
        std::vector<std::pair<std::string, index_type> > sliceFFCtrl;
        std::vector<std::pair<std::string, index_type> > sliceFFUnitCtrl;

        std::vector<std::string> siteOutCoordinate;
        std::vector<index_type> siteOutValue;

        std::string ffCtrlType;
        double wlXWeight;
        double wlYWeight;
        index_type lutMaxShared;
        index_type lutTypeInSliceUnit;
        index_type pinRouteCap;
        index_type routeCapH;
        index_type routeCapV;
        std::string sliceFF_ctrl_mode;

        std::size_t num_movable_nodes; ///< number of movable cells 
        std::size_t num_fixed_nodes; ///< number of fixed cells 
        std::size_t m_numLibCell; ///< number of standard cells in the library
        std::size_t m_numLUT; ///< number of LUTs in design
        std::size_t m_numFF; ///< number of FFs in design
        std::size_t m_numCCs; ///< number of carry chains in design

        std::string m_designName; ///< for writing def file

        //temp flag
        bool initSiteMapValUpd;
        //Flattened  
        std::vector<std::string> node_names; 
        std::vector<std::string> node_types; 
        std::vector<double> node_size_x;
        std::vector<double> node_size_y;
        std::vector<double> fixed_node_size_x;
        std::vector<double> fixed_node_size_y;
        std::vector<double> node_x;
        std::vector<double> node_y;
        std::vector<index_type> node_z;
        std::vector<double> fixed_node_x;
        std::vector<double> fixed_node_y;
        std::vector<index_type> fixed_node_z;
        std::vector<index_type> nodeCount;

        //New approach to parsing
        std::vector<std::string> fixed_node_names;
        std::vector<std::string> fixed_node_types;
        std::vector<std::string> net_names;
        std::vector<std::string> pin_names;
        std::vector<std::string> pin_types;
        std::vector<index_type > node2fence_region_map;
        std::vector<index_type > fixed_node2fence_region_map;
        std::vector<std::vector<index_type> > node2pin_map;
        std::vector<index_type> node2pincount_map;
        std::vector<index_type> net2pincount_map;
        std::vector<index_type> node2outpinIdx_map;
        std::vector<index_type> node2outpinCount;
        std::vector<index_type> pin_typeIds;
        std::vector<index_type> pin2node_map;
        std::vector<index_type> pin2net_map;
        std::vector<index_type> pin2nodeType_map;
        std::vector<std::vector<index_type> > net2pin_map;
        std::vector<index_type> flat_net2pin_map;
        std::vector<index_type> flat_net2pin_start_map;
        std::vector<index_type> flat_node2pin_map;
        std::vector<index_type> flat_node2pin_start_map;
        std::vector<index_type> cc_element_count;
        std::vector<index_type> is_cc_node;
        std::vector<index_type> flop_indices;
        std::vector<index_type> lut_type;
        std::vector<index_type> cluster_lut_type;
        std::vector<index_type> fixed_lut_type;
        std::vector<index_type> fixed_cluster_lut_type;
        std::vector<int> node2ccId_map;
        std::vector<int> cc2nodeId_map;

        std::vector<double> pin_offset_x;
        std::vector<double> pin_offset_y;

        //string2index_map_type mov_node_name2id_map;
        string2index_map_type fixed_node_name2id_map;
        string2index_map_type node_name2id_map;
        string2index_map_type net_name2id_map;

        //Data structures for original info when carry chains exist
        string2index_map_type org_node_name2id_map;
        std::vector<std::string> org_node_names; 
        std::vector<std::string> org_node_types; 
        std::vector<double> org_node_size_x;
        std::vector<double> org_node_size_y;
        std::vector<index_type > org_node2fence_region_map;
        std::vector<index_type> org_nodeCount;
        std::vector<index_type> org_is_cc_node;
        std::vector<index_type> org_flop_indices;
        std::vector<index_type> org_lut_type;
        std::vector<int> org_node2ccId_map;
        std::vector<int> org_node2ccIndex_map;
        std::vector<index_type> org_flat_cc2node_map;
        std::vector<index_type> org_flat_cc2node_start_map;
        std::vector<int> new2org_node_map;

        std::vector<double> org_node_x;
        std::vector<double> org_node_y;
        std::vector<index_type> org_node_z;
        std::vector<double> org_pin_offset_x;
        std::vector<double> org_pin_offset_y;
        std::vector<index_type> org_pin2nodeType_map;
        std::vector<index_type> org_node2pincount_map;
        std::vector<index_type> org_pin2node_map;
        std::vector<std::vector<index_type> > org_node2pin_map;
        std::vector<index_type> org_node2outpinCount;
        std::vector<index_type> org_node2outpinIdx_map;
        std::vector<index_type> org_flat_node2pin_map;
        std::vector<index_type> org_flat_node2pin_start_map;
        //Temporary org data structures
        std::size_t org_num_movable_nodes; ///< number of movable cells 
        string2index_map_type org_fixed_node_name2id_map;
        std::vector<index_type> lut_indices;
        ////Get information of carry chain node input/output pins
        //std::vector<int> flat_cc_input_pins_map; 
        //std::vector<int> flat_cc_output_pins_map; 
        //std::vector<int> flat_cc_input_pin_start_map;
        //std::vector<int> flat_cc_output_pin_start_map;
        //std::vector<int> overall_cc_input_pin_start_map;
        //std::vector<int> overall_cc_output_pin_start_map;

        ////Temporary datastructure
        //std::vector<std::vector<std::pair<int, int> > > temp_input_pin_info;
        //std::vector<std::vector<std::pair<int, int> > > temp_output_pin_info;
};

DREAMPLACE_END_NAMESPACE

#endif


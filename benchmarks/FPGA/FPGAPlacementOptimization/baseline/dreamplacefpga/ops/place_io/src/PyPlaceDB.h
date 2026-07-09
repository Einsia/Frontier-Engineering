/**
 * @file   PyPlaceDB.h
 * @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Mar 2021
 * @brief  Placement database for python 
 */

#ifndef _DREAMPLACE_PLACE_IO_PYPLACEDB_H
#define _DREAMPLACE_PLACE_IO_PYPLACEDB_H

//#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>
#include <pybind11/numpy.h>
#include <sstream>
//#include <boost/timer/timer.hpp>
#include "PlaceDB.h"
#include "Iterators.h"
#include "Box.h"
#include "utility/src/torch.h"

DREAMPLACE_BEGIN_NAMESPACE

bool readBookshelf(PlaceDB& db, std::string const& auxPath);

/// database for python 
struct PyPlaceDB
{
    pybind11::list node_names; ///< 1D array, cell name 
    pybind11::list node_size_x; ///< 1D array, cell width  
    pybind11::list node_size_y; ///< 1D array, cell height
    pybind11::list node_types; ///< 1D array, nodeTypes(FPGA)
    pybind11::list flop_indices; ///< 1D array, nodeTypes(FPGA)
    //pybind11::list lut_indices; ///< 1D array, nodeTypes(FPGA)
    //pybind11::list flop_lut_indices; ///< 1D array, nodeTypes(FPGA)
    //pybind11::list dsp_indices; ///< 1D array, nodeTypes(FPGA)
    //pybind11::list ram_indices; ///< 1D array, nodeTypes(FPGA)
    //pybind11::list dsp_ram_indices; ///< 1D array, nodeTypes(FPGA)
    pybind11::list node2fence_region_map; ///< only record fence regions for each cell 

    pybind11::list node_x; ///< 1D array, cell position x 
    pybind11::list node_y; ///< 1D array, cell position y 
    pybind11::list node_z; ///< 1D array, cell position z  (FPGA)
    pybind11::list node2pin_map; ///< array of 1D array, contains pin id of each node 
    pybind11::list flat_node2pin_map; ///< flatten version of node2pin_map 
    pybind11::list flat_node2pin_start_map; ///< starting index of each node in flat_node2pin_map
    pybind11::list node2pincount_map; ///< array of 1D array, number of pins in node
    pybind11::list net2pincount_map; ///< array of 1D array, number of pins in net
    pybind11::list node2outpinIdx_map; ///< array of 1D array, output pin idx of each node
    pybind11::list node2outpinCount; ///< array of 1D array, output pin count of each node
    pybind11::list lut_type; ///< 1D array, nodeTypes(FPGA)
    pybind11::list cluster_lut_type; ///< 1D array, LUT types for clustering
    pybind11::dict node_name2id_map; ///< node name to id map, cell name 

    //pybind11::dict movable_node_name2id_map; ///< node name to id map, cell name 
    //pybind11::dict fixed_node_name2id_map; ///< node name to id map, cell name 
    //pybind11::list fixedNodes; ///< 1D array, nodeTypes(FPGA)
    unsigned int num_terminals; ///< number of terminals, essentially IOs
    unsigned int num_movable_nodes; ///< number of movable nodes
    unsigned int num_physical_nodes; ///< number of movable nodes + terminals (FPGA)
    pybind11::list node_count; ///< 1D array, count of resource types

    unsigned int num_ccNodes; ///< number of carry chain nodes in design (FPGA)
    pybind11::list cc_element_count; ///< No of elements in all the carry chains
    pybind11::list is_cc_node; ///< Specifies if node is part of carry chain
    pybind11::list node2ccId_map; ///< Node id to carry chain indexing
    pybind11::list cc2nodeId_map; ///< carry chain id to node indexing
    //pybind11::list flat_cc2node_map; ///< flat cc2node map
    //pybind11::list flat_cc2node_start_map; ///< flat cc2node start map
    //pybind11::list carry_chain_nets; ///< cc nets
    //unsigned int num_carry_chains; ///< number of carry chain nodes in design (FPGA)

    unsigned int org_num_movable_nodes; ///< number of movable nodes
    pybind11::dict org_node_name2id_map; ///< node name to id map, cell name 
    pybind11::list org_node_names; ///< 1D array, cell name 
    pybind11::list org_node_types; ///< 1D array, nodeTypes(FPGA)
    pybind11::list org_node_size_x; ///< 1D array, cell width  
    pybind11::list org_node_size_y; ///< 1D array, cell width  
    pybind11::list org_node2fence_region_map; ///< only record fence regions for each cell 
    pybind11::list org_node_count; ///< count based on node type
    pybind11::list org_flop_indices; ///< 1D array, nodeTypes(FPGA)
    pybind11::list org_lut_type; ///< 1D array, nodeTypes(FPGA)
    pybind11::list org_pin_offset_x; ///< 1D array, pin offset x to its node 
    pybind11::list org_pin_offset_y; ///< 1D array, pin offset y to its node 
    pybind11::list org_pin2nodeType_map; ///< 1D array, pin to node type
    pybind11::list org_node2pincount_map; ///< array of 1D array, number of pins in node
    pybind11::list org_pin2node_map; ///< 1D array, contain parent node id of each pin 
    pybind11::list org_node2outpinCount; ///< array of 1D array, output pin count of each node
    pybind11::list org_node2outpinIdx_map; ///< array of 1D array, output pin idx of each node
    pybind11::list org_flat_node2pin_map; ///< flatten version of node2pin_map 
    pybind11::list org_flat_node2pin_start_map; ///< starting index of each node in flat_node2pin_map
    pybind11::list org_flat_cc2node_map; ///< flat cc2node map
    pybind11::list org_flat_cc2node_start_map; ///< flat cc2node start map
    pybind11::list org_is_cc_node; ///< Specifies if node is part of carry chain 
    pybind11::list org_node2ccId_map; ///< Node id to carry chain indexing
    pybind11::list org_node_x; ///< 1D array, cell position x 
    pybind11::list org_node_y; ///< 1D array, cell position y 
    pybind11::list org_node_z; ///< 1D array, cell position z  (FPGA)
    pybind11::list new2org_node_map; ///< Node id to org node id mapping
    pybind11::list org_ctrlSets; ///< 1D array, FF ctrl set (FPGA)
    pybind11::list org_extended_ctrlSets; ///< 1D array, FF ctrl signals (FPGA)
    pybind11::list org_ext_ctrlSet_start_map; ///< 1D array, FF ctrl set start map (FPGA)
    //pybind11::list flat_cc_input_pins_map; ///< flat carry chain node input pin mapping
    //pybind11::list flat_cc_output_pins_map; ///< flat carry chain node output pin mapping
    //pybind11::list flat_cc_input_pin_start_map; ///< flat carry chain node input pin mapping
    //pybind11::list flat_cc_output_pin_start_map; ///< flat carry chain node output pin mapping
    //pybind11::list overall_cc_input_pin_start_map; ///< overall carry chain node input pin mapping
    //pybind11::list overall_cc_output_pin_start_map; ///< overall carry chain node output pin mapping

    pybind11::list pin_offset_x; ///< 1D array, pin offset x to its node 
    pybind11::list pin_offset_y; ///< 1D array, pin offset y to its node 
    pybind11::list pin_names; ///< 1D array, pin names (FPGA)
    pybind11::list pin_types; ///< 1D array, pin types (FPGA)
    pybind11::list pin_typeIds; ///< 1D array, pin types (FPGA)
    pybind11::list pin2node_map; ///< 1D array, contain parent node id of each pin 
    pybind11::list pin2net_map; ///< 1D array, contain parent net id of each pin 
    pybind11::list pin2nodeType_map; ///< 1D array, pin to node type

    pybind11::list net_names; ///< net name 
    pybind11::list net2pin_map; ///< array of 1D array, each row stores pin id
    pybind11::list flat_net2pin_map; ///< flatten version of net2pin_map 
    pybind11::list flat_net2pin_start_map; ///< starting index of each net in flat_net2pin_map
    pybind11::dict net_name2id_map; ///< net name to id map
    //pybind11::list net_weights; ///< net weight 

    int num_sites_x; ///< number of sites in horizontal direction (FPGA)
    int num_sites_y; ///< number of sites in vertical direction (FPGA)
    pybind11::list siteTypes; ///< 1D array of site types
    pybind11::list siteWidths; ///< 1D array of site widths 
    pybind11::list siteHeights; ///< 1D array of site heights 
    pybind11::list rsrcTypes; ///< 1D array of rsrc types
    pybind11::list rsrcInstWidths; ///< 1D array of rsrc Inst widths 
    pybind11::list rsrcInstHeights; ///< 1D array of rsrc Inst heights 
    pybind11::list siteResources; ///< 2D array of site resources 
    pybind11::list rsrcInsts; ///< 2D array of resource instances
    pybind11::list rsrcInstTypes; ///< 1D array of resource instances
    pybind11::dict rsrc2siteMap; ///< rsrc to site map
    pybind11::dict inst2rsrcMap; ///< inst to rsrc map
    pybind11::dict siteRsrc2CountMap; ///< site rsrc to count map
    pybind11::dict siteType2indexMap; ///< site type to id map
    pybind11::dict rsrcType2indexMap; ///< rsrc type to id map
    pybind11::dict rsrcInstType2indexMap; ///< rsrc inst type to id map
    pybind11::list sliceElements; ///< 1D array of pairs - rsrc type and count
    pybind11::list lutFracturesMap; ///< 2D array of LUT fractures
    pybind11::list sliceFFCtrls; ///< 1D array of pairs - slice ff ctrls
    pybind11::list sliceUnitFFCtrls; ///< 1D array of pairs - slice unit ff ctrls
    pybind11::list siteOutCoordinates; ///< 1D array of site output coordinates 
    pybind11::list siteOutValues; ///< 1D array of site output values 
    pybind11::list site_type_map; ///< 2D array, site type of each site (FPGA)
    pybind11::list lg_siteXYs; ///< 2D array, site XYs for CLB at center (FPGA)
    //pybind11::list regions; ///< array of 1D array, each region contains rectangles 
    pybind11::list dspSiteXYs; ///< 1D array of DSP sites (FPGA)
    pybind11::list ramSite0XYs; ///< 1D array of RAM sites (FPGA)
    pybind11::list ramSite1XYs; ///< 1D array of RAM sites (FPGA)
    pybind11::list sliceSiteXYs; ///< 1D array of Slice sites (FPGA)
    //pybind11::list regionsLimits; ///< array of 1D array, each region contains rectangles 
    pybind11::list flat_region_boxes; ///< flatten version of regions 
    pybind11::list flat_region_boxes_start; ///< starting index of each region in flat_region_boxes

    pybind11::list spiral_accessor; ///< spiral accessor

    pybind11::list ctrlSets; ///< 1D array, FF ctrl set (FPGA)
    pybind11::list extended_ctrlSets; ///< 1D array, FF ctrl signals (FPGA)
    pybind11::list ext_ctrlSet_start_map; ///< 1D array, FF ctrl set start map (FPGA)
    //pybind11::list flat_ctrlSets; ///< 1D array, FF ctrl set (FPGA)
    //unsigned int num_nodes; ///< number of nodes, including terminals and terminal_NIs 
    unsigned int spiral_maxVal; ///< maxVal in spiral_accessor
    unsigned int num_routing_grids_x; ///< number of routing grids in x 
    unsigned int num_routing_grids_y; ///< number of routing grids in y 
    int routing_grid_xl; ///< routing grid region may be different from placement region 
    int routing_grid_yl; 
    int routing_grid_xh; 
    int routing_grid_yh;
    int xl; 
    int yl; 
    int xh; 
    int yh; 

    std::string ff_ctrl_type;
    double wl_weightX;
    double wl_weightY;
    std::string sliceFF_ctrl_mode;
    int lut_maxShared;
    int lut_type_in_sliceUnit;
    int pinRouteCap;
    int routeCapH;
    int routeCapV;

    //Site type Identifier
    int sliceIdx;
    int ioIdx;
    int bramIdx;
    int m9kIdx;
    int m144kIdx;
    int dspIdx;
    int pllIdx;
    int emptyIdx;

    //pybind11::list node2orig_node_map; ///< due to some fixed nodes may have non-rectangular shapes, we flat the node list; 
    //                                    ///< this map maps the new indices back to the original ones 
    //pybind11::list pin_direct; ///< 1D array, pin direction IO 
    //pybind11::list rows; ///< NumRows x 4 array, stores xl, yl, xh, yh of each row 
    //pybind11::list node_count; ///< Node count based on resource type (FPGA)
    //pybind11::list unit_horizontal_capacities; ///< number of horizontal tracks of layers per unit distance 
    //pybind11::list unit_vertical_capacities; /// number of vertical tracks of layers per unit distance 
    //pybind11::list initial_horizontal_demand_map; ///< initial routing demand from fixed cells, indexed by (layer, grid x, grid y) 
    //pybind11::list initial_vertical_demand_map; ///< initial routing demand from fixed cells, indexed by (layer, grid x, grid y)   
    //pybind11::list binCapMaps; ///< array of 2D array, Bin Capacity map for all resource types (FPGA)
    //pybind11::list fixedDemandMaps; ///< array of 2D array, Bin Capacity map for all resource types (FPGA)
    //double total_space_area; ///< total placeable space area excluding fixed cells. 
    //                        ///< This is not the exact area, because we cannot exclude the overlapping fixed cells within a bin. 
    //int num_movable_pins; 

    PyPlaceDB()
    {
    }

    PyPlaceDB(PlaceDB const& db)
    {
        set(db); 
    }

    void set(PlaceDB const& db);
};

DREAMPLACE_END_NAMESPACE

#endif


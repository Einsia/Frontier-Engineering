/**
 * @file   PyPlaceDB.cpp
 * @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Mar 2021
 * @brief  Placement database for python 
 */
#include <cmath>
#include <unordered_set>
#include <unordered_map>
#include "PyPlaceDB.h"
#include <boost/polygon/polygon.hpp>

DREAMPLACE_BEGIN_NAMESPACE

const int INVALID = -1;

bool readBookshelf(PlaceDB& db, std::string const& auxPath)
{
    // read bookshelf 
    if (!auxPath.empty())
    {
        std::string const& filename = auxPath;
        dreamplacePrint(kINFO, "reading %s\n", filename.c_str());
        bool flag = BookshelfParser::read(db, filename);
        if (!flag)
        {
            dreamplacePrint(kERROR, "Bookshelf file parsing failed: %s\n", filename.c_str());
            return false;
        }
        ////DBG
        //else
        //{
        //    std::cout << "Bookshelf file parsing successful " << std::endl;
        //}
        ////DBG
    }
    else dreamplacePrint(kWARN, "no Bookshelf file specified\n");

    return true;
}

void PyPlaceDB::set(PlaceDB const& db) 
{
    num_ccNodes = db.numCCNodes(); //macros
    num_terminals = db.numFixed(); //IOs
    num_movable_nodes = db.numMovable();  // Movable cells
    num_physical_nodes = num_terminals + num_movable_nodes;

    node_count = pybind11::cast(std::move(db.node_count()));

    //Node Info
    node_names = pybind11::cast(std::move(db.nodeNames()));
    node_types = pybind11::cast(std::move(db.nodeTypes()));
    node_size_x = pybind11::cast(std::move(db.nodeXSizes()));
    node_size_y = pybind11::cast(std::move(db.nodeYSizes()));
    node2fence_region_map = pybind11::cast(std::move(db.node2FenceRegionMap()));
    node_x = pybind11::cast(std::move(db.nodeXLocs()));
    node_y = pybind11::cast(std::move(db.nodeYLocs()));
    node_z = pybind11::cast(std::move(db.nodeZLocs()));
    flop_indices = pybind11::cast(std::move(db.flopIndices()));
    lut_type = pybind11::cast(std::move(db.lutTypes()));
    cluster_lut_type = pybind11::cast(std::move(db.clusterlutTypes()));

    ////DBG CHECK contents of lut_type and cluster_lut_type
    //for (int i = 0; i < 10; ++i)
    //{
    //    std::cout << "Instance: " << *node_names[i] << " of type: " << *node_types[i] << " has lut type: " << *lut_type[i];
    //    std::cout << " and cluster_lut_type: " << *cluster_lut_type[i] << std::endl;
    //}
    ////DBG

    //Carry chain Info
    if (num_ccNodes > 0)
    {
        org_num_movable_nodes = db.numOrgMovable();  // Movable cells
        org_node_names = pybind11::cast(std::move(db.orgNodeNames()));
        org_node_types = pybind11::cast(std::move(db.orgNodeTypes()));
        org_node_size_x = pybind11::cast(std::move(db.orgNodeXSizes()));
        org_node_size_y = pybind11::cast(std::move(db.orgNodeYSizes()));
        org_node2fence_region_map = pybind11::cast(std::move(db.orgNode2FenceRegionMap()));
        org_node_count = pybind11::cast(std::move(db.orgNodeCount()));
        org_flop_indices = pybind11::cast(std::move(db.orgFlopIndices()));
        org_lut_type = pybind11::cast(std::move(db.orgLutTypes()));
        org_pin_offset_x = pybind11::cast(std::move(db.orgPinOffsetX()));
        org_pin_offset_y = pybind11::cast(std::move(db.orgPinOffsetY()));
        org_pin2nodeType_map = pybind11::cast(std::move(db.orgPin2NodeTypeMap()));
        org_node2pincount_map = pybind11::cast(std::move(db.orgNode2PinCount()));
        org_pin2node_map = pybind11::cast(std::move(db.orgPin2NodeMap()));
        org_node2outpinCount = pybind11::cast(std::move(db.orgNode2OutPinCount()));
        org_node2outpinIdx_map = pybind11::cast(std::move(db.orgNode2OutPinId()));
        org_flat_node2pin_map = pybind11::cast(std::move(db.orgFlatNode2PinMap()));
        org_flat_node2pin_start_map = pybind11::cast(std::move(db.orgFlatNode2PinStartMap()));
        org_flat_cc2node_map = pybind11::cast(std::move(db.orgflatCCNodeMap()));
        org_flat_cc2node_start_map = pybind11::cast(std::move(db.orgflatCCNodeStartMap()));
        org_is_cc_node = pybind11::cast(std::move(db.isOrgCCNode()));
        org_node_name2id_map = pybind11::cast(std::move(db.orgNodeName2Index()));
        org_node_x = pybind11::cast(std::move(db.orgNodeXLocs()));
        org_node_y = pybind11::cast(std::move(db.orgNodeYLocs()));
        org_node_z = pybind11::cast(std::move(db.orgNodeZLocs()));

        cc_element_count = pybind11::cast(std::move(db.ccElementCount()));
        node2ccId_map = pybind11::cast(std::move(db.node2CCIdMap()));
        cc2nodeId_map = pybind11::cast(std::move(db.cc2nodeIdMap()));
        org_node2ccId_map = pybind11::cast(std::move(db.orgNode2CCIdMap()));
        new2org_node_map= pybind11::cast(std::move(db.new2OrgNodeMap()));
        is_cc_node = pybind11::cast(std::move(db.isCCNode()));
        //flat_cc_input_pins_map = pybind11::cast(std::move(db.flatCCInputPinsMap()));
        //flat_cc_output_pins_map = pybind11::cast(std::move(db.flatCCOutputPinsMap()));
        //flat_cc_input_pin_start_map = pybind11::cast(std::move(db.flatCCInputPinStartMap()));
        //flat_cc_output_pin_start_map = pybind11::cast(std::move(db.flatCCOutputPinStartMap()));
        //overall_cc_input_pin_start_map = pybind11::cast(std::move(db.overallCCInputPinStartMap()));
        //overall_cc_output_pin_start_map = pybind11::cast(std::move(db.overallCCOutputPinStartMap()));
    }

    node2outpinIdx_map = pybind11::cast(std::move(db.node2OutPinId()));
    node2outpinCount = pybind11::cast(std::move(db.node2OutPinCount()));
    node2pincount_map = pybind11::cast(std::move(db.node2PinCount()));
    node2pin_map = pybind11::cast(std::move(db.node2PinMap()));
    node_name2id_map = pybind11::cast(std::move(db.nodeName2Index()));
    //movable_node_name2id_map = pybind11::cast(std::move(db.movNodeName2Index()));
    //fixed_node_name2id_map = pybind11::cast(std::move(db.fixedNodeName2Index()));
    flat_node2pin_map = pybind11::cast(std::move(db.flatNode2PinMap()));
    flat_node2pin_start_map = pybind11::cast(std::move(db.flatNode2PinStartMap()));

    net_names = pybind11::cast(std::move(db.netNames()));
    net2pincount_map = pybind11::cast(std::move(db.net2PinCount()));
    net2pin_map = pybind11::cast(std::move(db.net2PinMap()));
    flat_net2pin_map = pybind11::cast(std::move(db.flatNet2PinMap()));
    flat_net2pin_start_map = pybind11::cast(std::move(db.flatNet2PinStartMap()));
    net_name2id_map = pybind11::cast(std::move(db.netName2Index()));

    pin_names = pybind11::cast(std::move(db.pinNames()));
    pin_types = pybind11::cast(std::move(db.pinTypes()));
    pin_typeIds = pybind11::cast(std::move(db.pinTypeIds()));
    pin_offset_x = pybind11::cast(std::move(db.pinOffsetX()));
    pin_offset_y = pybind11::cast(std::move(db.pinOffsetY()));
    pin2net_map = pybind11::cast(std::move(db.pin2NetMap()));
    pin2node_map = pybind11::cast(std::move(db.pin2NodeMap()));
    pin2nodeType_map = pybind11::cast(std::move(db.pin2NodeTypeMap()));

    //////DBG
    //std::cout << "There are " << std::to_string(num_physical_nodes) << " nodes, " << std::to_string(db.numPins()) 
    //          << " pins and " << std::to_string(db.numNets()) << " nets and " << std::to_string(db.numCCNodes()) 
    //          << " macros in the design" << std::endl;
    //////DBG

    //CtrlSets
    sliceFFCtrls = pybind11::cast(std::move(db.slice_FF_ctrls()));
    sliceUnitFFCtrls = pybind11::cast(std::move(db.sliceUnit_FF_ctrls()));

    //TODO - Make FF Ctrl signal generation part generic for any architecture
    //Currently only US and Stratix-IV architectures supported
    if (db.slice_ff_ctrl_mode() == "HALF")
    {
        //Xilinx US and related
        std::unordered_map<PlaceDB::index_type, PlaceDB::index_type> ceMapping;
        std::unordered_map<PlaceDB::index_type, std::unordered_map<PlaceDB::index_type, PlaceDB::index_type> > cksrMapping;
        PlaceDB::index_type numCKSR(0), numCE(0);

        for (unsigned int sFIdx = 0; sFIdx < db.numFF(); ++sFIdx)
        {
            unsigned int fIdx = db.flopIndex(sFIdx);

            int ck(INVALID), sr(INVALID), ce(INVALID), cksrId(INVALID), ceId(INVALID);

            //for (auto pin_id : node.pinIdArray())
            for (unsigned int pIdx = 0; pIdx < db.node2PinCnt(fIdx); ++pIdx)
            {
                PlaceDB::index_type pin_id = db.node2PinIdx(fIdx, pIdx);

                switch(pin_typeIds[pin_id].cast<PlaceDB::index_type>())
                {
                    case 2:
                        {
                            ck = pin2net_map[pin_id].cast<PlaceDB::index_type>();
                            break;
                        }
                    case 3:
                        {
                            ce = pin2net_map[pin_id].cast<PlaceDB::index_type>();
                            break;
                        }
                    case 4:
                        {
                            sr = pin2net_map[pin_id].cast<PlaceDB::index_type>();
                            break;
                        }
                    default:
                        {
                            break;
                        }
                }
            }

            auto ckIt = cksrMapping.find(ck);

            if (ckIt == cksrMapping.end())
            {
                cksrId = numCKSR;
                cksrMapping[ck][sr] = numCKSR++;
            } else
            {
                auto &srMap = ckIt->second;
                auto srIt = srMap.find(sr);
                if (srIt == srMap.end())
                {
                    cksrId = numCKSR;
                    srMap[sr] = numCKSR++;
                } else
                {
                    cksrId = srIt->second;
                }
            }

            auto ceIt = ceMapping.find(ce);
            if (ceIt == ceMapping.end())
            {
                ceId = numCE;
                ceMapping[ce] = numCE++;
            } else
            {
                ceId = ceIt->second;
            }
            ctrlSets.append(std::make_tuple(fIdx, cksrId, ceId));
            if (num_ccNodes > 0)
            {
                org_ctrlSets.append(std::make_tuple(db.orgNodeMap(fIdx), cksrId, ceId));
            }
        }
    } else
    {
        //Intel Stratix-IV and related
        std::unordered_map<PlaceDB::index_type, PlaceDB::index_type> clkMapping;
        PlaceDB::index_type numCTRL(0), numCLK(0);

        int ctrl_signal_count = db.slice_FF_ctrl_count(1);
        dreamplaceAssertMsg((ctrl_signal_count == 7), "Check if correct Ctrl signal count is provided");

        std::vector<int> ff_ctrls;

        ext_ctrlSet_start_map.append(0);
        if (num_ccNodes > 0)
        {
            org_ext_ctrlSet_start_map.append(0);
        }

        for (unsigned int sFIdx = 0; sFIdx < db.numFF(); ++sFIdx)
        {
            unsigned int fIdx = db.flopIndex(sFIdx);

            int ck(INVALID), ckId(INVALID);

            std::vector<int> curVal(10, INVALID);

            for (unsigned int pIdx = 0; pIdx < db.node2PinCnt(fIdx); ++pIdx)
            {
                PlaceDB::index_type pin_id = db.node2PinIdx(fIdx, pIdx);
                PlaceDB::index_type pinTypeId = pin_typeIds[pin_id].cast<PlaceDB::index_type>();

                if(pinTypeId > 1 && pinTypeId < 10)
                {
                    curVal[pinTypeId] = pin2net_map[pin_id].cast<PlaceDB::index_type>();

                    if (pinTypeId == 2) //CLK
                    {
                        ck = curVal[pinTypeId];
                    } else if (curVal[pinTypeId] != INVALID) 
                    {
                        ff_ctrls.emplace_back(curVal[pinTypeId]);
                    }
                }
            }
            ext_ctrlSet_start_map.append(ff_ctrls.size());
            if (num_ccNodes > 0)
            {
                org_ext_ctrlSet_start_map.append(ff_ctrls.size());
            }

            auto ckIt = clkMapping.find(ck);
            if (ckIt == clkMapping.end())
            {
                ckId = numCLK;
                clkMapping[ck] = numCLK++;
            } else
            {
                ckId = ckIt->second;
            }

            ctrlSets.append(std::make_tuple(fIdx, ckId, 0));
            if (num_ccNodes > 0)
            {
                org_ctrlSets.append(std::make_tuple(db.orgNodeMap(fIdx), ckId, 0));
            }
        }
        extended_ctrlSets = pybind11::cast(std::move(ff_ctrls));
        if (num_ccNodes > 0)
        {
            org_extended_ctrlSets = pybind11::cast(std::move(ff_ctrls));
        }

        dreamplacePrint(kINFO, "Design has %d unique clk signal(s) and multiple ctrl_mode combinations\n", numCLK);
    }

    //SiteInfo
    siteTypes = pybind11::cast(std::move(db.site_types()));
    siteWidths = pybind11::cast(std::move(db.site_widths()));
    siteHeights = pybind11::cast(std::move(db.site_heights()));
    rsrcTypes = pybind11::cast(std::move(db.rsrc_types()));
    rsrcInstWidths = pybind11::cast(std::move(db.rsrc_inst_widths()));
    rsrcInstHeights = pybind11::cast(std::move(db.rsrc_inst_heights()));
    siteResources = pybind11::cast(std::move(db.site_resources_map()));
    rsrcInsts = pybind11::cast(std::move(db.rsrc_insts_map()));
    rsrc2siteMap = pybind11::cast(std::move(db.rsrc2site_map()));
    inst2rsrcMap = pybind11::cast(std::move(db.inst2rsrc_map()));
    siteRsrc2CountMap = pybind11::cast(std::move(db.site_rsrc2count_map()));
    siteType2indexMap = pybind11::cast(std::move(db.site_type2index_map()));
    rsrcType2indexMap = pybind11::cast(std::move(db.rsrc_type2index_map()));
    rsrcInstType2indexMap = pybind11::cast(std::move(db.rsrc_inst_type2index_map()));
    sliceElements = pybind11::cast(std::move(db.slice_elements()));
    rsrcInstTypes = pybind11::cast(std::move(db.rsrc_inst_types()));
    lutFracturesMap = pybind11::cast(std::move(db.lut_fractures_map()));
    siteOutCoordinates = pybind11::cast(std::move(db.site_out_coordinates()));
    siteOutValues = pybind11::cast(std::move(db.site_out_values()));

    xl = db.xl(); 
    yl = db.yl(); 
    xh = db.xh(); 
    yh = db.yh(); 

    //Initialize site_type2index values that are used
    sliceIdx = INVALID;
    ioIdx = INVALID;
    bramIdx = INVALID;
    m9kIdx = INVALID;
    m144kIdx = INVALID;
    dspIdx = INVALID;
    pllIdx = INVALID;
    emptyIdx = INVALID;

    if (db.site_type2index_map().find("SLICE") != db.site_type2index_map().end())
    {
        sliceIdx = db.site_type2index("SLICE");
    }
    if (db.site_type2index_map().find("io") != db.site_type2index_map().end())
    {
        ioIdx = db.site_type2index("io");
    } else if(db.site_type2index_map().find("IO") != db.site_type2index_map().end())
    {
        ioIdx = db.site_type2index("IO");
    }
    if (db.site_type2index_map().find("BRAM") != db.site_type2index_map().end())
    {
        bramIdx = db.site_type2index("BRAM");
    }
    if (db.site_type2index_map().find("M9K") != db.site_type2index_map().end())
    {
        m9kIdx = db.site_type2index("M9K");
    }
    if (db.site_type2index_map().find("M144K") != db.site_type2index_map().end())
    {
        m144kIdx = db.site_type2index("M144K");
    }
    if (db.site_type2index_map().find("DSP") != db.site_type2index_map().end())
    {
        dspIdx = db.site_type2index("DSP");
    }
    if (db.site_type2index_map().find("PLL") != db.site_type2index_map().end())
    {
        pllIdx = db.site_type2index("PLL");
    }
    if (db.site_type2index_map().find("EMPTY") != db.site_type2index_map().end())
    {
        emptyIdx = db.site_type2index("EMPTY");
    }

    typedef Box<PlaceDB::index_type> box_type;
    std::vector<std::vector<box_type> > region_boxes(db.site_types().size()+1);

    int maxVal = std::max(db.siteRows(), db.siteCols());

    for (int i = 0, ie = db.siteRows(); i < ie; ++i)
    {
        pybind11::list rowVals, lg_rowXY; 
        for (int j = 0, je = db.siteCols(); j < je; ++j)
        {
            pybind11::list siteXY, lg_Site;

            if (db.siteVal(i,j) == sliceIdx)
            {
                lg_Site.append(i+0.5);
                lg_Site.append(j+0.5);
            } else
            {
                lg_Site.append(i);
                lg_Site.append(j);
            }
            lg_rowXY.append(lg_Site);
            if(db.siteVal(i,j) != 0 && db.siteVal(i,j) != emptyIdx)
            {
                if (db.siteVal(i,j) == sliceIdx)
                {
                    siteXY.append(i);
                    siteXY.append(j);
                    sliceSiteXYs.append(siteXY);

                    int siteW = int(db.site_width(sliceIdx));
                    int siteH = int(db.site_height(sliceIdx));
                    Box<PlaceDB::index_type> slicebox(i, j, i+siteW, j+siteH);

                    if (region_boxes[sliceIdx].size() == 0)
                    {
                        region_boxes[sliceIdx].emplace_back(slicebox);
                    } else
                    {
                        if (!mergeBoxes(slicebox, region_boxes[sliceIdx].back(), db.site_per_column()))
                        {
                            region_boxes[sliceIdx].emplace_back(slicebox);
                        }
                    }
                } 
                else if (db.siteVal(i,j) == dspIdx || db.siteVal(i,j) == bramIdx || db.siteVal(i,j) == m9kIdx || db.siteVal(i,j) == m144kIdx)
                {
                    double siteHeight = db.site_height(db.siteVal(i,j));
                    siteXY.append(i);

                    int siteW = int(db.site_width(db.siteVal(i,j)));
                    int siteH = int(siteHeight);
                    Box<PlaceDB::index_type> drbox(i, j, i+siteW, j+siteH);

                    if (std::floor(siteHeight) == siteHeight)
                    {
                        siteXY.append(j);
                    } else
                    {
                        siteXY.append(std::round(j/siteHeight)*siteHeight);
                        drbox.set(i, int(std::round(j/siteHeight)*siteHeight), i+siteW, int(std::round((j+siteH)/siteHeight)*siteHeight));
                    }
                    if (region_boxes[db.siteVal(i,j)].size() == 0)
                    {
                        region_boxes[db.siteVal(i,j)].emplace_back(drbox);
                    } else
                    {
                        if (!mergeBoxes(drbox, region_boxes[db.siteVal(i,j)].back(), db.site_per_column()))
                        {
                            region_boxes[db.siteVal(i,j)].emplace_back(drbox);
                        }
                    }

                    if (db.siteVal(i,j) == dspIdx)
                    {
                        dspSiteXYs.append(siteXY);
                    } else if (db.siteVal(i,j) == bramIdx || db.siteVal(i,j) == m9kIdx)
                    {
                        ramSite0XYs.append(siteXY);
                    } else
                    {
                        ramSite1XYs.append(siteXY);
                    }
                } else if (db.siteVal(i,j) == ioIdx)
                {
                    int siteW = int(db.site_width(ioIdx));
                    int siteH = int(db.site_height(ioIdx));
                    Box<PlaceDB::index_type> iobox(i, j, i+siteW, j+siteH);

                    if (region_boxes[ioIdx].size() == 0)
                    {
                        region_boxes[ioIdx].emplace_back(iobox);
                    } else
                    {
                        if (!mergeBoxes(iobox, region_boxes[ioIdx].back(), db.site_per_column()))
                        {
                            region_boxes[ioIdx].emplace_back(iobox);
                        }
                    }
                } else if (db.siteVal(i,j) == pllIdx)
                {
                    int siteW = int(db.site_width(pllIdx));
                    int siteH = int(db.site_height(pllIdx));
                    Box<PlaceDB::index_type> pllbox(i, j, i+siteW, j+siteH);

                    if (region_boxes[pllIdx].size() == 0)
                    {
                        region_boxes[pllIdx].emplace_back(pllbox);
                    } else
                    {
                        if (!mergeBoxes(pllbox, region_boxes[pllIdx].back(), db.site_per_column()))
                        {
                            region_boxes[pllIdx].emplace_back(pllbox);
                        }
                    }
                }
            }

            rowVals.append(db.siteVal(i,j));
        }
        site_type_map.append(rowVals);
        lg_siteXYs.append(lg_rowXY);
    }

    //Update flat_region_boxes and flat_region_boxes_start using region_boxes
    unsigned int flat_len = 0;
    flat_region_boxes_start.append(flat_len);
    for (unsigned int rgn = 0; rgn < db.rsrc_types().size(); ++rgn)
    {
        int site_type = db.site_type2index(db.rsrc_type2site(db.rsrc_type(rgn)));
        for (auto el : region_boxes[site_type])
        {
            pybind11::list flat_region;
            flat_region.append(el.xl());
            flat_region.append(el.yl());
            flat_region.append(el.xh());

            if (db.site_per_column() == 1)
            {
                flat_region.append(yh);
            } else
            {
                flat_region.append(el.yh());
            }

            flat_region_boxes.append(flat_region);
            flat_len += 1;
        }
        flat_region_boxes_start.append(flat_len);
    }


    num_sites_x = db.siteRows();
    num_sites_y = db.siteCols();

    // routing information initialized 
    num_routing_grids_x = db.width(); 
    num_routing_grids_y = db.height(); 
    routing_grid_xl = xl; 
    routing_grid_yl = yl; 
    routing_grid_xh = xh; 
    routing_grid_yh = yh; 

    ff_ctrl_type = db.ff_ctrl_type();
    wl_weightX = db.wl_weight_x();
    wl_weightY = db.wl_weight_y();
    sliceFF_ctrl_mode = db.slice_ff_ctrl_mode();
    lut_maxShared = db.lut_shared_max_pins();
    lut_type_in_sliceUnit = db.lut_type_in_sliceUnit();
    pinRouteCap = db.pin_route_cap();
    routeCapH = db.route_cap_h();
    routeCapV = db.route_cap_v();

    ////Spiral Accessor
    unsigned int rad = std::max(num_sites_x, num_sites_y);
    spiral_maxVal = (2 * rad * (1+rad)) +1; 
    spiral_accessor.append(std::make_tuple(0, 0));

    for(int r = 1; r <= rad; ++r)
    {
        // The 1st quadrant
        for (int x = r, y = 0; y < r; --x, ++y)
        {
            spiral_accessor.append(std::make_tuple(x, y));
        }
        // The 2nd quadrant
        for (int x = 0, y = r; y > 0; --x, --y)
        {
            spiral_accessor.append(std::make_tuple(x, y));
        }
        // The 3rd quadrant
        for (int x = -r, y = 0; y > -r; ++x, --y)
        {
            spiral_accessor.append(std::make_tuple(x, y));
        }
        // The 4th quadrant
        for (int x = 0, y = -r; y < 0; ++x, ++y)
        {
            spiral_accessor.append(std::make_tuple(x, y));
        }
    }
}

DREAMPLACE_END_NAMESPACE


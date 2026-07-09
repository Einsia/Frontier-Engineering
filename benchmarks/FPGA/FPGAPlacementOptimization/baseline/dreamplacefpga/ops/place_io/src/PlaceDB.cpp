/*************************************************************************
    > File Name: PlaceDB.cpp
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#include "PlaceDB.h"
#include <numeric>
#include <algorithm>
#include <cmath>
#include <string>
#include "BookshelfWriter.h"
#include "Iterators.h"
#include "utility/src/Msg.h"

DREAMPLACE_BEGIN_NAMESPACE

int get_last_digit_from_string(const std::string &val)
{
    //Conversion of char to int
    return (int)val.back()-48;
}

/// default constructor
PlaceDB::PlaceDB() {
  num_movable_nodes = 0;
  num_fixed_nodes = 0;
  m_numLibCell = 0;
  m_numLUT = 0;
  m_numFF = 0;
  m_numCCs = 0;
  wlXWeight = 0.0;
  wlYWeight = 0.0;
  pinRouteCap = 0;
  routeCapH = 0;
  routeCapV = 0;
}

void PlaceDB::add_bookshelf_node(std::string& name, std::string& type) 
{
    ////DBG
    //std::cout << " add bookshelf node " << name << " of type " << type << std::endl;
    ////DBG
    index_type rsrcType(rsrcTypes.size()+1);
    std::string rsrcName;

    string2string_map_type::iterator fnd = inst2RsrcMap.find(type);
    if (fnd == inst2RsrcMap.end())
    {
        dreamplacePrint(kWARN, "Unknown instance type not found in .scl file: %s, %s\n",
                type.c_str());
    } else
    {
        rsrcName = inst2RsrcMap[type];
        rsrcType = rsrcType2IndexMap[rsrcName];
    }

    if (rsrcType < rsrcTypes.size())
    {
        if (node_names.size() == 0 && fixed_node_names.size() == 0)
        {
            nodeCount.resize(rsrcTypes.size());
        }
        ++nodeCount[rsrcType];

        if (rsrcType == ioId || rsrcType == pllId)
        {
    ////DBG
    //std::cout << "Added fixed bookshelf node " << name << " of type " << type 
    //         << " with fixed nodeId: " << fixed_node_names.size() << std::endl;
    ////DBG
            fixed_node_name2id_map.insert(std::make_pair(name, fixed_node_names.size()));
            fixed_node_names.emplace_back(name);
            fixed_node_types.emplace_back(type);
            fixed_node2fence_region_map.emplace_back(rsrcType);
            fixed_node_x.emplace_back(0.0);
            fixed_node_y.emplace_back(0.0);
            fixed_node_z.emplace_back(0);
            ++num_fixed_nodes;

            double width(0.0), height(0.0);

            string2index_map_type::iterator found = rsrcInstType2IndexMap.find(type);
            if (found != rsrcInstType2IndexMap.end())
            {
                width = rsrcInstWidth[rsrcInstType2IndexMap[type]];
                height = rsrcInstHeight[rsrcInstType2IndexMap[type]];
            } else
            {
                width = rsrcInstWidth[rsrcType2IndexMap[rsrcName]];
                height = rsrcInstHeight[rsrcType2IndexMap[rsrcName]];
            }

            fixed_node_size_x.emplace_back(width);
            fixed_node_size_y.emplace_back(height);
            fixed_lut_type.emplace_back(0);
            fixed_cluster_lut_type.emplace_back(0);

        } else
        {
    ////DBG
    //std::cout << "Added movable bookshelf node " << name << " of type " << type << " with nodeId: " << node_names.size() << std::endl;
    ////DBG
            node_name2id_map.insert(std::make_pair(name, node_names.size()));
            node_names.emplace_back(name);
            node_types.emplace_back(type);
            node2fence_region_map.emplace_back(rsrcType);
            node_x.emplace_back(0.0);
            node_y.emplace_back(0.0);
            node_z.emplace_back(0);
            ++num_movable_nodes;

            double width(0.0), height(0.0);

            string2index_map_type::iterator found = rsrcInstType2IndexMap.find(type);
            if (found != rsrcInstType2IndexMap.end())
            {
                width = rsrcInstWidth[rsrcInstType2IndexMap[type]];
                height = rsrcInstHeight[rsrcInstType2IndexMap[type]];
            } else //FF, CARRY8
            {
                width = rsrcInstWidth[rsrcType2IndexMap[rsrcName]];
                height = rsrcInstHeight[rsrcType2IndexMap[rsrcName]];
            }

            if (rsrcType == lutId)
            {
                node_size_x.emplace_back(std::sqrt(width));
                node_size_y.emplace_back(std::sqrt(height));
                int val = get_last_digit_from_string(type);
                lut_type.emplace_back(val);
                //std::cout << "Instance: " << name << " of type: " << type << " has lut type: " << val;
                --val;
                val = std::max(0, val);
                cluster_lut_type.emplace_back(val);
                lut_indices.emplace_back(node_names.size()-1);
                //std::cout << " and cluster lut type: " << val << std::endl;
                ++m_numLUT;
            }
            else if (rsrcType == ffId)
            {
                node_size_x.emplace_back(std::sqrt(width));
                node_size_y.emplace_back(std::sqrt(height));
                lut_type.emplace_back(0);
                cluster_lut_type.emplace_back(0);
                flop_indices.emplace_back(node_names.size()-1);
                ++m_numFF;
            } else
            {
                node_size_x.emplace_back(width);
                node_size_y.emplace_back(height);
                lut_type.emplace_back(0);
                cluster_lut_type.emplace_back(0);
            }
        }

    } else
    {
        dreamplacePrint(kWARN, "Unknown type component found in .nodes file: %s, %s of type: %s with id: %d\n",
                name.c_str(), type.c_str(), rsrcName.c_str(), rsrcType);
    }

    std::vector<index_type> temp;
    node2pin_map.emplace_back(temp);
    node2pincount_map.emplace_back(0);
    is_cc_node.emplace_back(0);
    node2ccId_map.emplace_back(-1);
    org_node2ccIndex_map.emplace_back(-1);
    ////DBG
    //std::cout << "Added bookshelf node " << name << " of type " << type << std::endl;
    ////DBG
}

void PlaceDB::update_nodes() {
    index_type num_nodes = 0;
    //Re-arrange all nodes to accomodate carry chains
    if (m_numCCs > 0)
    {
        ////DBG
        //std::cout << " Update nodes before reading design net information" << std::endl;
        ////DBG

        num_nodes = node_names.size()+fixed_node_names.size();

        //Carry Chains are movable nodes
        org_num_movable_nodes = num_movable_nodes;
        org_node_name2id_map = node_name2id_map;
        org_node_size_x = node_size_x;
        org_node_size_y = node_size_y;
        org_node2fence_region_map = node2fence_region_map;
        org_node_names = node_names; 
        org_node_types = node_types; 
        org_nodeCount = nodeCount;
        org_is_cc_node = is_cc_node;
        org_node2ccId_map = node2ccId_map;
        org_flop_indices = flop_indices;
        org_lut_type = lut_type;
        org_node2pincount_map = node2pincount_map;
        org_node2pin_map = node2pin_map;

        org_node_x = node_x;
        org_node_y = node_y;
        org_node_z = node_z;
        index_type numFF = m_numFF;
        index_type numLUT = m_numLUT;
        std::vector<index_type> temp_cluster_lut_type = cluster_lut_type;

        node_name2id_map.clear();
        lut_type.clear();
        cluster_lut_type.clear();
        node_size_x.clear();
        node_size_y.clear();
        node_names.clear();
        node_types.clear();
        node_x.clear();
        node_y.clear();
        node_z.clear();
        node2fence_region_map.clear();
        is_cc_node.clear();
        node2ccId_map.clear();
        flop_indices.clear();
        nodeCount.clear();
        nodeCount.resize(org_nodeCount.size(),0);
        new2org_node_map.resize(num_nodes, -1);
        cc2nodeId_map.clear();
        cc2nodeId_map.resize(m_numCCs, 0);

        if (ioId != 100000)
        {
            nodeCount[ioId] = org_nodeCount[ioId];
        }
        if (pllId != 100000)
        {
            nodeCount[pllId] = org_nodeCount[pllId];
        }

        m_numFF = 0;
        m_numLUT = 0;
        num_movable_nodes = 0;

        for (unsigned int nId = 0; nId < org_num_movable_nodes; ++nId)
        {
            if (org_is_cc_node[nId] == 0) //Not a carry node
            {
                std::string node_name = org_node_names[nId];
                index_type rId = org_node2fence_region_map[nId];

                node_name2id_map[node_name] = node_names.size(); 
                node_size_x.emplace_back(org_node_size_x[nId]);
                node_size_y.emplace_back(org_node_size_y[nId]);
                node_types.emplace_back(org_node_types[nId]);
                node2fence_region_map.emplace_back(rId);

                node_x.emplace_back(org_node_x[nId]);
                node_y.emplace_back(org_node_y[nId]);
                node_z.emplace_back(org_node_z[nId]);
                lut_type.emplace_back(org_lut_type[nId]);
                cluster_lut_type.emplace_back(temp_cluster_lut_type[nId]);

                new2org_node_map[node_names.size()] = nId;
                if (rId == ffId)
                {
                    ++m_numFF;
                    flop_indices.emplace_back(node_names.size());
                } 
                else if (rId == lutId)
                {
                    ++m_numLUT;
                }

                node_names.emplace_back(node_name);
                ++nodeCount[rId];
                node2ccId_map.emplace_back(-1);
                is_cc_node.emplace_back(0);

                std::vector<index_type> temp;
            } else
            {
                index_type ccId = org_node2ccId_map[nId];
                index_type cc_headId = org_flat_cc2node_map[org_flat_cc2node_start_map[ccId]];
                std::string cc_name = org_node_names[cc_headId]; 
                index_type rId = org_node2fence_region_map[cc_headId];

                string2index_map_type::iterator found = node_name2id_map.find(cc_name);

                if (found != node_name2id_map.end())
                {
                    //Node part of existing carry chain 
                    std::string node_name = org_node_names[nId];
                    index_type cc_nodeId = node_name2id_map[cc_name];
                    node_name2id_map[node_name] = cc_nodeId;

                    //Assign larger type to root
                    if (org_lut_type[nId] > lut_type[cc_nodeId])
                    {
                        lut_type[cc_nodeId] = org_lut_type[nId];
                        cluster_lut_type[cc_nodeId] = temp_cluster_lut_type[nId];
                        node_types[cc_nodeId] = org_node_types[nId];
                    }
                    ////DBG
                    //std::cout << nId << " Node " << node_name << " assigned to " << node_name2id_map[cc_name] << std::endl;
                    ////DBG
                } else
                {
                    node_name2id_map[cc_name] = node_names.size(); //Assign nodeId for root node 
                    node_name2id_map[org_node_names[nId]] = node_name2id_map[cc_name]; //Assign current node if not root to same nodeId
                    lut_type.emplace_back(org_lut_type[cc_headId]);
                    cluster_lut_type.emplace_back(temp_cluster_lut_type[cc_headId]);
                    node_types.emplace_back(org_node_types[cc_headId]);
                    node_x.emplace_back(org_node_x[cc_headId]);
                    node_y.emplace_back(org_node_y[cc_headId]);
                    node_z.emplace_back(org_node_z[cc_headId]);
                    node2fence_region_map.emplace_back(rId);

                    node_size_x.emplace_back(std::sqrt(org_node_size_x[cc_headId]*org_node_size_x[cc_headId]*cc_element_count[ccId]));
                    node_size_y.emplace_back(std::sqrt(org_node_size_y[cc_headId]*org_node_size_y[cc_headId]*cc_element_count[ccId]));

                    ////DBG
                    //std::cout << nId << " Carry chain " << cc_name << " " << node_name2id_map[cc_name]
                    //          << " with " << cc_element_count[ccId] << " elements is of size "
                    //          << node_size_x.back() << " x "
                    //          << node_size_y.back() << std::endl;
                    ////DBG

                    new2org_node_map[node_names.size()] = cc_headId;
                    if (rId == ffId)
                    {
                        ++m_numFF;
                        flop_indices.emplace_back(node_names.size());
                    } 
                    else if (rId == lutId)
                    {
                        ++m_numLUT;
                    }

                    cc2nodeId_map[ccId] = node_names.size();
                    node2ccId_map.emplace_back(ccId); //Same as org
                    is_cc_node.emplace_back(1);
                    node_names.emplace_back(cc_name);
                    ++nodeCount[rId];
                }
            }
        }

        index_type org_num_nodes = org_num_movable_nodes + fixed_node_names.size();
        org_is_cc_node.resize(org_num_nodes,0);
        org_node2pincount_map.resize(org_num_nodes, 0);
        org_node2outpinCount.resize(org_num_nodes, 0);
        org_node2outpinIdx_map.resize(4*org_num_nodes, -1);
        org_node2pin_map.resize(org_num_nodes);
    }

    num_movable_nodes = node_names.size();
    num_nodes = num_movable_nodes + fixed_node_names.size();
    is_cc_node.resize(num_nodes,0);
    node2pincount_map.resize(num_nodes, 0);
    node2outpinCount.resize(num_nodes, 0);
    node2outpinIdx_map.resize(4*num_nodes, -1);
    node2pin_map.resize(num_nodes);

    ////DBG
    //std::cout << "Total nodes: " << num_nodes 
    //          << " = " << num_movable_nodes << " + "
    //          << fixed_node_names.size() << std::endl;
    ////DBG

}

void PlaceDB::add_bookshelf_net(BookshelfParser::Net const& n) {

    ////DBG
    //std::cout << " Add bookshelf net: " << n.net_name << " with " << n.vNetPin.size() << std::endl;
    ////DBG

    // check the validity of nets
    // if a node has multiple pins in the net, only one is kept
    std::vector<BookshelfParser::NetPin> vNetPin = n.vNetPin;

    index_type netId(net_names.size());
    net2pincount_map.emplace_back(vNetPin.size());
    net_name2id_map.insert(std::make_pair(n.net_name, netId));
    net_names.emplace_back(n.net_name);

    std::vector<index_type> netPins;
    if (flat_net2pin_start_map.size() == 0)
    {
        flat_net2pin_start_map.emplace_back(0);
    }

    for (unsigned i = 0; i < vNetPin.size(); ++i) 
    {   
        BookshelfParser::NetPin const& netPin = vNetPin[i];
        index_type nodeId, org_nodeId, pinId(pin_names.size());

        ////DBG
        //std::cout << "Consider net pin " <<  netPin.pin_name << std::endl;
        ////DBG

        pin_names.emplace_back(netPin.pin_name);
        pin2net_map.emplace_back(netId);

        string2index_map_type::iterator found = node_name2id_map.find(netPin.node_name);
        std::string nodeType, org_nodeType;

        ////DBG
        //std::cout << "Consider net pin connected to node " <<  netPin.node_name << std::endl;
        ////DBG
        if (found != node_name2id_map.end())
        {
            nodeId = node_name2id_map.at(netPin.node_name);
            ////DBG
            //std::cout << "Here for net pin " <<  netPin.pin_name << " part of nodeId: " << nodeId << " " << netPin.node_name << std::endl;
            ////DBG

            pin2nodeType_map.emplace_back(node2fence_region_map[nodeId]);
            ////DBG
            //std::cout << "Here for net pin " <<  netPin.pin_name << " with pin node type: " << node2fence_region_map[nodeId] << std::endl;
            ////DBG

            nodeType = node_types[nodeId];
            ////DBG
            //std::cout << "Here for net pin " <<  netPin.pin_name << " with node type: " << nodeType << std::endl;
            ////DBG


            if (is_cc_node[nodeId] == 0)
            {
                pin_offset_x.emplace_back(0.5*node_size_x[nodeId]);
                ////DBG
                //std::cout << "Here for net pin " <<  netPin.pin_name << " with pin_offset_x : " << 0.5*node_size_x[nodeId] << std::endl;
                ////DBG
                pin_offset_y.emplace_back(0.5*node_size_y[nodeId]);
                ////DBG
                //std::cout << "Here for net pin " <<  netPin.pin_name << " with pin_offset_y : " << 0.5*node_size_y[nodeId] << std::endl;
                ////DBG
            } else
            { //carry chain node
                pin_offset_x.emplace_back(0.5*node_size_x[nodeId]);
                org_nodeId = org_node_name2id_map.at(netPin.node_name);
                index_type ccId = org_node2ccId_map[org_nodeId];
                double element_height = node_size_y[nodeId]/cc_element_count[ccId];
                pin_offset_y.emplace_back((org_node2ccIndex_map[org_nodeId]+0.5)*element_height);

                ////DBG
                //std::cout << "Net pin " <<  netPin.pin_name << " of node: "
                //          << netPin.node_name << " part of " << cc_element_count[ccId]
                //          << " node carry chain has node2ccIndex: "
                //          << org_node2ccIndex_map[org_nodeId] << " has pin_offset: "
                //          << pin_offset_x.back() << " x "
                //          << pin_offset_y.back() << std::endl;
                ////DBG

                //index_type inv_ccIndex = cc_element_count[node2ccId_map[nodeId]] -1 - org_node2ccIndex_map[org_nodeId];
                //LibCell const& lCell = m_vLibCell.at(m_LibCellName2Index.at(nodeType));
                //int pinTypeId(lCell.pinType(netPin.pin_name));

                //if (pinTypeId == 1) //Input
                //{
                //    temp_input_pin_info[ccId].emplace_back(std::make_pair(pinId, inv_ccIndex));
                //} else if (pinTypeId == 0 || pinTypeId == 20) //Output pin
                //{
                //    temp_output_pin_info[ccId].emplace_back(std::make_pair(pinId, inv_ccIndex));
                //}

                ////DBG
                //if (ccId == 0)
                //{
                //    std::cout << "CC0 Consider pin " << netPin.pin_name << " of type: " << pinTypeId 
                //              << " with offset: " << inv_ccIndex << " ("
                //              << org_node2ccIndex_map[org_nodeId] << ")" << std::endl;
                //}
                ////DBG
            }
            //Required to udpate original datastructures
            if (m_numCCs > 0)
            {
                org_nodeId = org_node_name2id_map.at(netPin.node_name);
                org_pin2nodeType_map.emplace_back(org_node2fence_region_map[org_nodeId]);
                org_nodeType = org_node_types[org_nodeId];
                org_pin_offset_x.emplace_back(0.5*org_node_size_x[org_nodeId]);
                org_pin_offset_y.emplace_back(0.5*org_node_size_y[org_nodeId]);
            }
        } else
        {
        ////DBG
        //std::cout << " Node is fixed type " <<  nodeType << " in lib" << std::endl;
        ////DBG
            string2index_map_type::iterator fnd = fixed_node_name2id_map.find(netPin.node_name);
            if (fnd != fixed_node_name2id_map.end())
            {
                nodeId = fixed_node_name2id_map.at(netPin.node_name);
                pin2nodeType_map.emplace_back(fixed_node2fence_region_map[nodeId]);
                pin_offset_x.emplace_back(0.5*fixed_node_size_x[nodeId]);
                pin_offset_y.emplace_back(0.5*fixed_node_size_y[nodeId]);
                nodeType = fixed_node_types[nodeId];
                nodeId += num_movable_nodes;

                if (m_numCCs > 0)
                {
                    org_nodeId = fixed_node_name2id_map.at(netPin.node_name);
                    org_pin2nodeType_map.emplace_back(fixed_node2fence_region_map[org_nodeId]);
                    org_pin_offset_x.emplace_back(0.5*fixed_node_size_x[org_nodeId]);
                    org_pin_offset_y.emplace_back(0.5*fixed_node_size_y[org_nodeId]);
                    org_nodeType = fixed_node_types[org_nodeId];
                    org_nodeId += org_num_movable_nodes;
                }

            } else
            {
                dreamplacePrint(kERROR, "Net %s connects to instance %s pin %s. However instance %s is not specified in .nodes file. FIX\n",
                        n.net_name.c_str(), netPin.node_name.c_str(), netPin.pin_name.c_str(), netPin.node_name.c_str());
            }
        }

        std::string pType("");

        ////DBG
        //std::cout << " Check for nodeType " <<  nodeType << " in lib" << std::endl;
        ////DBG

        LibCell const& lCell = m_vLibCell.at(m_LibCellName2Index.at(nodeType));
        int pinTypeId(lCell.pinType(netPin.pin_name));

        if (pinTypeId == -1)
        {
            dreamplacePrint(kWARN, "Net %s connects to instance %s pin %s. However pin %s is not listed in .lib as a valid pin for instance type %s. FIX\n",
                    n.net_name.c_str(), netPin.node_name.c_str(), netPin.pin_name.c_str(), netPin.pin_name.c_str(), nodeType.c_str());
        }

        switch(pinTypeId)
        {
            case 2: //CLK
                {
                    pType = "CK";
                    break;
                }
            case 3: //CTRL
                {
                    if (netPin.pin_name.find("CE") != std::string::npos || 
                            netPin.pin_name.find("devclrn") != std::string::npos)
                        //if (netPin.pin_name == "CE" || netPin.pin_name == "devclrn" ||
                        //netPin.pin_name == "devclrn0")
                    {
                        pType = "CE";
                    } else if (netPin.pin_name == "R" || netPin.pin_name == "S" ||
                            netPin.pin_name.find("sclr") != std::string::npos)
                        //netPin.pin_name == "sclr" || netPin.pin_name == "sclr0")
                    {
                        pType = "SR";
                        pinTypeId = 4;
                        // else if (netPin.pin_name.find("prn") != std::string::npos )
                    } else if (netPin.pin_name.find("prn") != std::string::npos)
                        // else if (netPin.pin_name == "prn" ||
                        //            netPin.pin_name == "prn0")
                    {
                        pType = "PR";
                        pinTypeId = 5;
                    } else if (netPin.pin_name.find("aload") != std::string::npos)
                        // else if (netPin.pin_name == "aload" ||
                        //           netPin.pin_name == "aload0")
                    {
                        pType = "AL";
                        pinTypeId = 6;
                    } else if (netPin.pin_name.find("sload") != std::string::npos)
                        // else if (netPin.pin_name == "sload" ||
                        //           netPin.pin_name == "sload0")
                    {
                        pType = "SL";
                        pinTypeId = 7;
                    } else if (netPin.pin_name.find("devpor") != std::string::npos)
                        // else if (netPin.pin_name == "devpor" ||
                        //           netPin.pin_name == "devpor0")
                    {
                        pType = "DP";
                        pinTypeId = 8;
                    } else if (netPin.pin_name.find("clrn") != std::string::npos)
                        // else if (netPin.pin_name == "clrn" ||
                        //           netPin.pin_name == "clrn0")
                    {
                        pType = "DC";
                        pinTypeId = 9;
                    } 
                    break;
                }
            default:
                {
                    break;
                }
        }

        ////DBG
        //std::cout << " pType " <<  pType << " and pinTypeId " << pinTypeId << std::endl;
        ////DBG

        pin_types.emplace_back(pType);
        pin_typeIds.emplace_back(pinTypeId);
        ++node2pincount_map[nodeId];
        pin2node_map.emplace_back(nodeId);
        node2pin_map[nodeId].emplace_back(pinId);

        if (m_numCCs > 0)
        {
            ++org_node2pincount_map[org_nodeId];
            org_pin2node_map.emplace_back(org_nodeId);
            org_node2pin_map[org_nodeId].emplace_back(pinId);
        }


        //node2outpin info is mainly required for LUT/FF LG
        // cout (30) and shareout (40) are not considered
        if (pinTypeId == 0 || pinTypeId == 20) //Output pin
        {
            if (node2outpinCount[nodeId] < 4)
            {
                int n2oIdx = nodeId*4 + node2outpinCount[nodeId];
                node2outpinIdx_map[n2oIdx] = pinId;
                ++node2outpinCount[nodeId];
            }

            if (m_numCCs > 0 && org_node2outpinCount[org_nodeId] < 4)
            {
                int n2oIdx = org_nodeId*4 + org_node2outpinCount[org_nodeId];
                org_node2outpinIdx_map[n2oIdx] = pinId;
                ++org_node2outpinCount[org_nodeId];
            }
        }

        netPins.emplace_back(pinId);
        flat_net2pin_map.emplace_back(pinId);
    }
    flat_net2pin_start_map.emplace_back(flat_net2pin_map.size());
    net2pin_map.emplace_back(netPins);

    ////DBG
    //std::cout << net_names.size() << " added net: " << n.net_name << " with " << n.vNetPin.size() << std::endl;
    ////DBG
}

void PlaceDB::add_bookshelf_carry(BookshelfParser::CarryChain const& carry_chain) 
{
    ////DBG
    //std::cout << "add carry chain: " << carry_chain.name << " containing " << carry_chain.elCount << " nodes " << std::endl;
    ////DBG

    if (cc_element_count.size() == 0)
    {
        org_flat_cc2node_start_map.emplace_back(0);
    }

    for (unsigned i = 0; i < carry_chain.elements.size(); ++i)
    {
        index_type nodeId = node_names.size()+1;

        string2index_map_type::iterator found = node_name2id_map.find(carry_chain.elements[i]);
        if (found == node_name2id_map.end())
        {
            std::cout << "Carry Chain node " << carry_chain.elements[i] << " is not part of design.nodes - CHECK" << std::endl;
            continue;
        }

        nodeId = node_name2id_map[carry_chain.elements[i]];
        org_node2ccIndex_map[nodeId] = carry_chain.elements.size()-i-1;
        org_flat_cc2node_map.emplace_back(nodeId);
        node2ccId_map[nodeId] = cc_element_count.size();
        is_cc_node[nodeId] = 1;

        ////DBG
        //    std::cout << "Carry chain element " << i << " " << carry_chain.elements[i] << " has nodeId: " << nodeId
        //        << ", ccId: " << node2ccId_map[nodeId] << " and cc index: " << org_node2ccIndex_map[nodeId] << std::endl;
        ////DBG
    }
    org_flat_cc2node_start_map.emplace_back(org_flat_cc2node_map.size());
    cc_element_count.emplace_back(carry_chain.elCount);
    ++m_numCCs;

    ////Initialize 2D vector
    //std::vector<std::pair<int, int> > temp;
    //temp_input_pin_info.emplace_back(temp);
    //temp_output_pin_info.emplace_back(temp);
    ////DBG
    //std::cout << "Added carry chain " << m_numCCs << " with " << cc_element_count.back() << " nodes" << std::endl;
    ////DBG
}

void PlaceDB::resize_sites(int xSize, int ySize)
{
    m_dieArea.set(0, 0, xSize, ySize);
    m_siteDB.resize(xSize, std::vector<index_type>(ySize, 0));
    initSiteMapValUpd = true;
}

void PlaceDB::site_info_update(int x, int y, std::string const& name)
{
    if (initSiteMapValUpd)
    {
        int xh = m_dieArea.xh();
        int yh = m_dieArea.yh();
        m_dieArea.set(x, y, xh, yh);
        initSiteMapValUpd = false;
    }
    int siteId = siteType2IndexMap[name];
    m_siteDB[x][y] = siteId;
}

void PlaceDB::resize_clk_regions(int xReg, int yReg)
{
    m_clkRegX = xReg;
    m_clkRegY = yReg;
}

void PlaceDB::add_clk_region(std::string const& name, int xl, int yl, int xh, int yh, int xm, int ym)
{
    clk_region temp;
    temp.xl = xl;
    temp.yl = yl;
    temp.xh = xh;
    temp.yh = yh;
    temp.xm = xm;
    temp.ym = ym;
    m_clkRegionDB.emplace_back(temp);
    m_clkRegions.emplace_back(name);
}

void PlaceDB::add_lib_cell(std::string const& name)
{
  string2index_map_type::iterator found = m_LibCellName2Index.find(name);
  if (found == m_LibCellName2Index.end())  // Ignore if already exists
  {
    m_vLibCell.push_back(LibCell(name));
    LibCell& lCell = m_vLibCell.back();
    //lCell.setName(name);
    lCell.setId(m_vLibCell.size() - 1);
    std::pair<string2index_map_type::iterator, bool> insertRet =
        m_LibCellName2Index.insert(std::make_pair(lCell.name(), lCell.id()));
    dreamplaceAssertMsg(insertRet.second, "failed to insert libCell (%s, %d)",
                        lCell.name().c_str(), lCell.id());

    m_numLibCell = m_vLibCell.size();  // update number of libCells 
  }
  m_libCellTemp = name;
}

void PlaceDB::add_input_pin(std::string& pName)
{
    string2index_map_type::iterator found = m_LibCellName2Index.find(m_libCellTemp);

    if (found != m_LibCellName2Index.end())  
    {
        LibCell& lCell = m_vLibCell.at(m_LibCellName2Index.at(m_libCellTemp));
        lCell.addInputPin(pName);
    } else
    {
        dreamplacePrint(kWARN, "libCell not found in .lib file: %s\n",
                m_libCellTemp.c_str());
    }
}

void PlaceDB::add_input_add_pin(std::string& pName)
{
    string2index_map_type::iterator found = m_LibCellName2Index.find(m_libCellTemp);

    if (found != m_LibCellName2Index.end())  
    {
        LibCell& lCell = m_vLibCell.at(m_LibCellName2Index.at(m_libCellTemp));
        lCell.addInputAddPin(pName);
    } else
    {
        dreamplacePrint(kWARN, "libCell not found in .lib file: %s\n",
                m_libCellTemp.c_str());
    }
}

void PlaceDB::add_output_pin(std::string& pName)
{
    string2index_map_type::iterator found = m_LibCellName2Index.find(m_libCellTemp);

    if (found != m_LibCellName2Index.end())  
    {
        LibCell& lCell = m_vLibCell.at(m_LibCellName2Index.at(m_libCellTemp));
        lCell.addOutputPin(pName);
    } else
    {
        dreamplacePrint(kWARN, "libCell not found in .lib file: %s\n",
                m_libCellTemp.c_str());
    }
}

void PlaceDB::add_output_add_pin(std::string& pName)
{
    string2index_map_type::iterator found = m_LibCellName2Index.find(m_libCellTemp);

    if (found != m_LibCellName2Index.end())  
    {
        LibCell& lCell = m_vLibCell.at(m_LibCellName2Index.at(m_libCellTemp));
        lCell.addOutputAddPin(pName);
    } else
    {
        dreamplacePrint(kWARN, "libCell not found in .lib file: %s\n",
                m_libCellTemp.c_str());
    }
}

void PlaceDB::add_clk_pin(std::string& pName)
{
    string2index_map_type::iterator found = m_LibCellName2Index.find(m_libCellTemp);

    if (found != m_LibCellName2Index.end())  
    {
        LibCell& lCell = m_vLibCell.at(m_LibCellName2Index.at(m_libCellTemp));
        lCell.addClkPin(pName);
    } else
    {
        dreamplacePrint(kWARN, "libCell not found in .lib file: %s\n",
                m_libCellTemp.c_str());
    }
}

void PlaceDB::add_ctrl_pin(std::string& pName)
{
    string2index_map_type::iterator found = m_LibCellName2Index.find(m_libCellTemp);

    if (found != m_LibCellName2Index.end())  
    {
        LibCell& lCell = m_vLibCell.at(m_LibCellName2Index.at(m_libCellTemp));
        lCell.addCtrlPin(pName);
    } else
    {
        dreamplacePrint(kWARN, "libCell not found in .lib file: %s\n",
                m_libCellTemp.c_str());
    }
}

void PlaceDB::set_bookshelf_node_pos(std::string const& name, double x, double y, int z)
{
    string2index_map_type::iterator found = fixed_node_name2id_map.find(name);
    //bool fixed(true);

    if (found != fixed_node_name2id_map.end())
    {
        fixed_node_x.at(fixed_node_name2id_map.at(name)) = x;
        fixed_node_y.at(fixed_node_name2id_map.at(name)) = y;
        fixed_node_z.at(fixed_node_name2id_map.at(name)) = z;
    } else
    {
        //string2index_map_type::iterator fnd = mov_node_name2id_map.find(name);
        node_x.at(node_name2id_map.at(name)) = x;
        node_y.at(node_name2id_map.at(name)) = y;
        node_z.at(node_name2id_map.at(name)) = z;
    }

}

void PlaceDB::add_site(BookshelfParser::Site const& st)
{
    siteType2IndexMap.insert(std::make_pair(st.name, siteTypes.size()+1));
    siteTypes.emplace_back(st.name);

    std::vector<std::string> temp;
    for (unsigned i = 0; i < st.rsrcs.size(); ++i) 
    {
        std::string rsrc = st.rsrcs[i].first;
        temp.emplace_back(rsrc);
        siteRsrcCountMap.insert(std::make_pair(rsrc, st.rsrcs[i].second));
        rsrc2SiteMap.insert(std::make_pair(rsrc, st.name));
    }
    siteResources.emplace_back(temp);
    temp.clear();
}

void PlaceDB::add_rsrc(BookshelfParser::Rsrc const& rsrc)
{
    if (rsrc.rsrcCells.size() > 0)
    {
        //std::cout << "add resource: " << rsrc.name  << " with " << rsrc.rsrcCells.size() << " cells " << std::endl;
        rsrcType2IndexMap.insert(std::make_pair(rsrc.name, rsrcTypes.size()));
        rsrcTypes.emplace_back(rsrc.name);
        for (unsigned i = 0; i < rsrc.rsrcCells.size(); ++i) 
        {
            inst2RsrcMap.insert(std::make_pair(rsrc.rsrcCells[i], rsrc.name));
            rsrcInstType2IndexMap.insert(std::make_pair(rsrc.rsrcCells[i], rsrcInstTypes.size()));
            //std::cout << "rsrc Inst: " << rsrc.rsrcCells[i] << " assigned to id: " << rsrcInstType2IndexMap[rsrc.rsrcCells[i]] << std::endl;
            rsrcInstTypes.emplace_back(rsrc.rsrcCells[i]);
        }
        rsrcInsts.emplace_back(rsrc.rsrcCells);

        if (rsrc.name.find("FF") != std::string::npos ||
                rsrc.name.find("dffeas") != std::string::npos)
        {
            ffId = rsrcTypes.size()-1;
        }
        else if (rsrc.name.find("LUT") != std::string::npos ||
                rsrc.name.find("lcell_comb") != std::string::npos)
        {
            lutId = rsrcTypes.size()-1;
        }
        else if (rsrc.name.find("IO") != std::string::npos ||
                rsrc.name.find("io") != std::string::npos)
        {
            ioId = rsrcTypes.size()-1;
        }
        else if (rsrc.name.find("PLL") != std::string::npos ||
                rsrc.name.find("pll") != std::string::npos)
        {
            pllId = rsrcTypes.size()-1;
        }
    }
}

void PlaceDB::set_site_per_column(int val)
{
    sitePerColumn = val;
}

void PlaceDB::set_site_dimensions(std::string const& sName, double w, double h)
{
    if (siteWidth.size() == 0 || siteHeight.size() == 0 || rsrcInstWidth.size() == 0 || rsrcInstHeight.size() == 0)
    {
        siteWidth.resize(siteTypes.size()+1, 1.0);
        siteHeight.resize(siteTypes.size()+1, 1.0);
        rsrcInstWidth.resize(rsrcInstTypes.size(), 1.0);
        rsrcInstHeight.resize(rsrcInstTypes.size(), 1.0);
    }

    unsigned siteId = siteType2IndexMap[sName];
    siteWidth[siteId] = w;
    siteHeight[siteId] = h;

    unsigned rsrcId = rsrcType2IndexMap[siteResources[siteId-1][0]];
    for (unsigned srId = 0; srId < rsrcInsts[rsrcId].size(); ++srId)
    {
        std::string rsrcInst = rsrcInsts[rsrcId][srId];
        rsrcInstWidth[rsrcInstType2IndexMap[rsrcInst]] = w;
        rsrcInstHeight[rsrcInstType2IndexMap[rsrcInst]] = h;
    }
}

void PlaceDB::set_slice_element(std::string const& sName, int cnt)
{
    sliceElements.emplace_back(std::make_pair(sName, cnt));
}

void PlaceDB::set_cell_dimensions(std::string const& cName, double w, double h)
{
    rsrcInstWidth[rsrcInstType2IndexMap[cName]] = w;
    rsrcInstHeight[rsrcInstType2IndexMap[cName]] = h;
}

void PlaceDB::set_lut_max_shared(int cnt)
{
    lutMaxShared = cnt;
}

void PlaceDB::set_lut_type_in_sliceUnit(int cnt)
{
    lutTypeInSliceUnit = cnt;
}

void PlaceDB::set_lut_fractureability(BookshelfParser::LUTFract const& lutFract)
{
    if (lutFractures.size() == 0)
    {
        lutFractures.resize(rsrcInsts[lutId].size());
    }

    int fId = get_last_digit_from_string(lutFract.name)-1;

    if (fId >= 0)
    {
        for (unsigned i = 0; i < lutFract.fractCells.size(); ++i)
        {
            lutFractures[fId].emplace_back(get_last_digit_from_string(lutFract.fractCells[i])-1);
        }
    }
}

void PlaceDB::set_sliceFF_ctrl_mode(std::string const& mode)
{
    sliceFF_ctrl_mode = mode;
}

void PlaceDB::set_sliceFF_ctrl(std::string const& sName, int cnt)
{
    sliceFFCtrl.emplace_back(std::make_pair(sName, cnt));
}

void PlaceDB::set_sliceUnitFF_ctrl(std::string const& sName, int cnt)
{
    sliceFFUnitCtrl.emplace_back(std::make_pair(sName, cnt));
}

void PlaceDB::set_FFCtrl_type(std::string const& type)
{
    ////DBG
    //std::cout << "set ff ctrl type as " << type << std::endl;
    ////DBG
    ffCtrlType = type;
}

void PlaceDB::set_wl_weight_x(double wt)
{
    wlXWeight = wt;
}

void PlaceDB::set_wl_weight_y(double wt)
{
    wlYWeight = wt;
}

void PlaceDB::set_pin_route_cap(int pinCap)
{
    pinRouteCap = pinCap;
}

void PlaceDB::set_route_cap_H(int hRouteCap)
{
    routeCapH = hRouteCap;
}

void PlaceDB::set_route_cap_V(int vRouteCap)
{
    routeCapV = vRouteCap;
    //std::cout << "Vertical Routing Capacity = " << vRouteCap << std::endl;
}

void PlaceDB::set_siteOut(BookshelfParser::SiteOut const& st)
{
    if (siteOutCoordinate.size() == 0)
    {
        siteOutCoordinate.resize(siteTypes.size()+1, "");
        siteOutValue.resize(siteTypes.size()+1, 0);
    }

    for (unsigned i = 0; i < st.siteTypes.size(); ++i)
    {
        index_type siteId = siteType2IndexMap[st.siteTypes[i]];
        //std::cout << "Assign siteType : " << st.siteTypes[i] << " with siteId: " << siteId << " as " << st.coordinate << " " << st.value << std::endl;
        siteOutCoordinate[siteId] = st.coordinate;
        siteOutValue[siteId] = st.value;
    }

}

void PlaceDB::set_bookshelf_design(std::string& name) {
  m_designName.swap(name);
}

void PlaceDB::bookshelf_end() {
    //  // parsing bookshelf format finishes
    //  // now it is necessary to init data that is not set in bookshelf
    //Flatten node2pin
    flat_node2pin_map.reserve(pin_names.size());
    flat_node2pin_start_map.emplace_back(0);
    for (const auto& sub : node2pin_map)
    {
        flat_node2pin_map.insert(flat_node2pin_map.end(), sub.begin(), sub.end());
        flat_node2pin_start_map.emplace_back(flat_node2pin_map.size());
    }
    
    org_fixed_node_name2id_map = fixed_node_name2id_map;
    for (auto& el : fixed_node_name2id_map)
    {
        el.second += num_movable_nodes;
    }

    node_name2id_map.insert(fixed_node_name2id_map.begin(), fixed_node_name2id_map.end());
    lut_type.insert(lut_type.end(), fixed_lut_type.begin(), fixed_lut_type.end());
    cluster_lut_type.insert(cluster_lut_type.end(), fixed_cluster_lut_type.begin(), fixed_cluster_lut_type.end());
    node_size_x.insert(node_size_x.end(), fixed_node_size_x.begin(), fixed_node_size_x.end());
    node_size_y.insert(node_size_y.end(), fixed_node_size_y.begin(), fixed_node_size_y.end());
    node_names.insert(node_names.end(), fixed_node_names.begin(), fixed_node_names.end());
    node_types.insert(node_types.end(), fixed_node_types.begin(), fixed_node_types.end());
    node_x.insert(node_x.end(), fixed_node_x.begin(), fixed_node_x.end());
    node_y.insert(node_y.end(), fixed_node_y.begin(), fixed_node_y.end());
    node_z.insert(node_z.end(), fixed_node_z.begin(), fixed_node_z.end());
    node2fence_region_map.insert(node2fence_region_map.end(), fixed_node2fence_region_map.begin(), fixed_node2fence_region_map.end());

    if (m_numCCs > 0)
    {
        org_flat_node2pin_map.reserve(pin_names.size());
        org_flat_node2pin_start_map.emplace_back(0);
        for (const auto& sub : org_node2pin_map)
        {
            org_flat_node2pin_map.insert(org_flat_node2pin_map.end(), sub.begin(), sub.end());
            org_flat_node2pin_start_map.emplace_back(org_flat_node2pin_map.size());
        }

        for (auto& el : org_fixed_node_name2id_map)
        {
            el.second += org_num_movable_nodes;
        }

        org_node_name2id_map.insert(org_fixed_node_name2id_map.begin(), org_fixed_node_name2id_map.end());
        org_lut_type.insert(org_lut_type.end(), fixed_lut_type.begin(), fixed_lut_type.end());
        org_node_size_x.insert(org_node_size_x.end(), fixed_node_size_x.begin(), fixed_node_size_x.end());
        org_node_size_y.insert(org_node_size_y.end(), fixed_node_size_y.begin(), fixed_node_size_y.end());
        org_node_names.insert(org_node_names.end(), fixed_node_names.begin(), fixed_node_names.end());
        org_node_types.insert(org_node_types.end(), fixed_node_types.begin(), fixed_node_types.end());
        org_node2fence_region_map.insert(org_node2fence_region_map.end(), fixed_node2fence_region_map.begin(), fixed_node2fence_region_map.end());
        org_node_x.insert(org_node_x.end(), fixed_node_x.begin(), fixed_node_x.end());
        org_node_y.insert(org_node_y.end(), fixed_node_y.begin(), fixed_node_y.end());
        org_node_z.insert(org_node_z.end(), fixed_node_z.begin(), fixed_node_z.end());

        dreamplacePrint(kINFO, "Design contains %d carry chains\n", m_numCCs);

        //Generate required info on input/output pins of each carry chain node

        ////DBG
        ////Verify info
        //std::cout << "General info: ";
        //index_type ccnodeId = cc2nodeId_map[0];
        //std::cout << " consider node " << ccnodeId << " " << node_names[ccnodeId] << std::endl;
        //for (index_type idx = flat_node2pin_start_map[ccnodeId];
        //     idx < flat_node2pin_start_map[ccnodeId+1]; ++idx)
        //{
        //    index_type pinId = flat_node2pin_map[idx];
        //    if (pin_typeIds[pinId] == 1)
        //    {
        //        std::cout << "Input Pin " << pin_names[pinId] << " is of type " << pin_typeIds[pinId] << std::endl; 
        //    } else if (pin_typeIds[pinId] == 0 || pin_typeIds[pinId] == 20) //Output pin
        //    {
        //        std::cout << "Output Pin " << pin_names[pinId] << " is of type " << pin_typeIds[pinId] << std::endl; 
        //    }
        //}

        //std::cout << "Input pins of first cc node with offset: " << std::endl;
        //for (auto el : temp_input_pin_info[0])
        //{
        //    std::cout << el.second << " Input Pin " << pin_names[el.first] << " is of type " << pin_typeIds[el.first] << std::endl; 
        //}
        //std::cout << "Output pins of first cc node with offset: " << std::endl;
        //for (auto el : temp_output_pin_info[0])
        //{
        //    std::cout << el.second << " Output Pin " << pin_names[el.first] << " is of type " << pin_typeIds[el.first] << std::endl; 
        //}
        ////DBG

        //overall_cc_input_pin_start_map.emplace_back(0);
        //overall_cc_output_pin_start_map.emplace_back(0);
        //for (index_type ccIdx = 0; ccIdx < m_numCCs; ++ccIdx)
        //{
        //    ////DBG
        //    //std::cout << "Input pins of first cc node with offset: " << std::endl;
        //    //for (auto el : temp_input_pin_info[ccIdx])
        //    //{
        //    //    std::cout << el.second << " Input Pin " << pin_names[el.first] << " " << el.first << " is of type " << pin_typeIds[el.first] << std::endl; 
        //    //}
        //    ////DBG

        //    std::sort(temp_input_pin_info[ccIdx].begin(), temp_input_pin_info[ccIdx].end(),
        //              [&](const auto &a, const auto &b){ return a.second < b.second; });

        //    ////DBG
        //    //std::cout << "After sorting Input pins of first cc node with offset: " << std::endl;
        //    //for (auto el : temp_input_pin_info[ccIdx])
        //    //{
        //    //    std::cout << el.second << " Input Pin " << pin_names[el.first] << " " << el.first << " is of type " << pin_typeIds[el.first] << std::endl; 
        //    //}
        //    ////DBG

        //    int currEl = -1;
        //    flat_cc_input_pin_start_map.emplace_back(flat_cc_input_pins_map.size());
        //    for (auto el : temp_input_pin_info[ccIdx])
        //    {
        //        if (currEl == -1)
        //        {
        //            currEl = el.second;
        //        } else if (currEl != el.second)
        //        {
        //            flat_cc_input_pin_start_map.emplace_back(flat_cc_input_pins_map.size());
        //            currEl = el.second;
        //        }
        //        flat_cc_input_pins_map.emplace_back(el.first);
        //    }
        //    flat_cc_input_pin_start_map.emplace_back(flat_cc_input_pins_map.size());
        //    overall_cc_input_pin_start_map.emplace_back(flat_cc_input_pin_start_map.size());

        //    ////DBG
        //    //std::cout << "Contents of flat_cc_input_pins_map: " << std::endl;
        //    //for (auto el : flat_cc_input_pins_map)
        //    //{
        //    //    std::cout << el << " ";
        //    //}
        //    //std::cout << std::endl; 
        //    //std::cout << "Contents of flat_cc_input_pin_start_map: " << std::endl;
        //    //for (auto el : flat_cc_input_pin_start_map)
        //    //{
        //    //    std::cout << el << " ";
        //    //}
        //    //std::cout << std::endl; 
        //    //std::cout << "Contents of overall_cc_input_pin_start_map: " << std::endl;
        //    //for (auto el : overall_cc_input_pin_start_map)
        //    //{
        //    //    std::cout << el << " ";
        //    //}
        //    //std::cout << std::endl; 
        //    ////DBG

        //    std::sort(temp_output_pin_info[ccIdx].begin(), temp_output_pin_info[ccIdx].end(),
        //             [&](const auto &a, const auto &b){ return a.second < b.second; });
        //    currEl = -1;
        //    flat_cc_output_pin_start_map.emplace_back(flat_cc_output_pins_map.size());
        //    for (auto el : temp_output_pin_info[ccIdx])
        //    {
        //        if (currEl == -1)
        //        {
        //            currEl = el.second;
        //        } else if (currEl != el.second)
        //        {
        //            flat_cc_output_pin_start_map.emplace_back(flat_cc_output_pins_map.size());
        //            currEl = el.second;
        //        }
        //        flat_cc_output_pins_map.emplace_back(el.first);
        //    }
        //    flat_cc_output_pin_start_map.emplace_back(flat_cc_output_pins_map.size());
        //    overall_cc_output_pin_start_map.emplace_back(flat_cc_output_pin_start_map.size());
        //}
    }
}

bool PlaceDB::write(std::string const& filename) const {

  return write(filename, NULL, NULL);
}

bool PlaceDB::write(std::string const& filename,
                    float const* x,
                    float const* y,
                    PlaceDB::index_type const* z) const {
  return BookShelfWriter(*this).write(filename, x, y, z);
}

DREAMPLACE_END_NAMESPACE


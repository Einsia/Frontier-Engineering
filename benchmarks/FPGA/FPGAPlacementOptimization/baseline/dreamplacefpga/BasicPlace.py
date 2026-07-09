##
# @file   BasicPlace.py
# @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Sep 2020
# @brief  Base placement class
#

import os
import sys
import time
import gzip
if sys.version_info[0] < 3:
    import cPickle as pickle
else:
    import _pickle as pickle
import re
import numpy as np
import logging
import torch
import torch.nn as nn
import dreamplacefpga.ops.move_boundary.move_boundary as move_boundary
import dreamplacefpga.ops.hpwl.hpwl as hpwl
import dreamplacefpga.ops.electric_potential.electric_overflow as electric_overflow
import dreamplacefpga.ops.draw_place.draw_place as draw_place
import dreamplacefpga.ops.pin_pos.pin_pos as pin_pos
import dreamplacefpga.ops.precondWL.precondWL as precondWL
import dreamplacefpga.ops.demandMap.demandMap as demandMap
import dreamplacefpga.ops.sortNode2Pin.sortNode2Pin as sortNode2Pin
import dreamplacefpga.ops.lut_ff_legalization.lut_ff_legalization as lut_ff_legalization
import pdb

datatypes = {
        'float32' : torch.float32, 
        'float64' : torch.float64
        }

class PlaceDataCollectionFPGA(object):
    """
    @brief A wraper for all data tensors on device for building ops 
    """
    def __init__(self, pos, params, placedb, device):
        """
        @brief initialization 
        @param pos locations of cells 
        @param params parameters 
        @param placedb placement database 
        @param device cpu or cuda 
        """
        self.device = device
        self.dtype = datatypes[params.dtype]
        torch.set_num_threads(params.num_threads)
        # position should be parameter
        self.pos = pos

        with torch.no_grad():
            # other tensors required to build ops

            self.node_size_x = torch.from_numpy(placedb.node_size_x).to(device)
            self.node_size_y = torch.from_numpy(placedb.node_size_y).to(device)
            self.resource_size_x = torch.from_numpy(placedb.resource_size_x).to(device)
            self.resource_size_y = torch.from_numpy(placedb.resource_size_y).to(device)
            self.node_x = torch.from_numpy(placedb.node_x).to(device)
            self.node_y = torch.from_numpy(placedb.node_y).to(device)
            self.node_z = torch.from_numpy(placedb.node_z.astype(np.int32)).to(device)
            self.site_type_map = torch.from_numpy(placedb.site_type_map.astype(np.int32)).to(device)
            self.lg_siteXYs = torch.from_numpy(placedb.lg_siteXYs).to(device)

            if params.routability_opt_flag:
                self.original_node_size_x = self.node_size_x.clone()
                self.original_node_size_y = self.node_size_y.clone()

            self.pin_offset_x = torch.from_numpy(placedb.pin_offset_x).to(device)
            self.pin_offset_y = torch.from_numpy(placedb.pin_offset_y).to(device)
            self.lg_pin_offset_x = torch.from_numpy(placedb.lg_pin_offset_x).to(device)
            self.lg_pin_offset_y = torch.from_numpy(placedb.lg_pin_offset_y).to(device)

            # original pin offset for legalization, since they will be adjusted in global placement
            if params.routability_opt_flag:
                self.original_pin_offset_x = self.pin_offset_x.clone()
                self.original_pin_offset_y = self.pin_offset_y.clone()

            self.node_areas = self.node_size_x * self.node_size_y
            self.movable_macro_mask = None

            self.pin2node_map = torch.from_numpy(placedb.pin2node_map).to(device)
            self.flat_node2pin_map = torch.from_numpy(placedb.flat_node2pin_map).to(device)
            self.flat_node2pin_start_map = torch.from_numpy(placedb.flat_node2pin_start_map).to(device)
            self.node2outpinIdx_map = torch.from_numpy(placedb.node2outpinIdx_map).to(device)
            self.node2pincount_map = torch.from_numpy(placedb.node2pincount_map).to(device)
            self.net2pincount_map = torch.from_numpy(placedb.net2pincount_map).to(device)

            # number of pins for each cell
            self.pin_weights = (self.flat_node2pin_start_map[1:] -
                                self.flat_node2pin_start_map[:-1]).to(
                                    self.dtype)
            ## Resource type masks
            self.flop_mask = torch.from_numpy(placedb.flop_mask).to(device)
            self.lut_mask = torch.from_numpy(placedb.lut_mask).to(device)
            if placedb.sDSPIdx != -1:
                self.dsp_mask = torch.from_numpy(placedb.dsp_mask).to(device)
            if placedb.sBRAMIdx != -1 or placedb.sM9KIdx != -1:
                self.ram0_mask = torch.from_numpy(placedb.ram0_mask).to(device)
            if placedb.sM144KIdx != -1:
                self.ram1_mask = torch.from_numpy(placedb.ram1_mask).to(device)
            self.flop_lut_mask = self.flop_mask | self.lut_mask

            if placedb.sBRAMIdx == -1:
                self.dsp_ram_mask = self.dsp_mask | self.ram0_mask | self.ram1_mask
            else:
                self.dsp_ram_mask = self.dsp_mask | self.ram0_mask

            self.io_mask = torch.from_numpy(placedb.io_mask).to(device)
            self.fixed_rsrcIds = torch.from_numpy(placedb.fixed_rsrcIds).to(dtype=torch.int32,device=device)

            #TODO - For Stratix-IV: mlab is treated as lut type as sites for MLAB/LAB are not distinguished
            self.is_mlab_node = torch.from_numpy(placedb.is_mlab_node).to(device)

            #LUT type list
            self.lut_type = torch.from_numpy(placedb.lut_type).to(dtype=torch.int32,device=device)
            self.cluster_lut_type = torch.from_numpy(placedb.cluster_lut_type).to(dtype=torch.int32,device=device)
            self.pin_typeIds = torch.from_numpy(placedb.pin_typeIds).to(dtype=torch.int32,device=device)

            #FF control sets
            self.flop_ctrlSets = torch.from_numpy(placedb.flat_ctrlSets).to(dtype=torch.int32,device=device)
            #FF to ctrlset ID
            self.flop2ctrlSetId_map = torch.from_numpy(placedb.flop2ctrlSetId_map).to(dtype=torch.int32,device=device)
            #Spiral accessor for legalization
            self.spiral_accessor = torch.from_numpy(placedb.spiral_accessor).to(dtype=torch.int32,device=device)
            #Resource type indexing
            self.flop_indices = torch.from_numpy(placedb.flop_indices).to(dtype=torch.int32,device=device)
            self.lut_indices = torch.nonzero(self.lut_mask, as_tuple=True)[0].to(dtype=torch.int32)
            self.flop_lut_indices = torch.nonzero(self.flop_lut_mask, as_tuple=True)[0].to(dtype=torch.int32)
            self.dsp_ram_indices = torch.nonzero(self.dsp_ram_mask, as_tuple=True)[0].to(dtype=torch.int32)
            self.pin_weights[self.flop_mask] = params.ffPinWeight
            self.unit_pin_capacity = torch.empty(1, dtype=self.dtype, device=device)
            self.unit_pin_capacity.data.fill_(params.unit_pin_capacity)

            # routing information
            # project initial routing utilization map to one layer
            self.initial_horizontal_utilization_map = None
            self.initial_vertical_utilization_map = None
            if params.routability_opt_flag and placedb.initial_horizontal_demand_map is not None:
                self.initial_horizontal_utilization_map = torch.from_numpy(
                    placedb.initial_horizontal_demand_map).to(device).div_(
                        placedb.routing_grid_size_y *
                        placedb.unit_horizontal_capacity)
                self.initial_vertical_utilization_map = torch.from_numpy(
                    placedb.initial_vertical_demand_map).to(device).div_(
                        placedb.routing_grid_size_x *
                        placedb.unit_vertical_capacity)

            self.pin2net_map = torch.from_numpy(placedb.pin2net_map.astype(np.int32)).to(device)
            self.flat_net2pin_map = torch.from_numpy(placedb.flat_net2pin_map).to(device)
            self.flat_net2pin_start_map = torch.from_numpy(placedb.flat_net2pin_start_map).to(device)
            if np.amin(placedb.net_weights) == np.amax(placedb.net_weights):  # empty tensor
                logging.warning("net weights are all the same, ignored")
                #self.net_weights = torch.Tensor().to(device)
            self.net_weights = torch.from_numpy(placedb.net_weights).to(device)

            # regions
            self.region_boxes = [torch.tensor(region).to(device) for region in placedb.region_boxes]
            self.flat_region_boxes = torch.from_numpy(
                placedb.flat_region_boxes).to(device)
            self.flat_region_boxes_start = torch.from_numpy(
                placedb.flat_region_boxes_start).to(device)
            self.node2fence_region_map = torch.from_numpy(placedb.node2fence_region_map).to(device)

            self.num_nodes = torch.tensor(placedb.num_nodes, dtype=torch.int32, device=device)
            self.num_movable_nodes = torch.tensor(placedb.num_movable_nodes, dtype=torch.int32, device=device)
            self.num_filler_nodes = torch.tensor(placedb.num_filler_nodes, dtype=torch.int32, device=device)
            self.num_physical_nodes = torch.tensor(placedb.num_physical_nodes, dtype=torch.int32, device=device)
            self.filler_start_map = torch.from_numpy(placedb.filler_start_map).to(device)

            ## this is for overflow op
            self.total_movable_node_area_fence_region = torch.from_numpy(placedb.total_movable_node_area_fence_region).to(device)
            ## this is for gamma update
            self.num_movable_nodes_fence_region = torch.from_numpy(placedb.num_movable_nodes_fence_region).to(device)
            ## this is not used yet
            self.num_filler_nodes_fence_region = torch.from_numpy(placedb.num_filler_nodes_fence_region).to(device)

            self.net_mask_all = torch.from_numpy(np.ones(placedb.num_nets,dtype=np.uint8)).to(device)  # all nets included
            net_degrees = np.array([len(net2pin) for net2pin in placedb.net2pin_map])
            net_mask = np.logical_and(2 <= net_degrees,
                net_degrees < params.ignore_net_degree).astype(np.uint8)
            self.net_mask_ignore_large_degrees = torch.from_numpy(net_mask).to(device)  # nets with large degrees are ignored

            # For WL computation
            self.net_bounding_box_min = torch.zeros(placedb.num_nets * 2, dtype=self.dtype, device=self.device)
            self.net_bounding_box_max = torch.zeros_like(self.net_bounding_box_min)

            # avoid computing gradient for fixed macros
            # 1 is for fixed macros - IOs
            self.pin_mask_ignore_fixed_macros = (self.pin2node_map >= placedb.num_movable_nodes)

            # sort nodes by size, return their sorted indices, designed for memory coalesce in electrical force
            movable_size_x = self.node_size_x[:placedb.num_movable_nodes]
            _, self.sorted_node_map = torch.sort(movable_size_x)
            self.sorted_node_map = self.sorted_node_map.to(torch.int32)

            self.targetOverflow = torch.from_numpy(placedb.targetOverflow).to(dtype=self.dtype, device=device)
            self.node_area_adjust_overflow = torch.from_numpy(placedb.node_area_adjust_overflow).to(dtype=self.dtype, device=device)

            #Filler start/end for FF and LUT for resource area update
            self.ff_filler_start = placedb.filler_start_map[placedb.rsrc2compId_map[placedb.rFFIdx]]
            self.ff_filler_end = placedb.filler_start_map[placedb.rsrc2compId_map[placedb.rFFIdx]+1]
            self.lut_filler_start = placedb.filler_start_map[placedb.rsrc2compId_map[placedb.rLUTIdx]]
            self.lut_filler_end = placedb.filler_start_map[placedb.rsrc2compId_map[placedb.rLUTIdx]+1]

            #Carry chain nodes as single entity
            if placedb.num_ccNodes > 0:
                self.org_node_x = torch.from_numpy(placedb.org_node_x).to(device)
                self.org_node_y = torch.from_numpy(placedb.org_node_y).to(device)
                self.org_node_z = torch.from_numpy(placedb.org_node_z.astype(np.int32)).to(device)
                org_flop_lut_mask = torch.from_numpy(placedb.org_lut_flop_mask).to(device)
                self.org_flop_lut_indices = torch.nonzero(org_flop_lut_mask, as_tuple=True)[0].to(dtype=torch.int32)
                self.org_is_mlab_node = torch.from_numpy(placedb.org_is_mlab_node).to(device)
                self.org_flop2ctrlSetId_map = torch.from_numpy(placedb.org_flop2ctrlSetId_map).to(dtype=torch.int32,device=device)
                self.org_flop_ctrlSets = torch.from_numpy(placedb.flat_org_ctrlSets).to(dtype=torch.int32,device=device)
                self.org_pin2node_map = torch.from_numpy(placedb.org_pin2node_map).to(device)
                self.org_flat_node2pin_map = torch.from_numpy(placedb.org_flat_node2pin_map).to(device)
                self.org_flat_node2pin_start_map = torch.from_numpy(placedb.org_flat_node2pin_start_map).to(device)
                self.org_node2outpinIdx_map = torch.from_numpy(placedb.org_node2outpinIdx_map).to(device)
                self.org_node2pincount_map = torch.from_numpy(placedb.org_node2pincount_map).to(device)
                self.org_node2fence_region_map = torch.from_numpy(placedb.org_node2fence_region_map).to(device)
                self.org_lut_type = torch.from_numpy(placedb.org_lut_type).to(dtype=torch.int32,device=device)
                self.org_lg_pin_offset_x = torch.from_numpy(placedb.org_lg_pin_offset_x).to(device)
                self.org_lg_pin_offset_y = torch.from_numpy(placedb.org_lg_pin_offset_y).to(device)
                self.org_node_size_x = torch.from_numpy(placedb.org_node_size_x).to(device)
                self.org_node_size_y = torch.from_numpy(placedb.org_node_size_y).to(device)
                self.org_node_areas = self.org_node_size_x * self.org_node_size_y

class PlaceOpCollectionFPGA(object):
    """
    @brief A wrapper for all ops
    """
    def __init__(self):
        """
        @brief initialization
        """
        self.demandMap_op = None
        self.pin_pos_op = None
        self.move_boundary_op = None
        self.hpwl_op = None
        self.precondwl_op = None
        self.wirelength_op = None
        self.update_gamma_op = None
        self.density_op = None
        self.update_density_weight_op = None
        self.lg_precondition_op = None
        self.noise_op = None
        self.draw_place_op = None
        self.route_utilization_map_op = None
        self.pin_utilization_map_op = None
        self.clustering_compatibility_lut_area_op= None
        self.clustering_compatibility_ff_area_op= None
        self.adjust_node_area_op = None
        self.sort_node2pin_op = None
        self.lut_ff_legalization_op = None

class BasicPlaceFPGA(nn.Module):
    """
    @brief Base placement class. 
    All placement engines should be derived from this class. 
    """
    def __init__(self, params, placedb):
        """
        @brief initialization
        @param params parameter 
        @param placedb placement database 
        """
        torch.manual_seed(params.random_seed)
        super(BasicPlaceFPGA, self).__init__()

        #Assign carry chain net weighting if specified
        if params.cc_net_weight:
            placedb.carry_chain_net_weight = params.cc_net_weight
        else:
            placedb.carry_chain_net_weight = 1.0

        ###################################################
        ##IDENTIFY IF THERE ARE CARRY CHAINS IN THE DESIGN
        ###################################################
        if placedb.num_ccNodes == 0:
            #nodes_with_carry_chain = np.zeros(placedb.num_physical_nodes, dtype=np.int32)
            placedb.carry_chain_driver = np.ones(placedb.num_physical_nodes, dtype=np.int32)
            placedb.carry_chain_driver *= -1
            placedb.carry_chain_sink = np.ones_like(placedb.carry_chain_driver)
            placedb.carry_chain_sink *= -1
            placedb.carry_chain_nets = np.ones(placedb.num_nets, dtype=np.int32)
            placedb.carry_chain_nets *= -1

            lut_indices = np.nonzero(placedb.lut_mask)[0].astype(np.int32)
            #Check for carry chains if cout-cin connections exist
            if 30 in placedb.pin_typeIds and 31 in placedb.pin_typeIds:
                #Obtain carry chain information
                for instId in lut_indices:
                    pinIdBeg = placedb.flat_node2pin_start_map[instId]
                    pinIdEnd = placedb.flat_node2pin_start_map[instId+1]
                    for pinId in range(pinIdBeg, pinIdEnd, 1):
                        outPinId = placedb.flat_node2pin_map[pinId]
                        if placedb.pin_typeIds[outPinId] != 30: continue
                        outNetId = placedb.pin2net_map[outPinId]
                        pinIdxBeg = placedb.flat_net2pin_start_map[outNetId]
                        pinIdxEnd = placedb.flat_net2pin_start_map[outNetId+1]
                        for pinId in range(pinIdxBeg, pinIdxEnd, 1):
                            pinIdx = placedb.flat_net2pin_map[pinId]
                            nodeIdx = placedb.pin2node_map[pinIdx]
                            if placedb.pin_typeIds[pinIdx] == 31 and nodeIdx != instId:
                                placedb.net_weights[outNetId] = placedb.carry_chain_net_weight
                                placedb.carry_chain_nets[outNetId] = placedb.carry_chain_net_weight
                                placedb.carry_chain_sink[instId] = nodeIdx
                                placedb.carry_chain_driver[nodeIdx] = instId
            ccd = placedb.carry_chain_driver > -1
            ccs = placedb.carry_chain_sink > -1
            #placedb.nodes_with_carry_chain=np.logical_or(ccd, ccs)
            #placedb.nodes_cc_start=np.logical_and(~ccd, ccs)
            #placedb.non_root_cc_nodes=np.logical_and(placedb.nodes_with_carry_chain,~placedb.nodes_cc_start)
            #carry_chain_nodeIds = np.where(np.logical_or(ccd, ccs))[0].astype(np.int32)
            #Instance ids that are the start of carry chains
            placedb.carry_chain_start = np.where(np.logical_and(~ccd, ccs))[0].astype(np.int32)
            placedb.num_carry_chains = placedb.carry_chain_start.shape[0]

            ##placedb.node_area = placedb.node_size_x * placedb.node_size_y
            node_cc_id=np.ones(placedb.num_physical_nodes, dtype=np.int32)
            node_cc_id*=-1
            node_cc_id[placedb.carry_chain_start]=np.arange(placedb.num_carry_chains)

            #### PRINT CARRY CHAINS INFO AS DESIGN.CC FILE
            ####Get number of nodes in each carry chain
            #cc_element_count=np.zeros(placedb.num_carry_chains, dtype=np.int32)
            #for el in placedb.carry_chain_start:
            #    ccId=node_cc_id[el]
            #    #Get node info
            #    cc_element_count[ccId]=cc_element_count[ccId]+1
            #    sink_node=placedb.carry_chain_sink[el]
            #    while sink_node > -1:
            #        #Get node info
            #        cc_element_count[ccId]=cc_element_count[ccId]+1
            #        #Next sink
            #        sink_node=placedb.carry_chain_sink[sink_node]
            #### END PRINT CARRY CHAINS INFO AS DESIGN.CC FILE

            flat_cc2node_map = []
            flat_cc2node_start_map = []

            flat_cc2node_start_map.append(0)
            for el in placedb.carry_chain_start:
                ccId=node_cc_id[el]
                #### PRINT CARRY CHAINS INFO AS DESIGN.CC FILE
                #header="carry " + placedb.node_names[el] + " " + str(cc_element_count[ccId])
                #midportion="\t" + placedb.node_names[el] + "\n"
                #### END PRINT CARRY CHAINS INFO AS DESIGN.CC FILE
                flat_cc2node_map.append(el)
                sink_node=placedb.carry_chain_sink[el]
                while sink_node > -1:
                    flat_cc2node_map.append(sink_node)
                    #### PRINT CARRY CHAINS INFO AS DESIGN.CC FILE
                    #midportion=midportion+"\t" + placedb.node_names[sink_node] + "\n"
                    #### END PRINT CARRY CHAINS INFO AS DESIGN.CC FILE
                    sink_node=placedb.carry_chain_sink[sink_node]
                flat_cc2node_start_map.append(len(flat_cc2node_map))
                ### PRINT CARRY CHAINS INFO AS DESIGN.CC FILE
                #footer="endcarry"
                ##TODO - Uncomment below 3 lines to generate carry chain information
                #print(header)
                #print(midportion)
                #print(footer)
                ### END PRINT CARRY CHAINS INFO AS DESIGN.CC FILE
            placedb.flat_cc2node_map = np.array(flat_cc2node_map, dtype=np.int32)
            placedb.flat_cc2node_start_map = np.array(flat_cc2node_start_map, dtype=np.int32)

            if placedb.num_carry_chains > 0:
                logging.info("There are %d carry chains across %d nodes and %d nets" % 
                            (placedb.num_carry_chains, placedb.flat_cc2node_map.shape[0], (placedb.carry_chain_nets > -1).sum()))
        else:
            placedb.num_carry_chains = placedb.num_ccNodes
        ###################################################
        ##END OF CARRY CHAINS IDENTIFICATION
        ###################################################


        ## Random Initial Placement
        self.init_pos = np.zeros(placedb.num_nodes * 2, dtype=placedb.dtype)

        ##Settings to ensure reproduciblity
        manualSeed = 0
        np.random.seed(manualSeed)
        torch.manual_seed(manualSeed)
        if params.gpu:
            torch.cuda.manual_seed(manualSeed)
            torch.cuda.manual_seed_all(manualSeed)

        numPins = 0
        initLocX = 0
        initLocY = 0

        if placedb.num_terminals > 0:
            ##Use the average fixed pin location (weighted by pin count) as the initial location
            for nodeID in range(placedb.num_movable_nodes,placedb.num_physical_nodes):
                for pID in placedb.node2pin_map[nodeID]:
                    initLocX += placedb.node_x[nodeID] + placedb.pin_offset_x[pID]
                    initLocY += placedb.node_y[nodeID] + placedb.pin_offset_y[pID]
                numPins += len(placedb.node2pin_map[nodeID])
            initLocX /= numPins
            initLocY /= numPins
        else: ##Design does not have IO pins - place in center
            initLocX = 0.5 * (placedb.xh - placedb.xl)
            initLocY = 0.5 * (placedb.yh - placedb.yl)

        # x position
        self.init_pos[0:placedb.num_physical_nodes] = placedb.node_x
        if params.global_place_flag and params.random_center_init_flag:  # move to centroid of layout
            #logging.info("Move cells to the centroid of fixed IOs with random noise")
            self.init_pos[0:placedb.num_movable_nodes] = np.random.normal(
                loc = initLocX,
                scale = min(placedb.xh - placedb.xl, placedb.yh - placedb.yl) * 0.001,
                size = placedb.num_movable_nodes)
        self.init_pos[0:placedb.num_movable_nodes] -= (0.5 * placedb.node_size_x[0:placedb.num_movable_nodes])

        # y position
        self.init_pos[placedb.num_nodes:placedb.num_nodes+placedb.num_physical_nodes] = placedb.node_y
        if params.global_place_flag and params.random_center_init_flag:  # move to center of layout
            self.init_pos[placedb.num_nodes:placedb.num_nodes+placedb.num_movable_nodes] = np.random.normal(
                loc = initLocY,
                scale = min(placedb.xh - placedb.xl, placedb.yh - placedb.yl) * 0.001,
                size = placedb.num_movable_nodes)
        self.init_pos[placedb.num_nodes:placedb.num_nodes+placedb.num_movable_nodes] -= (0.5 * placedb.node_size_y[0:placedb.num_movable_nodes])
        #logging.info("Random Init Place in python takes %.2f seconds" % (time.time() - tt))

        if placedb.num_filler_nodes:  # uniformly distribute filler cells in the layout
            ### uniformly spread fillers in fence region
            ### for cells in the fence region
            for idx in range(placedb.regions):
                i = placedb.rsrc2compId_map[idx]
                if i != -1:
                    region = placedb.region_boxes[i]
                    #Construct Nx4 np array for region using placedb.flat_region_boxes
                    filler_beg, filler_end = placedb.filler_start_map[i:i+2]
                    if filler_end-filler_beg > 0:
                        num_region_fillers = filler_end-filler_beg
                        subregion_areas = (region[:,2]-region[:,0])*(region[:,3]-region[:,1])
                        total_area = np.sum(subregion_areas)
                        subregion_area_ratio = subregion_areas / total_area
                        subregion_num_filler = np.floor((filler_end - filler_beg) * subregion_area_ratio)
                        rem_fillers = num_region_fillers - int(subregion_num_filler.sum())
                        subregion_num_filler[:rem_fillers] += 1
                        #subregion_num_filler[-1] = (filler_end - filler_beg) - np.sum(subregion_num_filler[:-1])
                        subregion_num_filler_start_map = np.concatenate([np.zeros([1]),np.cumsum(subregion_num_filler)],0).astype(np.int32)
                        for j, subregion in enumerate(region):
                            sub_filler_beg, sub_filler_end = subregion_num_filler_start_map[j:j+2]
                            self.init_pos[placedb.num_physical_nodes+filler_beg+sub_filler_beg:placedb.num_physical_nodes+filler_beg+sub_filler_end]=np.random.uniform(
                                    low=subregion[0],
                                    high=subregion[2] -
                                    placedb.filler_size_x_fence_region[i],
                                    size=sub_filler_end-sub_filler_beg)
                            self.init_pos[placedb.num_nodes+placedb.num_physical_nodes+filler_beg+sub_filler_beg:placedb.num_nodes+placedb.num_physical_nodes+filler_beg+sub_filler_end]=np.random.uniform(
                                    low=subregion[1],
                                    high=subregion[3] -
                                    placedb.filler_size_y_fence_region[i],
                                    size=sub_filler_end-sub_filler_beg)
                #Skip for IOs
                else:
                    continue

            #logging.info("Random Init Place in Python takes %.2f seconds" % (time.time() - t2))
        
        self.device = torch.device("cuda" if params.gpu else "cpu")

        # position should be parameter
        # must be defined in BasicPlace
        #tbp = time.time()
        self.pos = nn.ParameterList(
            [nn.Parameter(torch.from_numpy(self.init_pos).to(self.device))])
        #logging.info("build pos takes %.2f seconds" % (time.time() - tbp))
        # shared data on device for building ops to avoid constructing data from placedb again and again
        #tt = time.time()
        self.data_collections = PlaceDataCollectionFPGA(self.pos, params, placedb, self.device)
        #logging.info("build data_collections takes %.2f seconds" %
        #              (time.time() - tt))

        # All ops are wrapped
        #tt = time.time()
        self.op_collections = PlaceOpCollectionFPGA()
        #logging.info("build op_collections takes %.2f seconds" %
        #              (time.time() - tt))

        tt = time.time()
        # Demand Map computation
        self.op_collections.demandMap_op = self.build_demandMap(params, placedb, self.data_collections, self.device)
        # position to pin position
        self.op_collections.pin_pos_op = self.build_pin_pos(params, placedb, self.data_collections, self.device)
        # bound nodes to layout region
        self.op_collections.move_boundary_op = self.build_move_boundary(params, placedb, self.data_collections, self.device)
        # hpwl and density overflow ops for evaluation
        self.op_collections.hpwl_op = self.build_hpwl(params, placedb, self.data_collections, self.op_collections.pin_pos_op, self.device)
        # WL preconditioner
        self.op_collections.precondwl_op = self.build_precondwl(params, placedb, self.data_collections, self.device)
        self.op_collections.lg_precondition_op = self.build_LGprecondwl(params, placedb, self.data_collections, self.device)
        # Sorting node2pin map
        self.op_collections.sort_node2pin_op = self.build_sortNode2Pin(params, placedb, self.data_collections, self.device)
        # rectilinear minimum steiner tree wirelength from flute
        # can only be called once
        self.op_collections.density_overflow_op = self.build_electric_overflow(params, placedb, self.data_collections, self.device)

        ##Legalization
        self.op_collections.lut_ff_legalization_op = self.build_lut_ff_legalization(params, placedb, self.data_collections, self.device)

        # draw placement
        self.op_collections.draw_place_op = self.build_draw_placement(params, placedb)

        #logging.info("build BasicPlace ops takes %.2f seconds" %
        #              (time.time() - tt))

    def __call__(self, params, placedb):
        """
        @brief Solve placement.
        placeholder for derived classes.
        @param params parameters
        @param placedb placement database
        """
        pass

    def build_pin_pos(self, params, placedb, data_collections, device):
        """
        @brief sum up the pins for each cell
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param device cpu or cuda
        """
        # Yibo: I found CPU version of this is super slow, more than 2s for ISPD2005 bigblue4 with 10 threads.
        # So I implemented a custom CPU version, which is around 20ms
        #pin2node_map = data_collections.pin2node_map.long()
        #def build_pin_pos_op(pos):
        #    pin_x = data_collections.pin_offset_x.add(torch.index_select(pos[0:placedb.num_physical_nodes], dim=0, index=pin2node_map))
        #    pin_y = data_collections.pin_offset_y.add(torch.index_select(pos[placedb.num_nodes:placedb.num_nodes+placedb.num_physical_nodes], dim=0, index=pin2node_map))
        #    pin_pos = torch.cat([pin_x, pin_y], dim=0)

        #    return pin_pos
        #return build_pin_pos_op

        return pin_pos.PinPos(
            pin_offset_x=data_collections.pin_offset_x,
            pin_offset_y=data_collections.pin_offset_y,
            pin2node_map=data_collections.pin2node_map,
            flat_node2pin_map=data_collections.flat_node2pin_map,
            flat_node2pin_start_map=data_collections.flat_node2pin_start_map,
            num_physical_nodes=placedb.num_physical_nodes,
            num_threads=params.num_threads,
            algorithm="node-by-node")

    def build_move_boundary(self, params, placedb, data_collections, device):
        """
        @brief bound nodes into layout region
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param device cpu or cuda
        """
        return move_boundary.MoveBoundary(
            data_collections.node_size_x,
            data_collections.node_size_y,
            xl=placedb.xl,
            yl=placedb.yl,
            xh=placedb.xh,
            yh=placedb.yh,
            num_movable_nodes=placedb.num_movable_nodes,
            num_filler_nodes=placedb.num_filler_nodes,
            num_threads=params.num_threads)

    def build_hpwl(self, params, placedb, data_collections, pin_pos_op, device):
        """
        @brief compute half-perimeter wirelength
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param pin_pos_op the op to compute pin locations according to cell locations
        @param device cpu or cuda
        """
        wirelength_for_pin_op = hpwl.HPWL(
            placedb=placedb,
            flat_netpin=data_collections.flat_net2pin_map,
            netpin_start=data_collections.flat_net2pin_start_map,
            pin2net_map=data_collections.pin2net_map,
            net_weights=data_collections.net_weights,
            num_carry_chains=placedb.num_carry_chains,
            cc_net_weight=placedb.carry_chain_net_weight,
            dir_net_weight=params.dir_net_weight,
            #net_mask=data_collections.net_mask_all,
            net_mask=data_collections.net_mask_ignore_large_degrees,
            net_bounding_box_min=data_collections.net_bounding_box_min,
            net_bounding_box_max=data_collections.net_bounding_box_max,
            num_threads=params.num_threads,
            algorithm='net-by-net')

        # wirelength for position
        def build_wirelength_op(pos):
            return wirelength_for_pin_op(pin_pos_op(pos))

        return build_wirelength_op

    def build_demandMap(self, params, placedb, data_collections, device):
        """
        @brief Build binCapMap and fixedDemandMap
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param device cpu or cuda
        """
        return demandMap.DemandMap(
            placedb=placedb,
            site_type_map=data_collections.site_type_map,
            site_size_x=data_collections.resource_size_x,
            site_size_y=data_collections.resource_size_y,
            deterministic_flag=params.deterministic_flag,
            device=device,
            num_threads=params.num_threads)

    def build_precondwl(self, params, placedb, data_collections, device):
        """
        @brief compute wirelength precondtioner
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param device cpu or cuda
        """
        return precondWL.PrecondWL(
            flat_node2pin_start=data_collections.flat_node2pin_start_map,
            flat_node2pin=data_collections.flat_node2pin_map,
            pin2net_map=data_collections.pin2net_map,
            flat_net2pin=data_collections.flat_net2pin_start_map,
            net_weights=data_collections.net_weights,
            num_nodes=placedb.num_nodes,
            num_movable_nodes=placedb.num_physical_nodes,#Compute for fixed nodes as well for Legalization
            device=device,
            num_threads=params.num_threads)

    def build_LGprecondwl(self, params, placedb, data_collections, device):
        """
        @brief compute wirelength precondtioner
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param device cpu or cuda
        """
        if placedb.num_ccNodes > 0:
            return precondWL.PrecondWL(
                flat_node2pin_start=data_collections.org_flat_node2pin_start_map,
                flat_node2pin=data_collections.org_flat_node2pin_map,
                pin2net_map=data_collections.pin2net_map,
                flat_net2pin=data_collections.flat_net2pin_start_map,
                net_weights=data_collections.net_weights,
                num_nodes=placedb.org_num_physical_nodes + placedb.num_filler_nodes,
                num_movable_nodes=placedb.org_num_physical_nodes,#Compute for fixed nodes as well for Legalization
                device=device,
                num_threads=params.num_threads)

    def build_sortNode2Pin(self, params, placedb, data_collections, device):
        """
        @brief sort instance node2pin mapping
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param device cpu or cuda
        """
        #Only used for LG
        if placedb.num_ccNodes == 0:
            return sortNode2Pin.SortNode2Pin(
                flat_node2pin_start=data_collections.flat_node2pin_start_map,
                flat_node2pin=data_collections.flat_node2pin_map,
                num_nodes=placedb.num_physical_nodes,
                device=device,
                num_threads=params.num_threads)
        else:
            return sortNode2Pin.SortNode2Pin(
                flat_node2pin_start=data_collections.org_flat_node2pin_start_map,
                flat_node2pin=data_collections.org_flat_node2pin_map,
                num_nodes=placedb.org_num_physical_nodes,
                device=device,
                num_threads=params.num_threads)

    def build_electric_overflow(self, params, placedb, data_collections, device):
        """
        @brief compute electric density overflow
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param device cpu or cuda
        """
        return electric_overflow.ElectricOverflow(
            node_size_x=data_collections.node_size_x,
            node_size_y=data_collections.node_size_y,
            xl=placedb.xl,
            yl=placedb.yl,
            xh=placedb.xh,
            yh=placedb.yh,
            bin_size_x=placedb.bin_size_x,
            bin_size_y=placedb.bin_size_y,
            num_movable_nodes=placedb.num_movable_nodes,
            num_terminals=placedb.num_terminals,
            num_filler_nodes=0,
            deterministic_flag=params.deterministic_flag,
            sorted_node_map=data_collections.sorted_node_map)


    def build_lut_ff_legalization(self, params, placedb, data_collections, device):
        """
        @brief legalization of LUT/FF Instances
        @param params parameters
        @param placedb placement database
        @param data_collections a collection of all data and variables required for constructing the ops
        @param device cpu or cuda
        """
        # legalize LUT/FF
        ###Avg areas
        ##avgLUTArea = data_collections.node_areas[:placedb.num_physical_nodes][placedb.lut_mask].sum()
        ##avgLUTArea /= placedb.node_count[placedb.rLUTIdx]
        ##avgFFArea = data_collections.node_areas[:placedb.num_physical_nodes][placedb.flop_mask].sum()
        ##avgFFArea /= placedb.node_count[placedb.rFFIdx]
        ###Inst Areas
        ##inst_areas = data_collections.node_areas[:placedb.num_physical_nodes].detach().clone()
        ##inst_areas[~placedb.lut_flop_mask] = 0.0 #Area of non SLICE nodes set to 0.0
        ##inst_areas[placedb.lut_mask] /= avgLUTArea
        ##inst_areas[placedb.flop_mask] /= avgFFArea
        #Site types
        site_types = data_collections.site_type_map.detach().clone()
        site_types[site_types != placedb.sSLICEIdx] = 0 #Set non SLICE to 0

        if (len(data_collections.net_weights)):
            net_wts = data_collections.net_weights
        else:
            net_wts = torch.ones(placedb.num_nets, dtype=self.pos[0].dtype, device=device)

        return lut_ff_legalization.LegalizeCLB(
            data_collections=data_collections,
            placedb=placedb,
            net_wts=net_wts,
            #inst_areas=inst_areas,
            site_types=site_types,
            num_threads=params.num_threads,
            device=device)

    def build_draw_placement(self, params, placedb):
        """
        @brief plot placement
        @param params parameters
        @param placedb placement database
        """
        return draw_place.DrawPlaceFPGA(placedb)

    def validate(self, placedb, pos, iteration):
        """
        @brief validate placement
        @param placedb placement database
        @param pos locations of cells
        @param iteration optimization step
        """
        pos = torch.from_numpy(pos).to(self.device)
        hpwl = self.op_collections.hpwl_op(pos)
        overflow, max_density = self.op_collections.density_overflow_op(pos)

        return hpwl, overflow, max_density

    def plot(self, params, placedb, iteration, pos):
        """
        @brief plot layout
        @param params parameters
        @param placedb placement database
        @param iteration optimization step
        @param pos locations of cells
        """
        tt = time.time()
        path = "%s/%s" % (params.result_dir, params.design_name())
        figname = "%s/plot/iter%s.png" % (path, '{:04}'.format(iteration))
        os.system("mkdir -p %s" % (os.path.dirname(figname)))
        if isinstance(pos, np.ndarray):
            pos = torch.from_numpy(pos)
        self.op_collections.draw_place_op(pos, figname)
        logging.info("plotting to %s takes %.3f seconds" %
                     (figname, time.time() - tt))


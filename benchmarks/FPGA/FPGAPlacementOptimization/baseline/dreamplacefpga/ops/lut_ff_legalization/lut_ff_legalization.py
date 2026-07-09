##
# @file   lut_ff_legalization.py
# @author Rachel Selina (DREAMPlaceFPGA-PL) 
# @date   Apr 2022
#

import math
import torch
from torch import nn
from torch.autograd import Function
import pdb 
import time
import logging
import numpy as np

import dreamplacefpga.ops.lut_ff_legalization.lut_ff_legalization_cpp as lut_ff_legalization_cpp
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE": 
    import dreamplacefpga.ops.lut_ff_legalization.lut_ff_legalization_cuda as lut_ff_legalization_cuda

def carry_chain_checker(flat_cc2node_start_map, flat_cc2node_map, inst_curr_detSite,
        site2addr_map, site_det_impl_lut, num_sites_y, lutsInSlice,
        num_carry_chains, device):

    carry_chain_ck = torch.zeros(num_carry_chains, dtype=torch.int, device=device)

    for idx in range(num_carry_chains):
        instId = flat_cc2node_map[flat_cc2node_start_map[idx]].item()
        siteId = inst_curr_detSite[instId].item()
        columnX = math.floor(siteId/num_sites_y)
        currY = math.floor(siteId%num_sites_y)
        s_Id = site2addr_map[siteId].item()

        if instId in site_det_impl_lut[s_Id]:
            instZ = (site_det_impl_lut[s_Id] == instId).nonzero(as_tuple=True)[0].item()
        else:
            print("ERROR: Instance: ", instId, " not found in site_det but assigned in inst_curr_detSite for site: ", siteId, " and sIdx: ", s_Id)

        if instZ != 0:
            carry_chain_ck[idx] = carry_chain_ck[idx]+1
            print("ERROR: INCORRECT START: For idx: ", idx , " start inst: ", instId, " has loc: ", updXloc[instId].to(torch.int).item(), ", ", updYloc[instId].to(torch.int).item(), ", ", updZloc[instId].item())

        yOffset = 0
        cnt = 0
        if instZ == 0:
            cnt = 1
        for ccIdx in range(flat_cc2node_start_map[idx]+1, flat_cc2node_start_map[idx+1]):
            instId = flat_cc2node_map[ccIdx].item()
            siteId = inst_curr_detSite[instId].item()
            nextX = math.floor(siteId/num_sites_y)
            nextY = math.floor(siteId%num_sites_y)
            s_Id = site2addr_map[siteId].item()

            if instId in site_det_impl_lut[s_Id]:
                nextZ = (site_det_impl_lut[s_Id] == instId).nonzero(as_tuple=True)[0].item()
            else:
                print("ERROR: Instance: ", instId, " not found in site_det but assigned in inst_curr_detSite for site: ", siteId, " and sIdx: ", s_Id)

            if columnX != nextX or nextY != currY + yOffset or nextZ != cnt:
                carry_chain_ck[idx] = carry_chain_ck[idx]+1
                print("ERROR: INCORRECT ")
                if columnX != nextX:
                    print(" X ")
                if nextY != currY + yOffset:
                    print(" Y ")
                if nextZ != cnt:
                    print(" Z ")
                print(" Location for carry chain (", idx , ") with inst: ", instId, " at (", nextX, ", ", nextY, ", ", nextZ, ")")

            cnt = cnt + 1
            if cnt == lutsInSlice:
                cnt = 0
                yOffset = yOffset - 1

        if carry_chain_ck[idx] > 0:
            print("ERROR: Check carry chain (", idx , ") with inst: ", instId, " at (", updXloc[instId].to(torch.int).item(), ", ", updYloc[instId].to(torch.int).item(), ", ", updZloc[instId].item(), ")")
    if carry_chain_ck.sum() > 0:
        logging.info("ERROR: %d Carry-chains not correct" %(carry_chain_ck.sum()))

def carry_chain_checker_loc(flat_cc2node_start_map, flat_cc2node_map, updXloc, updYloc,
        updZloc, HALF_SLICE_CAPACITY, lutsInSlice, num_carry_chains, device):

    carry_chain_ck = torch.zeros(num_carry_chains, dtype=torch.int, device=device)
    for idx in range(num_carry_chains):
        instId = flat_cc2node_map[flat_cc2node_start_map[idx]].item()
        columnX = updXloc[instId].item()
        currY = updYloc[instId].item()
        instZ = updZloc[instId].item()

        if instZ != 0 and instZ != HALF_SLICE_CAPACITY:
            carry_chain_ck[idx] = carry_chain_ck[idx]+1
            print("ERROR: INCORRECT START: For idx: ", idx , " start inst: ", instId, " has loc: ", updXloc[instId].to(torch.int).item(), ", ", updYloc[instId].to(torch.int).item(), ", ", updZloc[instId].item())

        yOffset = 0
        cnt = 0
        if instZ == 0:
            cnt = 1
        elif instZ == HALF_SLICE_CAPACITY:
            cnt = 1 + HALF_SLICE_CAPACITY
        for ccIdx in range(flat_cc2node_start_map[idx]+1, flat_cc2node_start_map[idx+1]):
            instId = flat_cc2node_map[ccIdx].item()

            if columnX != updXloc[instId].item() or updYloc[instId].item() != currY + yOffset or updZloc[instId].item() != cnt:
                carry_chain_ck[idx] = carry_chain_ck[idx]+1
                print("ERROR: INCORRECT ")
                if columnX != updXloc[instId].item():
                    print(" X ")
                if updYloc[instId].item() != currY + yOffset:
                    print(" Y ")
                if updZloc[instId].item() != cnt:
                    print(" Z ")
                print(" Location for carry chain (", idx , ") with inst: ", instId, " at (", updXloc[instId].to(torch.int).item(), ", ", updYloc[instId].to(torch.int).item(), ", ", updZloc[instId].item(), ")")

            cnt = cnt + 1
            if cnt == lutsInSlice:
                cnt = 0
                yOffset = yOffset - 1

        if carry_chain_ck[idx] > 0:
            print("ERROR: Check carry chain (", idx , ") with inst: ", instId, " at (", updXloc[instId].to(torch.int).item(), ", ", updYloc[instId].to(torch.int).item(), ", ", updZloc[instId].item(), ")")
    if carry_chain_ck.sum() > 0:
        logging.info("ERROR: %d Carry-chains not correct" %(carry_chain_ck.sum()))

def compute_remaining_slice_sites(slice_sites, site_det_sig_idx, addr2site_map):

    assigned_slice_site_mask = np.zeros(slice_sites.shape[0], dtype=bool)
    assigned_sites = addr2site_map[torch.where(site_det_sig_idx > 0)[0].long()].cpu().detach().numpy()

    indices = np.where(np.in1d(slice_sites, assigned_sites))[0]
    assigned_slice_site_mask[indices] = True

    return ~assigned_slice_site_mask

class LegalizeCLB(nn.Module):
    def __init__(self, data_collections, placedb, net_wts, #inst_areas,
                    site_types, num_threads, device):

        super(LegalizeCLB, self).__init__()

        if placedb.num_ccNodes == 0:
            self.num_movable_nodes=placedb.num_movable_nodes
            self.num_nodes=placedb.num_physical_nodes
            self.lut_flop_indices=data_collections.flop_lut_indices
            self.is_mlab_node = data_collections.is_mlab_node.int()
            self.flop2ctrlSetId_map=data_collections.flop2ctrlSetId_map
            self.flop_ctrlSets=data_collections.flop_ctrlSets
            self.pin2node_map=data_collections.pin2node_map
            self.flat_node2pin_map=data_collections.flat_node2pin_map
            self.flat_node2pin_start_map=data_collections.flat_node2pin_start_map
            self.node2fence_region_map=data_collections.node2fence_region_map
            self.node2outpinIdx_map=data_collections.node2outpinIdx_map
            self.node2pincount=data_collections.node2pincount_map
            self.lut_type=data_collections.lut_type
            self.pin_offset_x=data_collections.lg_pin_offset_x
            self.pin_offset_y=data_collections.lg_pin_offset_y
            self.node_size_x=data_collections.node_size_x[:self.num_nodes]
            self.node_size_y=data_collections.node_size_y[:self.num_nodes]
            self.flat_cc2node_map = torch.from_numpy(placedb.flat_cc2node_map).to(dtype=torch.int, device=device)
            self.flat_cc2node_start_map = torch.from_numpy(placedb.flat_cc2node_start_map).to(dtype=torch.int, device=device)
        else:
            self.num_movable_nodes=placedb.org_num_movable_nodes
            self.num_nodes=placedb.org_num_physical_nodes
            self.lut_flop_indices=data_collections.org_flop_lut_indices
            self.is_mlab_node = data_collections.org_is_mlab_node.int()
            self.flop2ctrlSetId_map=data_collections.org_flop2ctrlSetId_map
            self.flop_ctrlSets=data_collections.org_flop_ctrlSets
            self.pin2node_map=data_collections.org_pin2node_map
            self.flat_node2pin_map=data_collections.org_flat_node2pin_map
            self.flat_node2pin_start_map=data_collections.org_flat_node2pin_start_map
            self.node2fence_region_map=data_collections.org_node2fence_region_map
            self.node2outpinIdx_map=data_collections.org_node2outpinIdx_map
            self.node2pincount=data_collections.org_node2pincount_map
            self.lut_type=data_collections.org_lut_type
            self.pin_offset_x=data_collections.org_lg_pin_offset_x
            self.pin_offset_y=data_collections.org_lg_pin_offset_y
            self.node_size_x=data_collections.org_node_size_x[:self.num_nodes]
            self.node_size_y=data_collections.org_node_size_y[:self.num_nodes]
            self.flat_cc2node_map = torch.from_numpy(placedb.org_flat_cc2node_map).to(dtype=torch.int, device=device)
            self.flat_cc2node_start_map = torch.from_numpy(placedb.org_flat_cc2node_start_map).to(dtype=torch.int, device=device)

        self.num_lutflops=self.lut_flop_indices.shape[0]

        self.pin_typeIds=data_collections.pin_typeIds
        self.pin2net_map=data_collections.pin2net_map
        self.flat_net2pin_map=data_collections.flat_net2pin_map
        self.flat_net2pin_start_map=data_collections.flat_net2pin_start_map

        self.site_xy=data_collections.lg_siteXYs
        self.net2pincount=data_collections.net2pincount_map
        self.spiral_accessor=data_collections.spiral_accessor

        self.num_nets=placedb.num_nets
        self.num_sites_x=placedb.num_sites_x
        self.num_sites_y=placedb.num_sites_y
        self.xWirelenWt=placedb.xWirelenWt
        self.yWirelenWt=placedb.yWirelenWt
        self.nbrDistEnd=placedb.nbrDistEnd

        self.xl = placedb.xl
        self.yl = placedb.yl
        self.xh = placedb.xh
        self.yh = placedb.yh

        self.net_wts=net_wts
        #self.inst_areas=inst_areas
        self.site_types=site_types
        self.num_threads=num_threads
        self.device=device
        self.dtype = self.node_size_x.dtype

        self.sliceId = placedb.sSLICEIdx
        self.lutId = placedb.rLUTIdx
        self.ffId = placedb.rFFIdx

        self.lut_flop_mask = torch.logical_or(self.node2fence_region_map == self.lutId,self.node2fence_region_map == self.ffId)

        lutName = [key for key, val in placedb.rsrcType2indexMap.items() if val==placedb.rLUTIdx][0]
        ffName = [key for key, val in placedb.rsrcType2indexMap.items() if val==placedb.rFFIdx][0]

        self.lutsInSlice = placedb.siteRsrc2CountMap[lutName]
        ffsInSlice = placedb.siteRsrc2CountMap[ffName]

        #mlabs
        self.mlab_indices = torch.where(self.is_mlab_node == 1)[0].to(torch.int32)
        self.num_mlab_nodes = self.mlab_indices.shape[0]

        #Carry chains
        self.num_carry_chains = placedb.num_carry_chains
        self.num_ccNodes = placedb.num_ccNodes

        self.slice_minX = int(placedb.slice_x_min)
        self.slice_maxX = int(placedb.slice_x_max)
        self.slice_minY = int(placedb.slice_y_min)
        self.slice_maxY = int(placedb.slice_y_max)
        self.sliceSiteXYs = placedb.sliceSiteXYs
        self.slice_sites = (self.sliceSiteXYs[:,0]*self.num_sites_y + self.sliceSiteXYs[:,1]).astype(np.int32)

        #Architecture specific values
        for el in placedb.sliceFFCtrls:
            if 'clk'.casefold() in el[0].casefold() or 'ck'.casefold() in el[0].casefold():
                self.CKSR_IN_CLB = el[1]
            else:
                self.CE_IN_CLB = el[1]

        self.half_ctrl_mode = 0 #Use for FF ctrl signals

        if placedb.sliceFF_ctrl_mode == "HALF":
            self.CKSR_IN_CLB *= 2
            self.CE_IN_CLB *= 2
            self.half_ctrl_mode = 1

        for el in placedb.sliceElements:
            if lutName in el[0]:
                self.BLE_CAPACITY = el[1]
                break

        self.ff_ctrl_type = placedb.ff_ctrl_type
        self.netShareScoreMaxNetDegree = self.lutsInSlice
        self.SLICE_CAPACITY = placedb.SLICE_CAPACITY
        self.HALF_SLICE_CAPACITY = placedb.HALF_SLICE_CAPACITY
        self.NUM_BLE_PER_SLICE = int(self.SLICE_CAPACITY/self.BLE_CAPACITY)
        self.NUM_BLE_PER_HALF_SLICE = int(self.HALF_SLICE_CAPACITY/self.BLE_CAPACITY)
        self.extended_ctrlSets = torch.from_numpy(placedb.extended_ctrlSets).to(dtype=torch.int, device=self.device)
        self.ext_ctrlSet_start_map = torch.from_numpy(placedb.ext_ctrlSet_start_map).to(dtype=torch.int, device=self.device)

        self.PQ_IDX = 10
        self.SCL_IDX = 128

        self.SIG_IDX = self.lutsInSlice + ffsInSlice

        #Initialize required constants
        self.nbrDistBeg = 1.0
        self.nbrDistIncr = 1.0
        self.extNetCountWt = 0.3
        self.wirelenImprovWt = 0.1
        self.int_min_val = -2147483647
        self.WLscoreMaxNetDegree = 100
        self.maxList = max(128, math.ceil(0.005 * self.num_nodes)) #Based on empirical results from elfPlace
        self.numGroups = math.ceil((self.nbrDistEnd-self.nbrDistBeg)/self.nbrDistIncr) + 1

        #LUT specific entries
        #lut type that occupies entire sliceunit
        self.lutTypeInSliceUnit = placedb.lutTypeInSliceUnit
        #max shared inputs to luts in a sliceunit
        self.lut_maxShared = placedb.lut_maxShared

        #Initialize required tensors
        self.net_bbox = torch.zeros(self.num_nets*4, dtype=self.dtype, device=device)

        self.net_pinIdArrayX = torch.zeros(len(self.flat_net2pin_map), dtype=torch.int, device=device)
        self.net_pinIdArrayY = torch.zeros_like(self.net_pinIdArrayX) #len(flat_net2pin)

        self.flat_node2precluster_map = torch.ones((self.num_nodes,3), dtype=torch.int, device=device)
        self.flat_node2precluster_map *= -1
        self.flat_node2precluster_map[:,0] = torch.arange(self.num_nodes, dtype=torch.int, device=device)
        self.flat_node2prclstrCount = torch.ones(self.num_nodes, dtype=torch.int, device=device)

        #Instance Candidates
        self.inst_curr_detSite = torch.zeros_like(self.flat_node2prclstrCount) #num_nodes
        self.inst_curr_detSite[self.lut_flop_mask] = -1
        self.inst_curr_bestSite = torch.zeros_like(self.inst_curr_detSite) #num_nodes
        self.inst_curr_bestSite[self.lut_flop_mask] = -1
        self.inst_curr_bestScoreImprov = torch.zeros(self.num_nodes, dtype=self.dtype, device=device)
        self.inst_curr_bestScoreImprov[self.lut_flop_mask] = -10000.0

        self.inst_next_detSite = torch.zeros_like(self.inst_curr_detSite) #num_nodes
        self.inst_next_detSite[self.lut_flop_mask] = -1
        self.inst_next_bestSite = torch.zeros_like(self.inst_next_detSite) #num_nodes
        self.inst_next_bestSite[self.lut_flop_mask] = -1
        self.inst_next_bestScoreImprov = torch.zeros_like(self.inst_curr_bestScoreImprov) #num_nodes
        self.inst_next_bestScoreImprov[self.lut_flop_mask] = -10000.0

        self.num_clb_sites = torch.bincount(self.site_types.flatten())[self.sliceId].item()
        #Map from mem addr to CLB site
        self.addr2site_map = self.site_types.flatten().nonzero(as_tuple=True)[0]
        #Map from CLB site to mem addr
        self.site2addr_map = torch.ones(self.num_sites_x*self.num_sites_y, dtype=torch.int, device=device)
        self.site2addr_map *= -1
        self.site2addr_map[self.addr2site_map] = torch.arange(self.num_clb_sites, dtype=torch.int, device=device)
        self.addr2site_map = self.addr2site_map.int()

        #Site Neighbors
        self.site_nbrList = torch.zeros((self.num_clb_sites, self.maxList), dtype=torch.int, device=device)
        self.site_nbr = torch.zeros_like(self.site_nbrList) #num_clb_sites * maxList
        self.site_nbr_idx = torch.zeros(self.num_clb_sites, dtype=torch.int, device=device)
        self.site_nbrRanges = torch.zeros((self.num_clb_sites, self.numGroups+1), dtype=torch.int, device=device)
        self.site_nbrRanges_idx = torch.zeros_like(self.site_nbr_idx) #num_clb_sites
        self.site_nbrGroup_idx = torch.zeros_like(self.site_nbr_idx) #num_clb_sites
        ##Site Candidates
        self.site_det_score = torch.zeros(self.num_clb_sites, dtype=self.dtype, device=device)
        self.site_det_siteId = torch.ones_like(self.site_nbr_idx) #num_clb_sites
        self.site_det_siteId *= -1
        self.site_det_impl_lut = torch.ones((self.num_clb_sites, self.SLICE_CAPACITY), dtype=torch.int, device=device)
        self.site_det_impl_lut *= -1
        self.site_det_impl_ff = torch.ones_like(self.site_det_impl_lut) #num_clb_sites * SLICE_CAPACITY
        self.site_det_impl_ff *= -1
        self.site_det_impl_cksr = torch.ones((self.num_clb_sites, self.CKSR_IN_CLB), dtype=torch.int, device=device)
        self.site_det_impl_cksr *= -1
        self.site_det_impl_ce = torch.ones((self.num_clb_sites, self.CE_IN_CLB), dtype=torch.int, device=device)
        self.site_det_impl_ce *= -1
        self.site_det_sig = torch.ones((self.num_clb_sites, self.SIG_IDX), dtype=torch.int, device=device)
        self.site_det_sig *= -1
        self.site_det_sig_idx = torch.zeros_like(self.site_det_siteId) #num_clb_sites

        self.site_curr_stable = torch.zeros_like(self.site_nbr_idx) #num_clb_sites
        self.site_curr_scl_idx = torch.zeros_like(self.site_nbr_idx) #num_clb_sites
        self.site_curr_scl_validIdx = torch.ones((self.num_clb_sites, self.SCL_IDX), dtype=torch.int, device=device)
        self.site_curr_scl_validIdx *= -1
        self.site_curr_scl_siteId = torch.ones((self.num_clb_sites, self.SCL_IDX), dtype=torch.int, device=device) #num_clb_sites * SCL_IDX
        self.site_curr_scl_siteId *= -1
        self.site_curr_scl_score = torch.zeros((self.num_clb_sites, self.SCL_IDX), dtype=self.dtype, device=device)
        self.site_curr_scl_impl_lut = torch.ones((self.num_clb_sites, self.SCL_IDX, self.SLICE_CAPACITY), dtype=torch.int, device=device)
        self.site_curr_scl_impl_lut *= -1
        self.site_curr_scl_impl_ff = torch.ones_like(self.site_curr_scl_impl_lut) #num_clb_sites * SCL_IDX * SLICE_CAPACITY
        self.site_curr_scl_impl_ff *= -1
        self.site_curr_scl_impl_cksr = torch.ones((self.num_clb_sites, self.SCL_IDX, self.CKSR_IN_CLB), dtype=torch.int, device=device)
        self.site_curr_scl_impl_cksr *= -1
        self.site_curr_scl_impl_ce = torch.ones((self.num_clb_sites, self.SCL_IDX, self.CE_IN_CLB), dtype=torch.int, device=device)
        self.site_curr_scl_impl_ce *= -1
        self.site_curr_scl_sig = torch.ones((self.num_clb_sites, self.SCL_IDX, self.SIG_IDX), dtype=torch.int, device=device)
        self.site_curr_scl_sig *= -1
        self.site_curr_scl_sig_idx = torch.zeros_like(self.site_curr_scl_siteId) #num_clb_sites * SCL_IDX

        self.site_curr_pq_idx = torch.zeros_like(self.site_nbr_idx) #num_clb_sites
        self.site_curr_pq_top_idx = torch.ones_like(self.site_nbr_idx) #num_clb_sites
        self.site_curr_pq_top_idx *= -1
        self.site_curr_pq_score = torch.zeros((self.num_clb_sites, self.PQ_IDX), dtype=self.dtype, device=device)
        self.site_curr_pq_validIdx = torch.ones((self.num_clb_sites, self.PQ_IDX), dtype=torch.int, device=device)
        self.site_curr_pq_validIdx *= -1
        self.site_curr_pq_siteId = torch.ones((self.num_clb_sites, self.PQ_IDX), dtype=torch.int, device=device) #num_clb_sites * PQ_IDX
        self.site_curr_pq_siteId *= -1
        self.site_curr_pq_sig = torch.ones((self.num_clb_sites, self.PQ_IDX, self.SIG_IDX), dtype=torch.int, device=device)
        self.site_curr_pq_sig *= -1
        self.site_curr_pq_sig_idx = torch.zeros_like(self.site_curr_pq_siteId) #num_clb_sites * PQ_IDX
        self.site_curr_pq_impl_lut = torch.ones((self.num_clb_sites, self.PQ_IDX, self.SLICE_CAPACITY), dtype=torch.int, device=device)
        self.site_curr_pq_impl_lut *= -1
        self.site_curr_pq_impl_ff = torch.ones_like(self.site_curr_pq_impl_lut) #num_clb_sites * PQ_IDX * SLICE_CAPACITY.
        self.site_curr_pq_impl_ff *= -1
        self.site_curr_pq_impl_cksr = torch.ones((self.num_clb_sites, self.PQ_IDX, self.CKSR_IN_CLB), dtype=torch.int, device=device)
        self.site_curr_pq_impl_cksr *= -1
        self.site_curr_pq_impl_ce = torch.ones((self.num_clb_sites, self.PQ_IDX, self.CE_IN_CLB), dtype=torch.int, device=device)
        self.site_curr_pq_impl_ce *= -1

        self.site_next_stable = torch.zeros_like(self.site_nbr_idx) #num_clb_sites
        self.site_next_scl_idx = torch.zeros_like(self.site_nbr_idx) #num_clb_sites
        self.site_next_scl_validIdx = torch.ones_like(self.site_curr_scl_validIdx) #num_clb_sites * SCL_IDX
        self.site_next_scl_validIdx *= -1
        self.site_next_scl_siteId = torch.ones_like(self.site_curr_scl_siteId) #num_clb_sites * SCL_IDX
        self.site_next_scl_siteId *= -1
        self.site_next_scl_score = torch.zeros_like(self.site_curr_scl_score) #num_clb_sites * SCL_IDX
        self.site_next_scl_impl_lut = torch.ones_like(self.site_curr_scl_impl_lut) #num_clb_sites * SCL_IDX * SLICE_CAPACITY
        self.site_next_scl_impl_lut *= -1
        self.site_next_scl_impl_ff = torch.ones_like(self.site_next_scl_impl_lut) #num_clb_sites * SCL_IDX * SLICE_CAPACITY
        self.site_next_scl_impl_ff *= -1
        self.site_next_scl_impl_cksr = torch.ones_like(self.site_curr_scl_impl_cksr) #num_clb_sites * SCL_IDX * CKSR_IN_CLB
        self.site_next_scl_impl_cksr *= -1
        self.site_next_scl_impl_ce = torch.ones_like(self.site_curr_scl_impl_ce) #num_clb_sites * SCL_IDX * CE_IN_CLB
        self.site_next_scl_impl_ce *= -1
        self.site_next_scl_sig = torch.ones_like(self.site_curr_scl_sig) #num_clb_sites * SCL_IDX * SIG_IDX
        self.site_next_scl_sig *= -1
        self.site_next_scl_sig_idx = torch.zeros_like(self.site_next_scl_siteId) #num_clb_sites * SCL_IDX

        self.site_next_pq_idx = torch.zeros_like(self.site_nbr_idx) #num_clb_sites
        self.site_next_pq_top_idx = torch.ones_like(self.site_nbr_idx) #num_clb_sites
        self.site_next_pq_top_idx *= -1
        self.site_next_pq_score = torch.zeros_like(self.site_curr_pq_score) #num_clb_sites * PQ_IDX
        self.site_next_pq_validIdx = torch.ones_like(self.site_curr_pq_validIdx) #num_clb_sites * PQ_IDX
        self.site_next_pq_validIdx *= -1
        self.site_next_pq_siteId = torch.ones_like(self.site_curr_pq_siteId) #num_clb_sites * PQ_IDX
        self.site_next_pq_siteId *= -1
        self.site_next_pq_sig = torch.ones_like(self.site_curr_pq_sig) #num_clb_sites * PQ_IDX * SIG_IDX
        self.site_next_pq_sig *= -1
        self.site_next_pq_sig_idx = torch.zeros_like(self.site_curr_pq_validIdx) #num_clb_sites * PQ_IDX
        self.site_next_pq_impl_lut = torch.ones_like(self.site_curr_pq_impl_lut) #num_clb_sites * PQ_IDX * SLICE_CAPACITY
        self.site_next_pq_impl_lut *= -1
        self.site_next_pq_impl_ff = torch.ones_like(self.site_next_pq_impl_lut) #num_clb_sites * PQ_IDX * SLICE_CAPACITY
        self.site_next_pq_impl_ff *= -1
        self.site_next_pq_impl_cksr = torch.ones_like(self.site_curr_pq_impl_cksr) #num_clb_sites * PQ_IDX * CKSR_IN_CLB
        self.site_next_pq_impl_cksr *= -1
        self.site_next_pq_impl_ce = torch.ones_like(self.site_curr_pq_impl_ce) #num_clb_sites * PQ_IDX * CE_IN_CLB
        self.site_next_pq_impl_ce *= -1

        self.inst_score_improv = torch.zeros(self.num_nodes, dtype=torch.int, device=self.device)
        self.inst_score_improv[self.lut_flop_mask] = self.int_min_val
        self.site_score_improv = torch.zeros(self.num_clb_sites, dtype=torch.int, device=self.device)
        self.site_score_improv *= self.int_min_val

        self.special_nodes = torch.zeros(self.num_nodes, dtype=torch.int, device=self.device)
        self.special_nodes[self.flat_cc2node_map.long()] = 1

    def initialize(self, pos, wlPrecond, sorted_node_map, sorted_node_idx,
            sorted_net_map, sorted_net_idx, sorted_pin_map):

        tt = time.time()

        preClusteringMaxDist = 4.0
        maxD = math.ceil(self.nbrDistEnd) + 1
        spiralBegin = 0
        spiralEnd_maxD = 2 * (maxD + 1) * maxD + 1
        spiralEnd = self.spiral_accessor.shape[0] #Entire chip!

        #Handling carry chains
        self.sites_with_special_nodes = torch.zeros(self.num_clb_sites, dtype=torch.int, device=self.device)
        self.is_mlab_site = torch.zeros(self.num_clb_sites, dtype=torch.int, device=self.device)

        carry_chain_displacements = torch.zeros(self.num_nodes, dtype=pos.dtype, device=self.device)

        if pos.is_cuda:

            lut_ff_legalization_cuda.initLegalization(pos, self.pin_offset_x, self.pin_offset_y, 
                sorted_net_idx, sorted_node_map, sorted_node_idx, self.flat_net2pin_map, 
                self.flat_net2pin_start_map, self.flop2ctrlSetId_map, self.flop_ctrlSets, 
                self.node2fence_region_map, self.node2outpinIdx_map, self.pin2net_map,
                self.pin2node_map, self.pin_typeIds, self.net2pincount, self.is_mlab_node,
                preClusteringMaxDist, self.num_nets, self.num_nodes, self.lutId,
                self.ffId, self.WLscoreMaxNetDegree,
                self.net_bbox, self.net_pinIdArrayX, self.net_pinIdArrayY,
                self.flat_node2precluster_map, self.flat_node2prclstrCount)


            if self.num_carry_chains > 0:

                #Handle carry-chains and arithmetic share chains
                cpu_carry_chain_displacements = carry_chain_displacements.cpu()
                cpu_site_det_score = self.site_det_score.cpu()
                cpu_inst_curr_bestScoreImprov = self.inst_curr_bestScoreImprov.cpu()
                cpu_inst_next_bestScoreImprov = self.inst_next_bestScoreImprov.cpu()
                cpu_sites_with_carry_chain = self.sites_with_special_nodes.cpu()
                cpu_inst_curr_detSite = self.inst_curr_detSite.cpu()
                cpu_inst_curr_bestSite = self.inst_curr_bestSite.cpu()
                cpu_inst_next_detSite = self.inst_next_detSite.cpu()
                cpu_inst_next_bestSite = self.inst_next_bestSite.cpu()
                cpu_site_det_siteId = self.site_det_siteId.cpu()
                cpu_site_det_sig = torch.flatten(self.site_det_sig).cpu()
                cpu_site_det_sig_idx = self.site_det_sig_idx.cpu()
                cpu_site_det_impl_lut = torch.flatten(self.site_det_impl_lut).cpu()


                #Legalize carry chains
                lut_ff_legalization_cpp.legalizeCarryChain(
                    pos.cpu(), torch.flatten(self.site_xy).cpu(), wlPrecond.cpu(),
                    torch.flatten(self.spiral_accessor).cpu(), torch.flatten(self.site_types).cpu(),
                    self.site2addr_map.cpu(), self.flat_cc2node_start_map.cpu(),
                    self.flat_cc2node_map.cpu(), spiralBegin, spiralEnd, self.num_sites_x,
                    self.num_sites_y, self.sliceId, self.SIG_IDX, self.SLICE_CAPACITY,
                    self.num_carry_chains, self.lutsInSlice, self.slice_minX, self.slice_maxX,
                    self.slice_minY, self.slice_maxY,  cpu_carry_chain_displacements,
                    cpu_site_det_score, cpu_inst_curr_bestScoreImprov, cpu_inst_next_bestScoreImprov,
                    cpu_sites_with_carry_chain, cpu_inst_curr_detSite, cpu_inst_curr_bestSite,
                    cpu_inst_next_detSite, cpu_inst_next_bestSite, cpu_site_det_siteId,
                    cpu_site_det_sig, cpu_site_det_sig_idx, cpu_site_det_impl_lut, self.num_threads)

                carry_chain_displacements.data.copy_(cpu_carry_chain_displacements)
                self.site_det_score.data.copy_(cpu_site_det_score)
                self.inst_curr_bestScoreImprov.data.copy_(cpu_inst_curr_bestScoreImprov)
                self.inst_next_bestScoreImprov.data.copy_(cpu_inst_next_bestScoreImprov)
                self.sites_with_special_nodes.data.copy_(cpu_sites_with_carry_chain)
                self.inst_curr_detSite.data.copy_(cpu_inst_curr_detSite)
                self.inst_curr_bestSite.data.copy_(cpu_inst_curr_bestSite)
                self.inst_next_detSite.data.copy_(cpu_inst_next_detSite)
                self.inst_next_bestSite.data.copy_(cpu_inst_next_bestSite)
                self.site_det_siteId.data.copy_(cpu_site_det_siteId)
                torch.flatten(self.site_det_sig).data.copy_(cpu_site_det_sig)
                self.site_det_sig_idx.data.copy_(cpu_site_det_sig_idx)
                torch.flatten(self.site_det_impl_lut).data.copy_(cpu_site_det_impl_lut)

                logging.info("%d carry-chains legalized with max and avg displacements: (%f, %f)"
                            % (self.num_carry_chains, carry_chain_displacements.max(), carry_chain_displacements.sum()/self.num_carry_chains))

            #TODO - When mlabs are treated as a type of LUT
            ##Legalize mlabs if any
            if self.num_mlab_nodes > 0:

                lg_max_dist_init=self.nbrDistEnd
                lg_max_dist_incr=self.nbrDistIncr
                lg_flow_cost_scale=100.0

                #Remove already assigned slice sites if any
                rem_slice_sites_mask = compute_remaining_slice_sites(self.slice_sites, self.site_det_sig_idx, self.addr2site_map)
                num_sites = rem_slice_sites_mask.sum()
                num_total_nodes = pos.numel()//2

                locX = pos[:self.num_nodes][self.is_mlab_node.bool()].cpu().detach().numpy()
                locY = pos[num_total_nodes:num_total_nodes+self.num_nodes][self.is_mlab_node.bool()].cpu().detach().numpy()
                precondWL = wlPrecond[self.is_mlab_node.bool()].cpu().detach().numpy()

                movVal = np.zeros(2, dtype=np.float32).tolist()
                outLoc = np.zeros(2*self.num_mlab_nodes, dtype=np.float32).tolist()

                lut_ff_legalization_cpp.minCostFlow(locX, locY, num_sites, self.num_mlab_nodes, self.sliceSiteXYs[rem_slice_sites_mask].flatten(),
                        precondWL, lg_max_dist_init, lg_max_dist_incr, lg_flow_cost_scale, movVal, outLoc)

                outLoc=np.array(outLoc)
                mlab_locX = torch.from_numpy(outLoc[:self.num_mlab_nodes]).to(dtype=pos.dtype, device=self.device)
                mlab_locY = torch.from_numpy(outLoc[self.num_mlab_nodes:]).to(dtype=pos.dtype, device=self.device)

                mlab_displacements = torch.zeros(self.num_mlab_nodes, dtype=pos.dtype, device=self.device)

                lut_ff_legalization_cuda.legalizeMlab(pos, torch.flatten(self.site_xy),
                    mlab_locX, mlab_locY, self.mlab_indices, self.site2addr_map,
                    self.num_mlab_nodes, self.num_sites_y, self.SIG_IDX, self.SLICE_CAPACITY,
                    mlab_displacements, self.site_det_score, self.inst_curr_bestScoreImprov,
                    self.inst_next_bestScoreImprov, self.site_det_siteId, self.site_det_sig_idx,
                    self.site_det_sig, self.site_det_impl_lut, self.inst_curr_detSite,
                    self.inst_curr_bestSite, self.inst_next_detSite, self.inst_next_bestSite,
                    self.sites_with_special_nodes)

                logging.info("%d mlabs legalized with max and avg displacements: (%f, %f)"
                             % (self.num_mlab_nodes, mlab_displacements.max(), mlab_displacements.sum()/self.num_mlab_nodes))

                mlab_sites = self.site2addr_map[self.inst_curr_detSite[torch.where(self.is_mlab_node == 1)[0]].long()]
                self.is_mlab_site[mlab_sites.long()] = 1

            ## Initialize Site Neighbors ##
            cpu_site_curr_scl_score = torch.flatten(self.site_curr_scl_score).cpu()
            cpu_site_curr_scl_siteId = torch.flatten(self.site_curr_scl_siteId).cpu()
            cpu_site_curr_scl_validIdx = torch.flatten(self.site_curr_scl_validIdx).cpu()
            cpu_site_curr_scl_idx = self.site_curr_scl_idx.cpu()
            cpu_site_curr_scl_sig = torch.flatten(self.site_curr_scl_sig).cpu()
            cpu_site_curr_scl_sig_idx = torch.flatten(self.site_curr_scl_sig_idx).cpu()
            cpu_site_curr_scl_impl_lut = torch.flatten(self.site_curr_scl_impl_lut).cpu()
            cpu_site_nbrRanges = torch.flatten(self.site_nbrRanges).cpu()
            cpu_site_nbrRanges_idx = self.site_nbrRanges_idx.cpu()
            cpu_site_nbrList = torch.flatten(self.site_nbrList).cpu()
            cpu_site_nbr = torch.flatten(self.site_nbr).cpu()
            cpu_site_nbr_idx = self.site_nbr_idx.cpu()
            cpu_site_nbrGroup_idx = self.site_nbrGroup_idx.cpu()
            cpu_site_det_siteId = self.site_det_siteId.cpu()
            cpu_site_det_sig = torch.flatten(self.site_det_sig).cpu()
            cpu_site_det_sig_idx = self.site_det_sig_idx.cpu()
            cpu_site_det_impl_lut = torch.flatten(self.site_det_impl_lut).cpu()

            lut_ff_legalization_cpp.initSiteNbrs(
               pos.cpu(), wlPrecond.cpu(), torch.flatten(self.site_xy).cpu(), self.site_det_score.cpu(),
               sorted_node_idx.cpu(), self.node2fence_region_map.cpu(), torch.flatten(self.site_types).cpu(), 
               torch.flatten(self.spiral_accessor).cpu(), self.site2addr_map.cpu(), self.addr2site_map.cpu(),
               torch.flatten(self.flat_node2precluster_map).cpu(), self.flat_node2prclstrCount.cpu(),
               self.is_mlab_node.cpu(), self.is_mlab_site.cpu(), self.sites_with_special_nodes.cpu(), self.nbrDistEnd,
               self.nbrDistBeg, self.nbrDistIncr, self.lutId, self.ffId, self.sliceId, self.num_nodes,
               self.num_sites_x, self.num_sites_y, self.num_clb_sites, self.SCL_IDX, self.SIG_IDX,
               self.SLICE_CAPACITY, self.numGroups, self.maxList, spiralBegin, spiralEnd_maxD,
               cpu_site_curr_scl_score, cpu_site_curr_scl_siteId, cpu_site_curr_scl_validIdx,
               cpu_site_curr_scl_idx, cpu_site_curr_scl_sig, cpu_site_curr_scl_sig_idx,
               cpu_site_curr_scl_impl_lut, cpu_site_nbrRanges, cpu_site_nbrRanges_idx,
               cpu_site_nbrList, cpu_site_nbr,  cpu_site_nbr_idx, cpu_site_nbrGroup_idx, cpu_site_det_siteId,
               cpu_site_det_sig, cpu_site_det_sig_idx, cpu_site_det_impl_lut, self.num_threads)
               
            torch.flatten(self.site_curr_scl_score).data.copy_(cpu_site_curr_scl_score)
            torch.flatten(self.site_curr_scl_siteId).data.copy_(cpu_site_curr_scl_siteId)
            torch.flatten(self.site_curr_scl_validIdx).data.copy_(cpu_site_curr_scl_validIdx)
            self.site_curr_scl_idx.data.copy_(cpu_site_curr_scl_idx)
            torch.flatten(self.site_curr_scl_sig).data.copy_(cpu_site_curr_scl_sig)
            torch.flatten(self.site_curr_scl_sig_idx).data.copy_(cpu_site_curr_scl_sig_idx)
            torch.flatten(self.site_curr_scl_impl_lut).data.copy_(cpu_site_curr_scl_impl_lut)
            torch.flatten(self.site_nbrRanges).data.copy_(cpu_site_nbrRanges)
            self.site_nbrRanges_idx.data.copy_(cpu_site_nbrRanges_idx)
            torch.flatten(self.site_nbrList).data.copy_(cpu_site_nbrList.data)
            torch.flatten(self.site_nbr).data.copy_(cpu_site_nbr)
            self.site_nbr_idx.data.copy_(cpu_site_nbr_idx)
            self.site_nbrGroup_idx.data.copy_(cpu_site_nbrGroup_idx)
            self.site_det_siteId.data.copy_(cpu_site_det_siteId)
            torch.flatten(self.site_det_sig).data.copy_(cpu_site_det_sig)
            self.site_det_sig_idx.data.copy_(cpu_site_det_sig_idx)
            torch.flatten(self.site_det_impl_lut).data.copy_(cpu_site_det_impl_lut)

        else:
            lut_ff_legalization_cpp.initializeLG(
                pos, self.pin_offset_x, self.pin_offset_y, sorted_net_idx, sorted_node_map, sorted_node_idx,
                self.flat_net2pin_map, self.flat_net2pin_start_map, self.flop2ctrlSetId_map, self.flop_ctrlSets,
                self.node2fence_region_map, self.node2outpinIdx_map, self.pin2net_map, self.pin2node_map,
                self.pin_typeIds, self.net2pincount, self.is_mlab_node, preClusteringMaxDist, self.lutId,
                self.ffId, self.num_nets, self.num_nodes, self.num_threads,
                self.WLscoreMaxNetDegree, self.net_bbox, self.net_pinIdArrayX, self.net_pinIdArrayY,
                self.flat_node2precluster_map, self.flat_node2prclstrCount)

            if self.num_carry_chains > 0:

                #Legalize carry chains and initialize site neighbors accordingly
                lut_ff_legalization_cpp.legalizeCarryChain(
                    pos, torch.flatten(self.site_xy), wlPrecond, torch.flatten(self.spiral_accessor),
                    torch.flatten(self.site_types), self.site2addr_map, self.flat_cc2node_start_map,
                    self.flat_cc2node_map, spiralBegin, spiralEnd, self.num_sites_x, self.num_sites_y,
                    self.sliceId, self.SIG_IDX, self.SLICE_CAPACITY, self.num_carry_chains, self.lutsInSlice,
                    self.slice_minX, self.slice_maxX, self.slice_minY, self.slice_maxY, 
                    carry_chain_displacements, self.site_det_score, self.inst_curr_bestScoreImprov,
                    self.inst_next_bestScoreImprov, self.sites_with_special_nodes, self.inst_curr_detSite,
                    self.inst_curr_bestSite, self.inst_next_detSite, self.inst_next_bestSite,
                    self.site_det_siteId, self.site_det_sig, self.site_det_sig_idx,
                    self.site_det_impl_lut, self.num_threads)

                logging.info("%d carry-chains legalized with max and avg displacements: (%f, %f)" % 
                        (self.num_carry_chains, carry_chain_displacements.max(), carry_chain_displacements.sum()/self.num_carry_chains))

            #TODO - When mlabs are treated as a type of LUT
            ##Legalize mlabs if any
            if self.num_mlab_nodes > 0:

                lg_max_dist_init=self.nbrDistEnd
                lg_max_dist_incr=self.nbrDistIncr
                lg_flow_cost_scale=100.0

                #Remove already assigned slice sites if any
                rem_slice_sites_mask = compute_remaining_slice_sites(self.slice_sites, self.site_det_sig_idx, self.addr2site_map)
                num_sites = rem_slice_sites_mask.sum()
                num_total_nodes = pos.numel()//2

                locX = pos[:self.num_nodes][self.is_mlab_node.bool()].cpu().detach().numpy()
                locY = pos[num_total_nodes:num_total_nodes+self.num_nodes][self.is_mlab_node.bool()].cpu().detach().numpy()
                precondWL = wlPrecond[self.is_mlab_node.bool()].cpu().detach().numpy()

                movVal = np.zeros(2, dtype=np.float32).tolist()
                outLoc = np.zeros(2*self.num_mlab_nodes, dtype=np.float32).tolist()

                lut_ff_legalization_cpp.minCostFlow(locX, locY, num_sites, self.num_mlab_nodes, self.sliceSiteXYs[rem_slice_sites_mask].flatten(),
                        precondWL, lg_max_dist_init, lg_max_dist_incr, lg_flow_cost_scale, movVal, outLoc)

                outLoc=np.array(outLoc)
                mlab_locX = torch.from_numpy(outLoc[:self.num_mlab_nodes]).to(dtype=pos.dtype, device=self.device)
                mlab_locY = torch.from_numpy(outLoc[self.num_mlab_nodes:]).to(dtype=pos.dtype, device=self.device)

                mlab_displacements = torch.zeros(self.num_mlab_nodes, dtype=pos.dtype, device=self.device)

                lut_ff_legalization_cpp.legalizeMlab(pos, torch.flatten(self.site_xy),
                    mlab_locX, mlab_locY, self.mlab_indices, self.site2addr_map,
                    self.num_mlab_nodes, self.num_sites_y, self.SIG_IDX, self.SLICE_CAPACITY,
                    mlab_displacements, self.site_det_score, self.inst_curr_bestScoreImprov,
                    self.inst_next_bestScoreImprov, self.sites_with_special_nodes, self.inst_curr_detSite,
                    self.inst_curr_bestSite, self.inst_next_detSite, self.inst_next_bestSite,
                    self.site_det_siteId, self.site_det_sig, self.site_det_sig_idx,
                    self.site_det_impl_lut, self.num_threads)

                logging.info("%d mlabs legalized with max and avg displacements: (%f, %f)"
                             % (self.num_mlab_nodes, mlab_displacements.max(), mlab_displacements.sum()/self.num_mlab_nodes))

                mlab_sites = self.site2addr_map[self.inst_curr_detSite[torch.where(self.is_mlab_node == 1)[0]].long()]
                self.is_mlab_site[mlab_sites.long()] = 1

            ## Initialize Site Neighbors ##
            lut_ff_legalization_cpp.initSiteNbrs(pos, wlPrecond, torch.flatten(self.site_xy), self.site_det_score,
               sorted_node_idx, self.node2fence_region_map, torch.flatten(self.site_types), 
               torch.flatten(self.spiral_accessor), self.site2addr_map, self.addr2site_map,
               torch.flatten(self.flat_node2precluster_map), self.flat_node2prclstrCount, self.is_mlab_node, self.is_mlab_site,
               self.sites_with_special_nodes, self.nbrDistEnd, self.nbrDistBeg, self.nbrDistIncr, self.lutId,
               self.ffId, self.sliceId, self.num_nodes, self.num_sites_x, self.num_sites_y, self.num_clb_sites,
               self.SCL_IDX, self.SIG_IDX, self.SLICE_CAPACITY, self.numGroups, self.maxList, spiralBegin,
               spiralEnd_maxD, self.site_curr_scl_score, self.site_curr_scl_siteId, self.site_curr_scl_validIdx,
               self.site_curr_scl_idx, self.site_curr_scl_sig, self.site_curr_scl_sig_idx, self.site_curr_scl_impl_lut,
               self.site_nbrRanges, self.site_nbrRanges_idx, self.site_nbrList, self.site_nbr,  self.site_nbr_idx,
               self.site_nbrGroup_idx, self.site_det_siteId, self.site_det_sig, self.site_det_sig_idx,
               self.site_det_impl_lut, self.num_threads)
        
        #DBG
        #Preclustering Info
        preAll = (self.flat_node2prclstrCount[self.node2fence_region_map==self.lutId] > 1).sum().item()
        pre3 = (self.flat_node2prclstrCount[self.node2fence_region_map==self.lutId] > 2).sum().item()
        pre2 = preAll - pre3
        #print("# Precluster: ", preAll, " (", pre2, " + ", pre3, ")")
        #DBG
        print("Preclusters: %d (%d + %d) Initialization completed in %.3f seconds" % (preAll, pre2, pre3, time.time()-tt))
 
        #DBG
        spl_mask = self.special_nodes == 1
        if -1 in self.inst_curr_detSite[spl_mask]:
            print("ERROR: INCORRECT locations for special nodes after legalization - CHECK")

        #Carry-Chain Checker
        if self.num_carry_chains > 0:
            carry_chain_checker(self.flat_cc2node_start_map, self.flat_cc2node_map, self.inst_curr_detSite,
                        self.site2addr_map, self.site_det_impl_lut, self.num_sites_y,
                        self.lutsInSlice, self.num_carry_chains, self.device)
        #DBG

    def runDLIter(self, pos, wlPrecond, sorted_node_map, sorted_node_idx, sorted_net_map, sorted_net_idx, sorted_pin_map, 
                  activeStatus, illegalStatus, dlIter):
        maxDist = 5.0
        spiralBegin = 0
        spiralEnd = 2 * (int(maxDist) + 1) * int(maxDist) + 1
        minStableIter = 3
        minNeighbors = 10
        cumsum_curr_scl = torch.zeros(self.num_clb_sites, dtype=torch.int, device=self.device)
        sorted_clb_siteIds = torch.zeros_like(cumsum_curr_scl)
        validIndices_curr_scl = torch.ones_like(self.site_curr_scl_validIdx)
        validIndices_curr_scl *= -1

        if pos.is_cuda:
            lut_ff_legalization_cuda.runDLIter(pos, self.pin_offset_x, self.pin_offset_y,
                self.net_bbox, torch.flatten(self.site_xy), self.net_wts, self.net_pinIdArrayX,
                self.net_pinIdArrayY, torch.flatten(self.site_types), torch.flatten(self.spiral_accessor),
                self.node2fence_region_map, self.lut_flop_indices, self.flop2ctrlSetId_map,
                self.flop_ctrlSets, self.extended_ctrlSets, self.ext_ctrlSet_start_map,
                self.lut_type, self.flat_node2pin_start_map, self.flat_node2pin_map, self.node2outpinIdx_map,
                self.node2pincount, self.net2pincount, self.pin2net_map, self.pin_typeIds, self.flat_net2pin_start_map,
                self.pin2node_map, sorted_net_map, sorted_node_map, self.flat_node2prclstrCount,
                torch.flatten(self.flat_node2precluster_map), self.is_mlab_node, torch.flatten(self.site_nbrList),
                torch.flatten(self.site_nbrRanges), self.site_nbrRanges_idx, self.addr2site_map,
                self.site2addr_map, self.special_nodes, maxDist, self.xWirelenWt, self.yWirelenWt,
                self.wirelenImprovWt, self.extNetCountWt, self.num_sites_x, self.num_sites_y,
                self.num_clb_sites, self.num_lutflops, minStableIter, self.maxList, self.half_ctrl_mode,
                self.SLICE_CAPACITY, self.HALF_SLICE_CAPACITY, self.BLE_CAPACITY, self.NUM_BLE_PER_SLICE,
                minNeighbors, spiralBegin, spiralEnd, self.int_min_val, self.numGroups,
                self.netShareScoreMaxNetDegree, self.WLscoreMaxNetDegree,
                self.lutTypeInSliceUnit, self.lut_maxShared, self.CKSR_IN_CLB, self.CE_IN_CLB,
                self.SCL_IDX, self.PQ_IDX, self.SIG_IDX, self.lutId, self.ffId, self.sliceId,
                self.site_nbr_idx, self.site_nbr, self.site_nbrGroup_idx, self.site_curr_pq_top_idx,
                self.site_curr_pq_sig_idx, self.site_curr_pq_sig, self.site_curr_pq_idx, self.site_curr_stable,
                self.site_curr_pq_siteId,  self.site_curr_pq_validIdx, self.site_curr_pq_score,
                self.site_curr_pq_impl_lut, self.site_curr_pq_impl_ff, self.site_curr_pq_impl_cksr,
                self.site_curr_pq_impl_ce, self.site_curr_scl_score, self.site_curr_scl_siteId,
                self.site_curr_scl_idx, cumsum_curr_scl, self.site_curr_scl_validIdx, validIndices_curr_scl,
                self.site_curr_scl_sig_idx, self.site_curr_scl_sig, self.site_curr_scl_impl_lut,
                self.site_curr_scl_impl_ff, self.site_curr_scl_impl_cksr, self.site_curr_scl_impl_ce,
                self.site_next_pq_idx, self.site_next_pq_validIdx, self.site_next_pq_top_idx, self.site_next_pq_score, 
                self.site_next_pq_siteId, self.site_next_pq_sig_idx, self.site_next_pq_sig, self.site_next_pq_impl_lut, 
                self.site_next_pq_impl_ff, self.site_next_pq_impl_cksr, self.site_next_pq_impl_ce, self.site_next_scl_score,
                self.site_next_scl_siteId, self.site_next_scl_idx, self.site_next_scl_validIdx, self.site_next_scl_sig_idx, 
                self.site_next_scl_sig, self.site_next_scl_impl_lut, self.site_next_scl_impl_ff, self.site_next_scl_impl_cksr,
                self.site_next_scl_impl_ce, self.site_next_stable, self.site_det_score, self.site_det_siteId, self.site_det_sig_idx,
                self.site_det_sig, self.site_det_impl_lut, self.site_det_impl_ff, self.site_det_impl_cksr, self.site_det_impl_ce,
                self.inst_curr_detSite, self.inst_curr_bestScoreImprov, self.inst_curr_bestSite, self.inst_next_detSite,
                self.inst_next_bestScoreImprov, self.inst_next_bestSite, activeStatus, illegalStatus, self.inst_score_improv,
                self.site_score_improv, sorted_clb_siteIds)

        else:
            lut_ff_legalization_cpp.runDLIter(pos, self.pin_offset_x, self.pin_offset_y, self.net_bbox, self.net_pinIdArrayX,
                self.net_pinIdArrayY, torch.flatten(self.site_xy), self.node2fence_region_map, self.flop_ctrlSets,
                self.extended_ctrlSets, self.ext_ctrlSet_start_map, self.flop2ctrlSetId_map, self.lut_type,
                self.flat_node2pin_start_map, self.flat_node2pin_map, self.node2outpinIdx_map, self.node2pincount, self.net2pincount,
                self.pin2net_map, self.pin_typeIds, self.flat_net2pin_start_map, self.pin2node_map, self.flat_node2prclstrCount,
                torch.flatten(self.flat_node2precluster_map), self.is_mlab_node, self.is_mlab_site, torch.flatten(self.site_nbrList),
                torch.flatten(self.site_nbrRanges), self.site_nbrRanges_idx, sorted_node_map, sorted_net_map, self.net_wts,
                self.addr2site_map, self.special_nodes, self.num_sites_x, self.num_sites_y, self.num_clb_sites, minStableIter,
                self.maxList, self.half_ctrl_mode, self.SLICE_CAPACITY, self.HALF_SLICE_CAPACITY, self.BLE_CAPACITY,
                self.NUM_BLE_PER_SLICE, minNeighbors, self.numGroups, self.netShareScoreMaxNetDegree, self.WLscoreMaxNetDegree,
                self.lutTypeInSliceUnit, self.lut_maxShared, self.xWirelenWt, self.yWirelenWt, self.wirelenImprovWt,
                self.extNetCountWt, self.CKSR_IN_CLB, self.CE_IN_CLB, self.SCL_IDX, self.PQ_IDX, self.SIG_IDX, self.lutId,
                self.ffId, self.num_nodes, self.num_threads, self.site_nbr_idx, self.site_nbr, self.site_nbrGroup_idx,
                self.site_curr_pq_top_idx, self.site_curr_pq_sig_idx, self.site_curr_pq_sig, self.site_curr_pq_idx,
                self.site_curr_pq_validIdx, self.site_curr_stable, self.site_curr_pq_siteId, self.site_curr_pq_score,
                self.site_curr_pq_impl_lut, self.site_curr_pq_impl_ff, self.site_curr_pq_impl_cksr, self.site_curr_pq_impl_ce,
                self.site_curr_scl_score, self.site_curr_scl_siteId, self.site_curr_scl_idx, self.site_curr_scl_validIdx,
                self.site_curr_scl_sig_idx, self.site_curr_scl_sig, self.site_curr_scl_impl_lut, self.site_curr_scl_impl_ff,
                self.site_curr_scl_impl_cksr, self.site_curr_scl_impl_ce, self.site_next_pq_idx, self.site_next_pq_validIdx,
                self.site_next_pq_top_idx, self.site_next_pq_score, self.site_next_pq_siteId, self.site_next_pq_sig_idx,
                self.site_next_pq_sig, self.site_next_pq_impl_lut, self.site_next_pq_impl_ff, self.site_next_pq_impl_cksr,
                self.site_next_pq_impl_ce, self.site_next_scl_score, self.site_next_scl_siteId, self.site_next_scl_idx,
                self.site_next_scl_validIdx, self.site_next_scl_sig_idx, self.site_next_scl_sig, self.site_next_scl_impl_lut,
                self.site_next_scl_impl_ff, self.site_next_scl_impl_cksr, self.site_next_scl_impl_ce, self.site_next_stable,
                self.site_det_score, self.site_det_siteId, self.site_det_sig_idx, self.site_det_sig, self.site_det_impl_lut,
                self.site_det_impl_ff, self.site_det_impl_cksr, self.site_det_impl_ce, self.inst_curr_detSite,
                self.inst_curr_bestScoreImprov, self.inst_curr_bestSite, self.inst_next_detSite, self.inst_next_bestScoreImprov,
                self.inst_next_bestSite, activeStatus, illegalStatus)

        ####DBG
        print(dlIter,": ", (self.inst_curr_detSite[self.node2fence_region_map==self.lutId] > -1).sum().item()+(self.inst_curr_detSite[self.node2fence_region_map==self.ffId] > -1).sum().item(), "/", self.num_nodes)
        print("\tactive Status : ", activeStatus.sum().item())
        print("\tillegal Status : ", illegalStatus.sum().item())
        ##DBG

    def ripUP_Greedy_slotAssign(self, pos, wlPrecond, node_z, sorted_node_map, sorted_node_idx, sorted_net_map,
                    sorted_net_idx, sorted_pin_map, inst_areas):

        tt = time.time()
        spiralBegin = 0
        spiralEnd = self.spiral_accessor.shape[0] #Entire chip!
        ripupExpansion = 1
        greedyExpansion = 5
        slotAssignFlowWeightScale = 1000.0
        slotAssignFlowWeightIncr = 0.5

        updXloc = torch.ones(self.num_nodes, dtype=self.dtype, device=self.device)
        updXloc *= -1
        updYloc = torch.ones_like(updXloc)
        updYloc *= -1
        updZloc = torch.zeros(self.num_movable_nodes, dtype=torch.int, device=self.device)

        #Re-initialize preclustering Update first element as itself
        self.flat_node2precluster_map = torch.ones((self.num_nodes,3), dtype=torch.int, device=self.device)
        self.flat_node2precluster_map *= -1
        self.flat_node2precluster_map[:,0] = torch.arange(self.num_nodes, dtype=torch.int, device=self.device)
        self.flat_node2prclstrCount = torch.zeros(self.num_nodes, dtype=torch.int, device=self.device)
        self.flat_node2prclstrCount[self.lut_flop_mask] = 1

        #RipUp + Greedy Legalization
        rem_insts_mask = (self.inst_curr_detSite == -1)
        num_remInsts = rem_insts_mask.sum().item()
        rem_inst_areas = inst_areas[rem_insts_mask]
        rem_inst_ids = torch.arange(self.num_nodes, dtype=torch.int, device=self.device)[rem_insts_mask]

        if self.num_mlab_nodes > 0:
            self.sites_with_special_nodes = torch.logical_or(self.sites_with_special_nodes, self.is_mlab_site).to(torch.int32)

        if self.half_ctrl_mode == 1:
            #sorted node ids only comprise of remaining instances
            _, sorted_ids = torch.sort(rem_inst_areas, descending=True)
            sorted_remNode_idx = rem_inst_ids[sorted_ids]
            sorted_remNode_idx = sorted_remNode_idx.to(torch.int32)

            #sorted node map will consist of all instances sorted based on decreasing area
            _, sort_all_ids = torch.sort(inst_areas, descending=True)
            _, sorted_remNode_map = torch.sort(sort_all_ids)
            sorted_remNode_map = sorted_remNode_map.to(torch.int32)
        else:
            #Prioritize based on lut type and inst area
            inst_scores = 2*self.lut_type/self.lut_type.max()
            inst_scores += (inst_areas/inst_areas.max())
            rem_inst_scores = inst_scores[rem_insts_mask]
            #sorted node ids only comprise of remaining instances
            _, sorted_ids = torch.sort(rem_inst_scores, descending=True)
            sorted_remNode_idx = rem_inst_ids[sorted_ids]
            sorted_remNode_idx = sorted_remNode_idx.to(torch.int32)

            #sorted node map will consist of all instances sorted based on decreasing area
            _, sort_all_ids = torch.sort(inst_scores, descending=True)
            _, sorted_remNode_map = torch.sort(sort_all_ids)
            sorted_remNode_map = sorted_remNode_map.to(torch.int32)

        #DBG
        #print("RipUp & Greedy LG on ", num_remInsts, "insts (neighbors within", self.nbrDistEnd, "distance)")
        numFFs = (self.node2fence_region_map[rem_inst_ids.long()] == self.ffId).sum().item()
        numLUTs = rem_inst_ids.shape[0] - numFFs
        #print("RipUP & Greedy LG on ", num_remInsts, " insts (", numLUTs, " LUTs + ", numFFs, " FFs)")
        #DBG

        if pos.is_cuda:
            cpu_inst_curr_detSite = self.inst_curr_detSite.cpu()
            cpu_site_det_sig_idx = self.site_det_sig_idx.cpu()
            cpu_site_det_sig = torch.flatten(self.site_det_sig).cpu()
            cpu_site_det_impl_lut = torch.flatten(self.site_det_impl_lut).cpu()
            cpu_site_det_impl_ff = torch.flatten(self.site_det_impl_ff).cpu()
            cpu_site_det_impl_cksr = torch.flatten(self.site_det_impl_cksr).cpu()
            cpu_site_det_impl_ce = torch.flatten(self.site_det_impl_ce).cpu()
            cpu_site_det_siteId = self.site_det_siteId.cpu()
            cpu_site_det_score = self.site_det_score.cpu()
            cpu_node_x = updXloc.cpu()
            cpu_node_y = updYloc.cpu()
            cpu_node_z = updZloc.cpu()

            lut_ff_legalization_cpp.ripUp_SlotAssign(pos.cpu(), self.pin_offset_x.cpu(), self.pin_offset_y.cpu(),
                self.net_wts.cpu(), self.net_bbox.cpu(), inst_areas.cpu(), wlPrecond.cpu(),
                torch.flatten(self.site_xy).cpu(), self.net_pinIdArrayX.cpu(), self.net_pinIdArrayY.cpu(),
                torch.flatten(self.spiral_accessor).cpu(), self.node2fence_region_map.cpu(), self.lut_type.cpu(),
                torch.flatten(self.site_types).cpu(), self.node2pincount.cpu(), self.net2pincount.cpu(),
                self.pin2net_map.cpu(), self.pin2node_map.cpu(), self.pin_typeIds.cpu(),
                self.flop2ctrlSetId_map.cpu(), self.flop_ctrlSets.cpu(), self.extended_ctrlSets.cpu(),
                self.ext_ctrlSet_start_map.cpu(), self.flat_node2pin_start_map.cpu(),
                self.flat_node2pin_map.cpu(), self.flat_net2pin_start_map.cpu(), self.flat_node2prclstrCount.cpu(), 
                torch.flatten(self.flat_node2precluster_map).cpu(), sorted_remNode_map.cpu(), sorted_remNode_idx.cpu(),
                sorted_net_map.cpu(), self.node2outpinIdx_map.cpu(), self.flat_net2pin_map.cpu(), 
                self.addr2site_map.cpu(), self.site2addr_map.cpu(), self.sites_with_special_nodes.cpu(),
                self.special_nodes.cpu(), self.nbrDistEnd, self.xWirelenWt, self.yWirelenWt, self.extNetCountWt,
                self.wirelenImprovWt, slotAssignFlowWeightScale, slotAssignFlowWeightIncr, self.lutTypeInSliceUnit,
                self.lut_maxShared, num_remInsts, self.num_sites_x, self.num_sites_y, self.num_clb_sites, spiralBegin,
                spiralEnd, self.half_ctrl_mode, self.CKSR_IN_CLB, self.CE_IN_CLB, self.SLICE_CAPACITY,
                self.HALF_SLICE_CAPACITY, self.BLE_CAPACITY, self.NUM_BLE_PER_SLICE, self.NUM_BLE_PER_HALF_SLICE,
                self.netShareScoreMaxNetDegree, self.WLscoreMaxNetDegree, ripupExpansion, greedyExpansion, self.SIG_IDX,
                self.lutId, self.ffId, self.sliceId, self.num_threads,
                cpu_inst_curr_detSite, cpu_site_det_sig_idx, cpu_site_det_sig, cpu_site_det_impl_lut, cpu_site_det_impl_ff,
                cpu_site_det_impl_cksr, cpu_site_det_impl_ce, cpu_site_det_siteId, cpu_site_det_score,
                cpu_node_x, cpu_node_y, cpu_node_z)

            self.inst_curr_detSite.data.copy_(cpu_inst_curr_detSite.data)
            self.site_det_sig_idx.data.copy_(cpu_site_det_sig_idx.data)
            torch.flatten(self.site_det_sig).data.copy_(cpu_site_det_sig.data)
            torch.flatten(self.site_det_impl_lut).data.copy_(cpu_site_det_impl_lut.data)
            torch.flatten(self.site_det_impl_ff).data.copy_(cpu_site_det_impl_ff.data)
            torch.flatten(self.site_det_impl_cksr).data.copy_(cpu_site_det_impl_cksr.data)
            torch.flatten(self.site_det_impl_ce).data.copy_(cpu_site_det_impl_ce.data)
            self.site_det_siteId.data.copy_(cpu_site_det_siteId.data)
            self.site_det_score.data.copy_(cpu_site_det_score.data)
            updXloc.data.copy_(cpu_node_x.data)
            updYloc.data.copy_(cpu_node_y.data)
            updZloc.data.copy_(cpu_node_z.data)
        else:
            lut_ff_legalization_cpp.ripUp_SlotAssign(pos, self.pin_offset_x, self.pin_offset_y, self.net_wts, self.net_bbox, inst_areas, wlPrecond,
                torch.flatten(self.site_xy), self.net_pinIdArrayX, self.net_pinIdArrayY, torch.flatten(self.spiral_accessor), 
                self.node2fence_region_map, self.lut_type, torch.flatten(self.site_types), self.node2pincount, self.net2pincount,
                self.pin2net_map, self.pin2node_map, self.pin_typeIds, self.flop2ctrlSetId_map,
                self.flop_ctrlSets, self.extended_ctrlSets, self.ext_ctrlSet_start_map, self.flat_node2pin_start_map,
                self.flat_node2pin_map, self.flat_net2pin_start_map, self.flat_node2prclstrCount, torch.flatten(self.flat_node2precluster_map),
                sorted_remNode_map, sorted_remNode_idx, sorted_net_map, self.node2outpinIdx_map, self.flat_net2pin_map, 
                self.addr2site_map, self.site2addr_map, self.sites_with_special_nodes, self.special_nodes,
                self.nbrDistEnd, self.xWirelenWt, self.yWirelenWt, self.extNetCountWt, self.wirelenImprovWt, slotAssignFlowWeightScale,
                slotAssignFlowWeightIncr, self.lutTypeInSliceUnit, self.lut_maxShared, num_remInsts, self.num_sites_x, self.num_sites_y,
                self.num_clb_sites, spiralBegin, spiralEnd, self.half_ctrl_mode, self.CKSR_IN_CLB, self.CE_IN_CLB, self.SLICE_CAPACITY,
                self.HALF_SLICE_CAPACITY, self.BLE_CAPACITY, self.NUM_BLE_PER_SLICE, self.NUM_BLE_PER_HALF_SLICE,
                self.netShareScoreMaxNetDegree, self.WLscoreMaxNetDegree, ripupExpansion, greedyExpansion, self.SIG_IDX, 
                self.lutId, self.ffId, self.sliceId, self.num_threads,
                self.inst_curr_detSite, self.site_det_sig_idx, self.site_det_sig, self.site_det_impl_lut, self.site_det_impl_ff, 
                self.site_det_impl_cksr, self.site_det_impl_ce, self.site_det_siteId, self.site_det_score, updXloc, updYloc, updZloc)

        #Carry-Chain Checker
        if self.num_carry_chains > 0:
            carry_chain_checker_loc(self.flat_cc2node_start_map, self.flat_cc2node_map, updXloc, updYloc,
                    updZloc, self.HALF_SLICE_CAPACITY, self.lutsInSlice, self.num_carry_chains, self.device)

        totalNodes = int(len(pos)/2)
        node_z.data.copy_(updZloc)
        pos[:self.num_nodes].data.masked_scatter_(self.lut_flop_mask, updXloc[self.lut_flop_mask])
        pos[totalNodes:totalNodes+self.num_nodes].data.masked_scatter_(self.lut_flop_mask, updYloc[self.lut_flop_mask])

        ###Logic Utilization
        logic_util = 100 * (self.site_det_sig_idx > 0 ).sum().item() /self.num_clb_sites
        logging.info("Occupied Slices = %d, Total slices = %d and LOGIC UTILIZATION %.4f%%" % ((self.site_det_sig_idx > 0 ).sum().item(), self.num_clb_sites, logic_util))
        print("RipUP & Greedy LG on %d insts (%d LUTs + %d FFs) takes %.3f seconds" % (num_remInsts, numLUTs, numFFs, time.time()-tt))

        return pos

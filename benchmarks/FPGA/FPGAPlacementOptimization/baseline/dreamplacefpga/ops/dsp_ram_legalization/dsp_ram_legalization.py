'''
@File: dsp_ram_legalization.py
@Author: Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
@Date: May 2023
'''
import math
import torch
from torch import nn
from torch.autograd import Function
import numpy as np
import pdb 

import dreamplacefpga.ops.dsp_ram_legalization.legalize_cpp as legalize_cpp
import dreamplacefpga.configure as configure

import logging
logger = logging.getLogger(__name__)

class LegalizeDSPRAMFunction(Function):
    @staticmethod
    def legalize(pos, placedb, region_id, model):
        """
        @brief legalize DSP/RAM at the end of Global Placement
        @param pos X/Y locations of all instances locX ndarray
        @param placedb Placement Database
        @param region_id Instance type identifier
        @param model Use for region mask and wirelength preconditioner
        @param num_nodes Instance count
        @param num_sites Instance site count
        @param sites Instance site ndarray 
        @param precondWL Instance wirelength preconditioner ndarray 
        @param dInit lg_max_dist_init
        @param dIncr lg_max_dist_incr
        @param fScale lg_flow_cost_scale
        @param movVal Maximum & Average Instance movement (list)
        @param outLoc Legalized Instance locations list - {x0, x1, ... xn, y0, y1, ... yn} 
        """
        lg_max_dist_init=10.0
        lg_max_dist_incr=10.0
        lg_flow_cost_scale=100.0
        numNodes = pos.numel()//2
        comp_id = placedb.rsrc2compId_map[region_id]
        num_inst = placedb.num_movable_nodes_fence_region[comp_id]
        outLoc = np.zeros(2*num_inst, dtype=np.float32).tolist()

        if region_id == placedb.rDSPIdx:
            mask = model.data_collections.dsp_mask
            sites = placedb.dspSiteXYs
        else:
            if region_id == placedb.rBRAMIdx or region_id == placedb.rM9KIdx:
                mask = model.data_collections.ram0_mask
                sites = placedb.ramSite0XYs
            elif region_id == placedb.rM144KIdx:
                mask = model.data_collections.ram1_mask
                sites = placedb.ramSite1XYs
        
        locX = pos[:placedb.num_physical_nodes][mask].cpu().detach().numpy()
        locY = pos[numNodes:numNodes+placedb.num_physical_nodes][mask].cpu().detach().numpy()

        num_sites = len(sites)
        precondWL = model.precondWL[:placedb.num_physical_nodes][mask].cpu().detach().numpy()
        movVal = np.zeros(2, dtype=np.float32).tolist()

        #Use auction algorithm
        if placedb.sliceFF_ctrl_mode != "HALF" or num_inst > 0.8*num_sites:
            # Assign num_sites as N for auction algorithm that employs an N->N mapping
            cost = torch.ones(num_sites*num_sites, dtype=pos.dtype, device=pos.device)
            cost *= -10000.0
            locations = torch.ones(num_sites, dtype=torch.int, device=pos.device)
            locations *= -1
            displacement = torch.zeros(num_inst, dtype=pos.dtype, device=pos.device)
            lg_sites = torch.from_numpy(sites.flatten()).to(pos.device)
            posX = pos[:placedb.num_physical_nodes][mask].data
            posY = pos[numNodes:numNodes+placedb.num_physical_nodes][mask].data
            precond = model.precondWL[:placedb.num_physical_nodes][mask]
            diff = num_sites - num_inst
            if diff > 0:
                tmp_diff = torch.zeros(diff, dtype=pos.dtype, device=pos.device)
                posX = torch.cat((posX, tmp_diff), 0)
                posY = torch.cat((posY, tmp_diff), 0)
                tmp_diff += 1.0
                precond = torch.cat((precond, tmp_diff), 0)

            if pos.is_cuda:
                cpu_locations = locations.cpu()
                cpu_displacement = displacement.cpu()
                legalize_cpp.legalize_auction(posX.cpu(), posY.cpu(), lg_sites.cpu(),
                        precond.cpu(), num_inst, num_sites, cost.cpu(), cpu_displacement,
                        cpu_locations)
                locations.data.copy_(cpu_locations.data)
                displacement.data.copy_(cpu_displacement.data)
            else:
                legalize_cpp.legalize_auction(posX, posY, lg_sites, precond,
                            num_inst, num_sites, cost, displacement, locations)
            
            outLoc[:num_inst] = sites[locations[:num_inst].cpu().detach().numpy()][:,0]
            outLoc[num_inst:] = sites[locations[:num_inst].cpu().detach().numpy()][:,1]
            outLoc = np.array(outLoc)
            movVal[0] = displacement.max().item()
            movVal[1] = displacement.mean().item()
        else:
            legalize_cpp.legalize(locX, locY, num_inst, num_sites, sites.flatten(), precondWL, lg_max_dist_init, lg_max_dist_incr, lg_flow_cost_scale, movVal, outLoc)
            outLoc = np.array(outLoc)

        updLoc = torch.from_numpy(outLoc).to(dtype=pos.dtype, device=pos.device)
        pos.data[:placedb.num_physical_nodes].masked_scatter_(mask, updLoc[:num_inst])
        pos.data[numNodes:numNodes+placedb.num_physical_nodes].masked_scatter_(mask, updLoc[num_inst:])

        return movVal 

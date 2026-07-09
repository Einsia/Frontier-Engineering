##
# @file   electric_potential.py
# @Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
# @Date: Oct 2020
# @brief  electric potential according to e-place (http://cseweb.ucsd.edu/~jlu/papers/eplace-todaes14/paper.pdf)
#

import os
import sys
import math
import numpy as np
import time
import torch
from torch import nn
from torch.autograd import Function
from torch.nn import functional as F
import logging

import dreamplacefpga.ops.dct.discrete_spectral_transform as discrete_spectral_transform

import dreamplacefpga.ops.dct.dct2_fft2 as dct
from dreamplacefpga.ops.dct.discrete_spectral_transform import get_exact_expk as precompute_expk

from dreamplacefpga.ops.electric_potential.electric_overflow import ElectricDensityMapFunction as ElectricDensityMapFunction
from dreamplacefpga.ops.electric_potential.electric_overflow import ElectricOverflow as ElectricOverflow

import dreamplacefpga.ops.electric_potential.electric_potential_cpp as electric_potential_cpp
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE":
    import dreamplacefpga.ops.electric_potential.electric_potential_cuda as electric_potential_cuda

import pdb
import matplotlib
matplotlib.use('Agg')

logger = logging.getLogger(__name__)

# global variable for plot
plot_count = 0


class ElectricPotentialFunction(Function):
    """
    @brief compute electric potential according to e-place.
    """
    @staticmethod
    def forward(
        ctx,
        pos,
        node_size_x_clamped,
        node_size_y_clamped,
        offset_x,
        offset_y,
        ratio,
        initial_density_map,
        xl,
        yl,
        xh,
        yh,
        bin_size_x,
        bin_size_y,
        num_movable_nodes,
        num_filler_nodes,
        num_bins_x,
        num_bins_y,
        deterministic_flag,
        sorted_node_map,
        exact_expkM=None,  # exp(-j*pi*k/M)
        exact_expkN=None,  # exp(-j*pi*k/N)
        inv_wu2_plus_wv2=None,  # 1.0/(wu^2 + wv^2)
        wu_by_wu2_plus_wv2_half=None,  # wu/(wu^2 + wv^2)/2
        wv_by_wu2_plus_wv2_half=None,  # wv/(wu^2 + wv^2)/2
        dct2=None,
        idct2=None,
        idct_idxst=None,
        idxst_idct=None,
        stretchRatio=None,
        lock_flag=None
    ):

        tt = time.time()

        # output consists of (density_cost, density_map, max_density)
        ctx.node_size_x_clamped = node_size_x_clamped
        ctx.node_size_y_clamped = node_size_y_clamped
        ctx.offset_x = offset_x
        ctx.offset_y = offset_y
        ctx.ratio = ratio
        ctx.xl = xl
        ctx.yl = yl
        ctx.xh = xh
        ctx.yh = yh
        ctx.bin_size_x = bin_size_x
        ctx.bin_size_y = bin_size_y
        ctx.num_movable_nodes = num_movable_nodes
        ctx.num_filler_nodes = num_filler_nodes
        ctx.num_bins_x = num_bins_x
        ctx.num_bins_y = num_bins_y
        ctx.pos = pos
        ctx.sorted_node_map = sorted_node_map
        ctx.stretchRatio = stretchRatio

        if lock_flag is None:
            ctx.lock_flag = False
        else:
            ctx.lock_flag = lock_flag
        #Return zero if there are no elements in this resourceType
        if (num_movable_nodes == 0 and num_filler_nodes == 0) or ctx.lock_flag:
            return torch.tensor(0, dtype=pos.dtype, device=pos.device)

        #If filler sizes become zero due to instance adjust area
        if node_size_x_clamped[-1] == 0 or node_size_y_clamped[-1] == 0:
            density_map = ElectricDensityMapFunction.forward(
                pos, node_size_x_clamped[:num_movable_nodes], node_size_y_clamped[:num_movable_nodes], 
                offset_x[:num_movable_nodes], offset_y[:num_movable_nodes],
                ratio[:num_movable_nodes], 
                initial_density_map,
                xl, yl, xh, yh, bin_size_x, bin_size_y,
                num_movable_nodes, 0, 
                num_bins_x, num_bins_y, 
                deterministic_flag, sorted_node_map, stretchRatio)
        else:
            density_map = ElectricDensityMapFunction.forward(
                pos, node_size_x_clamped, node_size_y_clamped, offset_x, offset_y,
                ratio, 
                initial_density_map,
                xl, yl, xh, yh, bin_size_x, bin_size_y,
                num_movable_nodes, num_filler_nodes, 
                num_bins_x, num_bins_y, 
                deterministic_flag, sorted_node_map, stretchRatio)

        # for DCT
        M = num_bins_x
        N = num_bins_y

        # wu and wv
        if inv_wu2_plus_wv2 is None:
            wu = torch.arange(M,
                              dtype=density_map.dtype,
                              device=density_map.device).mul(2 * np.pi /
                                                             M).view([M, 1])
            wv = torch.arange(N,
                              dtype=density_map.dtype,
                              device=density_map.device).mul(2 * np.pi /
                                                             N).view([1, N])
            wu2_plus_wv2 = wu.pow(2) + wv.pow(2)
            wu2_plus_wv2[0,
                         0] = 1.0  # avoid zero-division, it will be zeroed out
            inv_wu2_plus_wv2 = 1.0 / wu2_plus_wv2
            inv_wu2_plus_wv2[0, 0] = 0.0
            wu_by_wu2_plus_wv2_half = wu.mul(inv_wu2_plus_wv2).mul_(1. / 2)
            wv_by_wu2_plus_wv2_half = wv.mul(inv_wu2_plus_wv2).mul_(1. / 2)

        # compute auv
        density_map.mul_(1.0 / (ctx.bin_size_x * ctx.bin_size_y))

        #auv = discrete_spectral_transform.dct2_2N(density_map, expk0=exact_expkM, expk1=exact_expkN)
        auv = dct2.forward(density_map)

        # compute field xi
        auv_by_wu2_plus_wv2_wu = auv.mul(wu_by_wu2_plus_wv2_half)
        auv_by_wu2_plus_wv2_wv = auv.mul(wv_by_wu2_plus_wv2_half)

        ctx.field_map_x = idxst_idct.forward(auv_by_wu2_plus_wv2_wu)

        ctx.field_map_y = idct_idxst.forward(auv_by_wu2_plus_wv2_wv)

        auv_by_wu2_plus_wv2 = auv.mul(inv_wu2_plus_wv2)

        potential_map = idct2.forward(auv_by_wu2_plus_wv2)

        # compute energy
        energy = potential_map.mul(density_map).sum()
        return energy

    @staticmethod
    def backward(ctx, grad_pos):
        tt = time.time()

        #Return zero if there are no elements in this resourceType
        if (ctx.num_movable_nodes == 0 and ctx.num_filler_nodes == 0) or ctx.lock_flag:
            return None, None, None, None, \
                   None, None, None, None, \
                   None, None, None, None, \
                   None, None, None, None, \
                   None, None, None, None, \
                   None, None, None, None, \
                   None, None, None, None, \
                   None, None, None, None, \
                   None, None, None, None, \
                   None, None, None, None

        if grad_pos.is_cuda:
            output = -electric_potential_cuda.electric_force_fpga(
                grad_pos, ctx.num_bins_x, ctx.num_bins_y,
                ctx.field_map_x.view([-1]), ctx.field_map_y.view([-1]),
                ctx.pos, ctx.node_size_x_clamped,
                ctx.node_size_y_clamped, 
                ctx.bin_size_x, ctx.bin_size_y, ctx.num_movable_nodes,
                ctx.num_filler_nodes, ctx.sorted_node_map)
        else:
            output = -electric_potential_cpp.electric_force_fpga(
                grad_pos, ctx.num_bins_x, ctx.num_bins_y,
                ctx.field_map_x.view([-1]), ctx.field_map_y.view(
                    [-1]), ctx.pos, ctx.node_size_x_clamped,
                ctx.node_size_y_clamped, 
                ctx.ratio,
                ctx.bin_size_x, ctx.bin_size_y, ctx.num_movable_nodes,
                ctx.num_filler_nodes)
        return output, \
            None, None, None, None, \
            None, None, None, None, \
            None, None, None, None, \
            None, None, None, None, \
            None, None, None, None, \
            None, None, None, None, \
            None, None, None, None, \
            None, None, None, None, \
            None, None, None, None, \
            None, None, None


class ElectricPotential(ElectricOverflow):
    """
    @brief Compute electric potential according to e-place
    """
    def __init__(
        self,
        node_size_x,
        node_size_y,
        xl,
        yl,
        xh,
        yh,
        bin_size_x,
        bin_size_y,
        num_movable_nodes,
        num_terminals,
        num_filler_nodes,
        deterministic_flag,  # control whether to use deterministic routine
        sorted_node_map,
        region_id=None,
        fence_regions=None, # [n_subregion, 4] as dummy macros added to initial density. (xl,yl,xh,yh) rectangles
        node2fence_region_map=None,
        placedb=None,
        stretchRatio=None
        ):
        """
        @brief initialization
        Be aware that all scalars must be python type instead of tensors.
        Otherwise, GPU version can be weirdly slow.
        @param node_size_x cell width array consisting of movable cells, fixed cells, and filler cells in order
        @param node_size_y cell height array consisting of movable cells, fixed cells, and filler cells in order
        @param movable_macro_mask some large movable macros need to be scaled to avoid halos
        @param bin_center_x bin center x locations
        @param bin_center_y bin center y locations
        @param target_density target density
        @param xl left boundary
        @param yl bottom boundary
        @param xh right boundary
        @param yh top boundary
        @param bin_size_x bin width
        @param bin_size_y bin height
        @param num_movable_nodes number of movable cells
        @param num_terminals number of fixed cells
        @param num_filler_nodes number of filler cells
        @param padding bin padding to boundary of placement region
        @param deterministic_flag control whether to use deterministic routine
        @param fast_mode if true, only gradient is computed, while objective computation is skipped
        @param region_id id for fence region, from 0 to N if there are N fence regions
        @param fence_regions # [n_subregion, 4] as dummy macros added to initial density. (xl,yl,xh,yh) rectangles
        @param node2fence_region_map node to region id map, non fence region is set to INT_MAX
        @param placedb
        """

        if(region_id is not None):
            ### reconstruct data structure
            self.region_id = region_id
            self.comp_id = placedb.rsrc2compId_map[region_id]
            num_nodes = placedb.num_nodes
            self.fence_region_mask = node2fence_region_map[:num_movable_nodes] == region_id

            node_size_x = torch.cat([node_size_x[:num_movable_nodes][self.fence_region_mask],
                                    node_size_x[num_nodes-num_filler_nodes+placedb.filler_start_map[self.comp_id]:num_nodes-num_filler_nodes+placedb.filler_start_map[self.comp_id+1]]], 0)
            node_size_y = torch.cat([node_size_y[:num_movable_nodes][self.fence_region_mask],
                                    node_size_y[num_nodes-num_filler_nodes+placedb.filler_start_map[self.comp_id]:num_nodes-num_filler_nodes+placedb.filler_start_map[self.comp_id+1]]], 0)

            num_movable_nodes = (self.fence_region_mask).long().sum().item()
            num_filler_nodes = placedb.filler_start_map[self.comp_id+1]-placedb.filler_start_map[self.comp_id]
            ## sorted cell is recomputed
            sorted_node_map = torch.sort(node_size_x[:num_movable_nodes])[1].to(torch.int32)
            ## make pos mask for fast forward
            self.pos_mask = torch.zeros(2, placedb.num_nodes, dtype=torch.bool, device=node_size_x.device)
            self.pos_mask[0,:placedb.num_movable_nodes].masked_fill_(self.fence_region_mask, 1)
            self.pos_mask[1,:placedb.num_movable_nodes].masked_fill_(self.fence_region_mask, 1)
            self.pos_mask[:,placedb.num_nodes-placedb.num_filler_nodes+placedb.filler_start_map[self.comp_id]:placedb.num_nodes-placedb.num_filler_nodes+placedb.filler_start_map[self.comp_id+1]] = 1
            self.pos_mask = self.pos_mask.view(-1)

        super(ElectricPotential,
              self).__init__(node_size_x=node_size_x,
                             node_size_y=node_size_y,
                             xl=xl,
                             yl=yl,
                             xh=xh,
                             yh=yh,
                             bin_size_x=bin_size_x,
                             bin_size_y=bin_size_y,
                             num_movable_nodes=num_movable_nodes,
                             num_terminals=0,
                             num_filler_nodes=num_filler_nodes,
                             deterministic_flag=deterministic_flag,
                             sorted_node_map=sorted_node_map)
        self.fence_regions = fence_regions
        self.node2fence_region_map = node2fence_region_map
        self.placedb = placedb
        self.region_id = region_id
        self.fence_region_mask = node2fence_region_map == region_id
        ## set by build_density_op func
        self.filler_start_map = None
        self.filler_beg = None
        self.filler_end = None
        self.initial_density_map = None 
        self.lock_flag = False


    def reset(self, data_collections=None):
        """ Compute members derived from input
        """
        if data_collections is not None and self.region_id is not None:
            self.node_size_x = torch.cat([data_collections.node_size_x[:data_collections.num_movable_nodes][self.fence_region_mask[:data_collections.num_movable_nodes]],
                                     data_collections.node_size_x[data_collections.num_nodes-data_collections.num_filler_nodes+data_collections.filler_start_map[self.comp_id]:data_collections.num_nodes-data_collections.num_filler_nodes+data_collections.filler_start_map[self.comp_id+1]]], 0)
            self.node_size_y = torch.cat([data_collections.node_size_y[:data_collections.num_movable_nodes][self.fence_region_mask[:data_collections.num_movable_nodes]],
                                     data_collections.node_size_y[data_collections.num_nodes-data_collections.num_filler_nodes+data_collections.filler_start_map[self.comp_id]:data_collections.num_nodes-data_collections.num_filler_nodes+data_collections.filler_start_map[self.comp_id+1]]], 0)
            self.sorted_node_map = torch.sort(self.node_size_x[:(self.fence_region_mask).long().sum().item()])[1].to(torch.int32)

        super(ElectricPotential, self).reset()

    def setLockDSPRAM(self):
        """ Set computation for DSP/RAM to zero after legalization 
        """
        if self.region_id is not None and self.region_id in self.placedb.dsp_ram_rsrcIds:
            self.lock_flag = True

    def forward(self, pos, mode="density"):
        assert mode in {"density", "overflow"}, "Only support density mode or overflow mode"
        if(self.region_id is not None):
            ### reconstruct pos, only extract cells in this electric field
            pos = pos[self.pos_mask]

        if self.initial_density_map is None:
            num_nodes = pos.size(0)//2
            if(self.fence_regions is not None):
                self.initial_density_map = self.fence_regions
            else:
                pdb.set_trace() #Rachel: Should not reach here for FPGA
            #logger.info("fixed density map: average %g, max %g, bin area %g" %
            #            (self.initial_density_map.mean(),
            #             self.initial_density_map.max(),
            #             self.bin_size_x * self.bin_size_y))

            # expk
            M = self.num_bins_x
            N = self.num_bins_y
            self.exact_expkM = precompute_expk(M,
                                               dtype=pos.dtype,
                                               device=pos.device)
            self.exact_expkN = precompute_expk(N,
                                               dtype=pos.dtype,
                                               device=pos.device)

            # init dct2, idct2, idct_idxst, idxst_idct with expkM and expkN
            self.dct2 = dct.DCT2(self.exact_expkM, self.exact_expkN)
            self.idct2 = dct.IDCT2(self.exact_expkM, self.exact_expkN)
            self.idct_idxst = dct.IDCT_IDXST(self.exact_expkM,
                                             self.exact_expkN)
            self.idxst_idct = dct.IDXST_IDCT(self.exact_expkM,
                                             self.exact_expkN)

            ar = self.bin_size_x / self.bin_size_y * self.placedb.xWirelenWt / self.placedb.yWirelenWt
            # wu and wv
            wu = torch.arange(M, dtype=pos.dtype, device=pos.device).mul(
                2 * np.pi / M).view([M, 1])
            # scale wv because the aspect ratio of a bin may not be 1
            wv = torch.arange(N, dtype=pos.dtype, device=pos.device).mul(2*np.pi / N).view(
                                  [1, N]).mul_(ar)
            wu2_plus_wv2 = wu.pow(2) + wv.pow(2)
            wu2_plus_wv2[0,
                         0] = 1.0  # avoid zero-division, it will be zeroed out
            self.inv_wu2_plus_wv2 = 1.0 / wu2_plus_wv2
            self.inv_wu2_plus_wv2[0, 0] = 0.0
            self.wu_by_wu2_plus_wv2_half = wu.mul(self.inv_wu2_plus_wv2).mul_(
                1. / 2)
            self.wv_by_wu2_plus_wv2_half = wv.mul(self.inv_wu2_plus_wv2).mul_(
                1. / 2)

        if(mode == "density"):
            #print("Density computation for region: %d" %(self.region_id))
            return ElectricPotentialFunction.apply(
                pos, self.node_size_x_clamped, self.node_size_y_clamped,
                self.offset_x, self.offset_y, self.ratio, 
                self.initial_density_map, 
                self.xl, self.yl, self.xh, self.yh, self.bin_size_x,
                self.bin_size_y, self.num_movable_nodes, self.num_filler_nodes,
                self.num_bins_x, self.num_bins_y,
                self.deterministic_flag, self.sorted_node_map, self.exact_expkM,
                self.exact_expkN, self.inv_wu2_plus_wv2,
                self.wu_by_wu2_plus_wv2_half, self.wv_by_wu2_plus_wv2_half,
                self.dct2, self.idct2, self.idct_idxst, self.idxst_idct,
                math.sqrt(2.0), self.lock_flag)
        elif(mode == "overflow"):
            ### num_filler_nodes is set 0
            #Return zero if there are no elements in this resourceType
            if (self.num_movable_nodes == 0 and self.num_filler_nodes == 0) or self.lock_flag:
                return torch.tensor(0, dtype=pos.dtype, device=pos.device), torch.tensor(0, dtype=pos.dtype, device=pos.device)

            density_map = ElectricDensityMapFunction.forward(
                pos, self.node_size_x_clamped, self.node_size_y_clamped,
                self.offset_x, self.offset_y, self.ratio, 
                self.initial_density_map, 
                self.xl, self.yl, self.xh, self.yh, self.bin_size_x,
                self.bin_size_y, self.num_movable_nodes, 0,
                self.num_bins_x, self.num_bins_y,
                self.deterministic_flag, self.sorted_node_map,
                self.placedb.overflowInstDensityStretchRatio[self.comp_id])

            bin_area = self.bin_size_x * self.bin_size_y
            density_cost = (density_map - bin_area).clamp_(min=0.0).sum()

            return density_cost, density_map.max() / bin_area


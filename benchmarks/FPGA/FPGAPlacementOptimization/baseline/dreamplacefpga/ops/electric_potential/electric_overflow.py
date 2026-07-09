##
# @file   electric_overflow.py
# @Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
# @Date: Oct 2020
#

import math
import numpy as np
import torch
from torch import nn
from torch.autograd import Function
from torch.nn import functional as F

import dreamplacefpga.ops.electric_potential.electric_potential_cpp as electric_potential_cpp
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE":
    import dreamplacefpga.ops.electric_potential.electric_potential_cuda as electric_potential_cuda

import pdb
import matplotlib
matplotlib.use('Agg')
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt


class ElectricDensityMapFunction(Function):
    """
    @brief compute density overflow.
    @param ctx pytorch API to store data for backward proporgation
    @param pos location of cells, x and then y
    @param node_size_x_clamped stretched size, max(bin_size*sqrt2, node_size)
    @param node_size_y_clamped stretched size, max(bin_size*sqrt2, node_size)
    @param offset_x (stretched size - node_size) / 2
    @param offset_y (stretched size - node_size) / 2
    @param ratio node_size_x * node_size_y for FPGA
    @param initial_density_map density_map for fixed cells
    @param target_density target density
    @param xl left boundary
    @param yl lower boundary
    @param xh right boundary
    @param yh upper boundary
    @param bin_size_x bin width
    @param bin_size_x bin height
    @param num_movable_nodes number of movable cells
    @param num_filler_nodes number of filler cells
    @param padding bin padding to boundary of placement region
    @param padding_mask padding mask with 0 and 1 to indicate padding bins with padding regions to be 1
    @param num_bins_x number of bins in horizontal direction
    @param num_bins_y number of bins in vertical direction
    @param num_movable_impacted_bins_x number of impacted bins for any movable cell in x direction
    @param num_movable_impacted_bins_y number of impacted bins for any movable cell in y direction
    @param num_filler_impacted_bins_x number of impacted bins for any filler cell in x direction
    @param num_filler_impacted_bins_y number of impacted bins for any filler cell in y direction
    @param sorted_node_map the indices of the movable node map
    """
    @staticmethod
    def forward(
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
        stretchRatio):

        ##Rachel: Incorporate stretch ratio as a variable as it differs for Density/OVFL computation in FPGA
        targetHalfSizeX = 0.5 * stretchRatio * bin_size_x
        targetHalfSizeY = 0.5 * stretchRatio * bin_size_y

        if pos.is_cuda:
            output = electric_potential_cuda.density_map_fpga(
                pos.view(pos.numel()), node_size_x_clamped,
                node_size_y_clamped, offset_x, offset_y, ratio.mul(0.25),
                initial_density_map, xl, yl, xh,
                yh, bin_size_x, bin_size_y, num_movable_nodes,
                num_filler_nodes, num_bins_x, num_bins_y,
                deterministic_flag, sorted_node_map, targetHalfSizeX, targetHalfSizeY)
        else:
            output = electric_potential_cpp.density_map_fpga(
                pos.view(pos.numel()), node_size_x_clamped,
                node_size_y_clamped, offset_x, offset_y, ratio.mul(0.25),
                initial_density_map, xl, yl, xh, yh, bin_size_x, bin_size_y,
                targetHalfSizeX, targetHalfSizeY, num_movable_nodes, 
                num_filler_nodes, num_bins_x, num_bins_y,
                deterministic_flag)

        density_map = output.view([num_bins_x, num_bins_y])
        
        return density_map


class ElectricOverflow(nn.Module):
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
        fence_regions=None,
        stretchRatio=None):
        super(ElectricOverflow, self).__init__()
        self.node_size_x = node_size_x
        self.node_size_y = node_size_y

        self.xl = xl
        self.yl = yl
        self.xh = xh
        self.yh = yh
        self.bin_size_x = bin_size_x
        self.bin_size_y = bin_size_y
        self.num_movable_nodes = num_movable_nodes
        self.num_terminals = 0 
        self.num_filler_nodes = num_filler_nodes
        self.sorted_node_map = sorted_node_map

        self.deterministic_flag = deterministic_flag
        #Rachel: Include explicit stretchRatio as it varies for DSP/RAM for Density and OVFL computation
        self.stretchRatio = stretchRatio

        self.reset()
        # initial density_map due to fixed cells
        if fence_regions is not None:
            self.initial_density_map = fence_regions

    def reset(self, data_collections=None):
        sqrt2 = math.sqrt(2)
        # clamped means stretch a cell to bin size
        # clamped = max(bin_size*sqrt2, node_size)
        # offset means half of the stretch size
        # ratio means the original area over the stretched area
        self.node_size_x_clamped = self.node_size_x
        self.offset_x = self.node_size_x_clamped.mul(0.5)
        self.node_size_y_clamped = self.node_size_y
        self.offset_y = self.node_size_y_clamped.mul(0.5)
        self.ratio = self.node_size_x_clamped * self.node_size_y_clamped

        # compute maximum impacted bins
        self.num_bins_x = int(math.ceil((self.xh - self.xl) / self.bin_size_x))
        self.num_bins_y = int(math.ceil((self.yh - self.yl) / self.bin_size_y))

    def forward(self, pos):
        if self.initial_density_map is None:
            pdb.set_trace() #Rachel: Should not reach here for FPGA
        
        density_map = ElectricDensityMapFunction.forward(
            pos, self.node_size_x_clamped, self.node_size_y_clamped,
            self.offset_x, self.offset_y, self.ratio, 
            self.initial_density_map, 
            self.xl, self.yl, self.xh, self.yh, self.bin_size_x,
            self.bin_size_y, self.num_movable_nodes, self.num_filler_nodes,
            self.num_bins_x, self.num_bins_y,
            self.deterministic_flag, self.sorted_node_map, self.stretchRatio)

        bin_area = self.bin_size_x * self.bin_size_y
        density_cost = (density_map -
                        self.target_density * bin_area).clamp_(min=0.0).sum().unsqueeze(0)

        return density_cost, density_map.max().unsqueeze(0) / bin_area


def plot(plot_count, density_map, padding, name):
    """
    density map contour and heat map
    """
    density_map = density_map[padding:density_map.shape[0] - padding,
                              padding:density_map.shape[1] - padding]
    print("max density = %g @ %s" %
          (np.amax(density_map),
           np.unravel_index(np.argmax(density_map), density_map.shape)))
    print("mean density = %g" % (np.mean(density_map)))

    fig = plt.figure()
    ax = fig.gca(projection='3d')

    x = np.arange(density_map.shape[0])
    y = np.arange(density_map.shape[1])

    x, y = np.meshgrid(x, y)
    # looks like x and y should be swapped
    ax.plot_surface(y, x, density_map, alpha=0.8)

    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('density')

    # plt.tight_layout()
    plt.savefig(name + ".3d.png")
    plt.close()

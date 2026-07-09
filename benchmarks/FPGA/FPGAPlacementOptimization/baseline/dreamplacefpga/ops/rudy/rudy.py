'''
@File   rudy.py
@Author: Jake Gu (DREAMPlace), Rachel Selina (DREAMPlaceFPGA)
@Date   Apr 2023
'''

import math
import torch
from torch import nn
from torch.autograd import Function
import matplotlib.pyplot as plt
import pdb 

import dreamplacefpga.ops.rudy.rudy_cpp as rudy_cpp
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE":
    import dreamplacefpga.ops.rudy.rudy_cuda as rudy_cuda

class Rudy(nn.Module):
    def __init__(self,
                 netpin_start, flat_netpin, net_weights,
                 xl, xh, yl, yh,
                 num_bins_x, num_bins_y,
                 unit_horizontal_capacity, 
                 unit_vertical_capacity, 
                 deterministic_flag,
                 initial_horizontal_utilization_map=None, 
                 initial_vertical_utilization_map=None, 
                 num_threads=None
                 ):
        super(Rudy, self).__init__()
        self.netpin_start = netpin_start
        self.flat_netpin = flat_netpin
        self.net_weights = net_weights
        self.xl = xl
        self.yl = yl
        self.xh = xh
        self.yh = yh
        self.num_threads = num_threads
        self.num_bins_x = num_bins_x
        self.num_bins_y = num_bins_y
        self.bin_size_x = (xh - xl) / num_bins_x
        self.bin_size_y = (yh - yl) / num_bins_y

        # initialize parameters
        self.unit_horizontal_capacity = unit_horizontal_capacity 
        self.unit_vertical_capacity = unit_vertical_capacity 

        self.deterministic_flag = deterministic_flag

        self.initial_horizontal_utilization_map = initial_horizontal_utilization_map 
        self.initial_vertical_utilization_map = initial_vertical_utilization_map 
        
        #plt.imsave("rudy_initial.png", (self.initial_horizontal_utilization_map + self.initial_vertical_utilization_map).data.cpu().numpy().T, origin='lower')

    def forward(self, pin_pos):
        horizontal_utilization_map = torch.zeros((self.num_bins_x, self.num_bins_y), dtype=pin_pos.dtype, device=pin_pos.device)
        vertical_utilization_map = torch.zeros_like(horizontal_utilization_map)
        if pin_pos.is_cuda:
            rudy_cuda.forward(
                    pin_pos,
                    self.netpin_start,
                    self.flat_netpin,
                    self.net_weights,
                    self.bin_size_x,
                    self.bin_size_y,
                    self.xl,
                    self.yl,
                    self.xh,
                    self.yh,
                    self.num_bins_x,
                    self.num_bins_y, 
                    self.deterministic_flag,
                    horizontal_utilization_map, 
                    vertical_utilization_map
                    )
        else:
            rudy_cpp.forward(
                    pin_pos,
                    self.netpin_start,
                    self.flat_netpin,
                    self.net_weights,
                    self.bin_size_x,
                    self.bin_size_y,
                    self.xl,
                    self.yl,
                    self.xh,
                    self.yh,
                    self.num_bins_x,
                    self.num_bins_y,
                    self.num_threads, 
                    self.deterministic_flag,
                    horizontal_utilization_map, 
                    vertical_utilization_map
                    )

        # convert demand to utilization in each bin
        bin_area = self.bin_size_x * self.bin_size_y 
        horizontal_utilization_map.mul_(1 / (bin_area * self.unit_horizontal_capacity))
        vertical_utilization_map.mul_(1 / (bin_area * self.unit_vertical_capacity))

        # infinity norm
        route_utilization_map = torch.max(horizontal_utilization_map.abs_(), vertical_utilization_map.abs_())

        return route_utilization_map


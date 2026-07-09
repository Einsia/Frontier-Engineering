##
# @file   hpwl.py
# @author Yibo Lin (DREAMPlace) Rachel Selina (DREAMPlaceFPGA)
# @date   May 2023
#

import torch
from torch.autograd import Function
from torch import nn
import numpy as np 
import pdb 
import time

import dreamplacefpga.ops.hpwl.hpwl_cpp as hpwl_cpp
import dreamplacefpga.ops.hpwl.hpwl_cpp_atomic as hpwl_cpp_atomic
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE": 
    import dreamplacefpga.ops.hpwl.hpwl_cuda as hpwl_cuda
    import dreamplacefpga.ops.hpwl.hpwl_cuda_atomic as hpwl_cuda_atomic

class HPWLFunction(Function):
    """compute half-perimeter wirelength.
    @param pos pin location (x array, y array), not cell location 
    @param flat_netpin flat netpin map, length of #pins 
    @param netpin_start starting index in netpin map for each net, length of #nets+1, the last entry is #pins  
    @param net_weights weight of nets 
    @param net_mask a boolean mask containing whether a net should be computed 
    @param pin2net_map pin2net map, second set of options 
    """
    @staticmethod
    def forward(ctx, pos, flat_netpin, netpin_start, net_weights, 
            net_weights_x, net_mask, net_bounding_box_min, net_bounding_box_max,
             xWeight, yWeight, num_threads):

        output = pos.new_empty(1)
        if pos.is_cuda:
            output = hpwl_cuda.forward(pos.view(pos.numel()), flat_netpin, netpin_start, net_weights, net_mask)
            return (net_weights_x*output[0]).sum()*xWeight + (net_weights*output[1]).sum()*yWeight
        else:
            output = hpwl_cpp.forward(pos.view(pos.numel()), flat_netpin, netpin_start, net_weights, 
                        net_weights_x, net_mask, xWeight, yWeight, num_threads)
            return output 

class HPWLAtomicFunction(Function):
    """compute half-perimeter wirelength using atomic max/min.
    @param pos pin location (x array, y array), not cell location 
    @param pin2net_map pin2net map, second set of options 
    @param net_weights weight of nets 
    @param net_mask a boolean mask containing whether a net should be computed 
    """
    @staticmethod
    def forward(ctx, pos, pin2net_map, net_weights, net_weights_x, net_mask, xWeight, yWeight):

        output = pos.new_empty(1)
        if pos.is_cuda:
            output = hpwl_cuda_atomic.forward(pos.view(pos.numel()), pin2net_map, net_weights, net_mask)
            return ((net_weights_x*output[0]).sum()*xWeight + (net_weights*output[1]).sum()*yWeight).sum().mul_(1.0/1000)
        else:
            output = hpwl_cpp_atomic.forward(pos.view(pos.numel()), pin2net_map, net_weights, net_mask)
            return ((net_weights_x*output[0]).sum()*xWeight + (net_weights*output[1]).sum()*yWeight).sum()

class HPWL(nn.Module):
    """ 
    @brief Compute half-perimeter wirelength. 
    Support two algoriths: net-by-net and atomic. 
    Different parameters are required for different algorithms. 
    """
    def __init__(self, placedb=None, flat_netpin=None, netpin_start=None, pin2net_map=None, net_weights=None,
             num_carry_chains=None, cc_net_weight=None, dir_net_weight=None, net_mask=None, net_bounding_box_min=None,
             net_bounding_box_max=None, num_threads=None, algorithm='atomic'):
        """
        @brief initialization 
        @param flat_netpin flat netpin map, length of #pins 
        @param netpin_start starting index in netpin map for each net, length of #nets+1, the last entry is #pins  
        @param pin2net_map pin2net map 
        @param net_weights weight of nets 
        @param net_mask whether to compute wirelength, 1 means to compute, 0 means to ignore  
        @param algorithm must be net-by-net | atomic
        """
        super(HPWL, self).__init__()
        assert net_mask is not None, "net_mask is a requried parameter"
        if algorithm == 'net-by-net':
            assert flat_netpin is not None and netpin_start is not None, "flat_netpin, netpin_start are requried parameters for algorithm net-by-net"
        elif algorithm == 'atomic':
            assert pin2net_map is not None, "pin2net_map is required for algorithm atomic"
        self.xWeight = placedb.xWirelenWt
        self.yWeight = placedb.yWirelenWt
        self.flat_netpin = flat_netpin 
        self.netpin_start = netpin_start
        self.pin2net_map = pin2net_map 
        self.net_weights = net_weights
        self.net_weights_x = net_weights.detach().clone()
        self.num_carry_chains = num_carry_chains
        self.cc_net_weight = cc_net_weight
        self.dir_net_weight = dir_net_weight
        self.net_mask = net_mask 
        self.algorithm = algorithm
        self.num_threads = num_threads
        self.net_bounding_box_min = net_bounding_box_min
        self.net_bounding_box_max = net_bounding_box_max

        #Weight x direction 50% more than y for carry chains
        if self.num_carry_chains > 0 and self.cc_net_weight > 1.0 and self.dir_net_weight:
            self.net_weights_x[self.net_weights_x == cc_net_weight] = 1.5*cc_net_weight

    def forward(self, pos): 
        if self.algorithm == 'net-by-net': 
            return HPWLFunction.apply(pos, 
                    self.flat_netpin, 
                    self.netpin_start, 
                    self.net_weights, 
                    self.net_weights_x, 
                    self.net_mask, 
                    self.net_bounding_box_min,
                    self.net_bounding_box_max,
                    self.xWeight,
                    self.yWeight,
                    self.num_threads
                    )
        elif self.algorithm == 'atomic':
            return HPWLAtomicFunction.apply(pos, 
                    self.pin2net_map, 
                    self.net_weights,
                    self.net_weights_x,
                    self.net_mask,
                    self.xWeight,
                    self.yWeight
                    )

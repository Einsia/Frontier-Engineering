##
# @file   precondWL.py
# @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Nov 2020
#

import torch
from torch.autograd import Function
from torch import nn
import numpy as np 
import pdb 
import time

import dreamplacefpga.ops.precondWL.precondWL_cpp as precondWL_cpp
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE": 
    import dreamplacefpga.ops.precondWL.precondWL_cuda as precondWL_cuda

class PrecondWL(nn.Module):
    """ 
    @brief Compute wirelength preconditioner. 
    """
    def __init__(self, flat_node2pin_start, flat_node2pin, pin2net_map, flat_net2pin, net_weights, num_nodes, num_movable_nodes, device, num_threads):
        """
        @brief initialization 
        @param flat_node2pin_start_map 
        @param flat_node2pin_map node to pin map
        @param flat_netpin flat netpin map, length of #pins 
        @param pin2net_map pin to net map
        @param net_weights weight of nets 
        @param num_nodes 
        @param num_threads
        """
        super(PrecondWL, self).__init__()
        self.flat_node2pin_start=flat_node2pin_start
        self.flat_node2pin=flat_node2pin
        self.flat_net2pin=flat_net2pin
        self.pin2net_map=pin2net_map
        self.net_weights=net_weights
        self.num_nodes=num_nodes
        self.num_movable_nodes=num_movable_nodes
        self.num_threads=num_threads
        self.device=device

    def forward(self): 
        out = torch.zeros(self.num_nodes, dtype=torch.float32, device=self.device)
        ##TODO - Temporary fix expecting net_weights to be empty
        if self.net_weights.shape == []:
            net_weights = torch.ones(self.num_nodes, dtype=torch.float32, device=self.device)
        else:
            net_weights = torch.clamp(self.net_weights, min=1.0)
        
        if out.is_cuda:
            precondWL_cuda.forward(
                                   self.flat_node2pin_start, 
                                   self.flat_node2pin, 
                                   self.pin2net_map, 
                                   self.flat_net2pin, 
                                   net_weights,
                                   self.num_movable_nodes,
                                   out)
        else:
            precondWL_cpp.forward(
                                  net_weights,
                                  self.flat_node2pin_start, 
                                  self.flat_node2pin, 
                                  self.flat_net2pin, 
                                  self.pin2net_map, 
                                  self.num_movable_nodes, 
                                  self.num_threads, 
                                  out)
        return out


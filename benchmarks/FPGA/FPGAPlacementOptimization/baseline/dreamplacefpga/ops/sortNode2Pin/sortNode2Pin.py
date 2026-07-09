##
# @file   sortNode2Pin.py
# @author Rachel Selina (DREAMPlaceFPGA-PL)
# @date   Nov 2021
#

import torch
from torch.autograd import Function
from torch import nn
import numpy as np 
import pdb 
import time

import dreamplacefpga.ops.sortNode2Pin.sortNode2Pin_cpp as sortNode2Pin_cpp
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE": 
    import dreamplacefpga.ops.sortNode2Pin.sortNode2Pin_cuda as sortNode2Pin_cuda

class SortNode2Pin(nn.Module):
    """ 
    @brief Compute wirelength preconditioner. 
    """
    def __init__(self, flat_node2pin_start, flat_node2pin, num_nodes, device, num_threads):
        """
        @brief initialization 
        @param flat_node2pin_start_map 
        @param flat_node2pin_map node to pin map
        @param num_nodes 
        @param num_threads
        """
        super(SortNode2Pin, self).__init__()
        self.flat_node2pin_start=flat_node2pin_start
        self.flat_node2pin=flat_node2pin
        self.num_nodes=num_nodes
        self.device=device
        self.num_threads = num_threads

    def forward(self, sorted_pin_map): 
        node2pinId = torch.zeros(self.num_nodes, dtype=torch.int32, device=self.device)
        
        if node2pinId.is_cuda:
            sortNode2Pin_cuda.forward(
                                      self.flat_node2pin_start, 
                                      self.flat_node2pin, 
                                      sorted_pin_map,
                                      self.num_nodes,
                                      node2pinId)
        else:
            sortNode2Pin_cpp.forward(
                                     self.flat_node2pin_start, 
                                     self.flat_node2pin, 
                                     sorted_pin_map,
                                     self.num_nodes, 
                                     self.num_threads, 
                                     node2pinId)

        return node2pinId


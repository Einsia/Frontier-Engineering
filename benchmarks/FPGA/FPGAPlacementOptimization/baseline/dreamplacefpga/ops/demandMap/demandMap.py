##
# @file   demandMap.py
# @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Nov 2020
#

import torch
from torch.autograd import Function
from torch import nn
import numpy as np 
import pdb 
import time

import dreamplacefpga.ops.demandMap.demandMap_cpp as demandMap_cpp
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE": 
    import dreamplacefpga.ops.demandMap.demandMap_cuda as demandMap_cuda

class DemandMap(nn.Module):
    """ 
    @brief Build binCapMap and fixedDemandMap
    """
    def __init__(self, placedb, site_type_map, site_size_x, site_size_y,
                 deterministic_flag, device, num_threads):
        """
        @brief initialization 
        @param placedb 
        @param site_type_map
        @param site_size_x
        @param site_size_y
        @param deterministic_flag 
        @param device 
        @param num_threads
        """
        super(DemandMap, self).__init__()
        self.num_bins_x=placedb.num_bins_x
        self.num_bins_y=placedb.num_bins_y
        self.width=placedb.xh - placedb.xl
        self.height=placedb.yh - placedb.yl
        self.rsrc2compId_map=placedb.rsrc2compId_map
        self.comp2rsrcId_map=placedb.comp2rsrcId_map
        self.rsrc2siteMap = placedb.rsrc2siteMap
        self.rsrcType2IndexMap = placedb.rsrcType2indexMap
        self.siteType2IndexMap = placedb.siteType2indexMap
        self.node_count=placedb.node_count
        self.site_type_map=site_type_map
        self.site_size_x=site_size_x
        self.site_size_y=site_size_y
        self.deterministic_flag = deterministic_flag
        self.device=device
        self.num_threads = num_threads

    def forward(self): 
        numSiteTypes = len(self.siteType2IndexMap)+1
        binCapMap = torch.zeros((numSiteTypes, self.num_bins_x, self.num_bins_y), dtype=self.site_size_x.dtype, device=self.device)

        binW = self.width/self.num_bins_x
        binH = self.height/self.num_bins_y

        if binCapMap.is_cuda:
            demandMap_cuda.forward(
                                   self.site_type_map.flatten(), 
                                   self.site_size_x, 
                                   self.site_size_y, 
                                   self.num_bins_x,
                                   self.num_bins_y,
                                   self.width, 
                                   self.height, 
                                   binW, binH,
                                   numSiteTypes,
                                   self.num_bins_x*self.num_bins_y,
                                   binCapMap,
                                   self.deterministic_flag)
        else:
            demandMap_cpp.forward(
                                   self.site_type_map.flatten(), 
                                   self.site_size_x, 
                                   self.site_size_y, 
                                   self.num_bins_x,
                                   self.num_bins_y,
                                   self.width, 
                                   self.height, 
                                   numSiteTypes,
                                   binCapMap,
                                   self.num_threads,
                                   self.deterministic_flag)

        binArea = binW * binH
        binCapMap = binArea - binCapMap

        rsrcDemMap = torch.zeros((len(self.rsrcType2IndexMap),self.num_bins_x,self.num_bins_y), dtype=self.site_size_x.dtype, device=self.device)

        for rsrc, rsrcId in self.rsrcType2IndexMap.items():
            compId = self.rsrc2compId_map[rsrcId]
            if compId != -1:
                sId = self.siteType2IndexMap[self.rsrc2siteMap[rsrc]]
                rsrcDemMap[compId] = binCapMap[sId]

        out = []

        for idx in self.rsrc2compId_map:
            if idx != -1:
                out.append(rsrcDemMap[idx])

        return out

'''
@File: clustering_compatibility.py
@Author: Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
@Date: June 2023
'''
import math
import torch
from torch import nn
from torch.autograd import Function
import matplotlib.pyplot as plt
import pdb 

import dreamplacefpga.ops.clustering_compatibility.clustering_compatibility_cpp as clustering_compatibility_cpp
import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE":
    import dreamplacefpga.ops.clustering_compatibility.clustering_compatibility_cuda as clustering_compatibility_cuda

class LUTCompatibility(nn.Module):
    def __init__(self,
                 lut_indices, lut_type, node_size_x, node_size_y,
                 num_bins_x, num_bins_y, num_bins_l,
                 placedb, deterministic_flag,
                 num_threads
                 ):
        super(LUTCompatibility, self).__init__()
        self.lut_indices = lut_indices
        self.lut_type = lut_type
        self.node_size_x = node_size_x
        self.node_size_y = node_size_y
        self.num_threads = num_threads
        self.num_bins_x = num_bins_x
        self.num_bins_y = num_bins_y
        self.num_bins_l = num_bins_l
        self.xl = placedb.xl
        self.yl = placedb.yl
        self.xh = placedb.xh
        self.yh = placedb.yh
        self.inst_stddev_x = placedb.instDemStddevX
        self.inst_stddev_y = placedb.instDemStddevY
        self.inst_stddev_trunc = placedb.instDemStddevTrunc
        self.deterministic_flag = deterministic_flag
        self.lutFracturesMap = placedb.lutFracturesMap
        self.SLICE_CAPACITY = placedb.SLICE_CAPACITY
        self.maxLUTSize = placedb.lutTypeInSliceUnit
        self.subSlice_area = 1/placedb.HALF_SLICE_CAPACITY

        self.half_ctrl_mode = 0
        if placedb.sliceFF_ctrl_mode == "HALF":
            self.half_ctrl_mode = 1


    def forward(self, pos):
        lutType_DemMap = torch.zeros((self.num_bins_x, self.num_bins_y, self.num_bins_l), dtype=pos.dtype, device=pos.device)
        resource_areas = torch.zeros(len(self.node_size_x), dtype=pos.dtype, device=pos.device)

        ext_bin = max(round(self.inst_stddev_trunc - 0.5), 0)
        demandX = torch.zeros((2 * ext_bin + 1), dtype=pos.dtype, device=pos.device)
        demandY = torch.zeros_like(demandX)

        lut_fracture = torch.zeros((self.num_bins_l, self.num_bins_l), dtype=torch.int, device=pos.device)

        if self.half_ctrl_mode == 0:
            resource_areas[self.lut_indices.long()] = (self.node_size_x*self.node_size_y)[self.lut_indices.long()]
            #Set the LUTs one sizes smaller than maxLUTSize to also be subSlice_area
            val = self.maxLUTSize - 2
            large_lut_indices = torch.where(self.lut_type == val)[0]
            if (large_lut_indices.shape[0] > 0):
                resource_areas[large_lut_indices] = self.subSlice_area
            #Set the LUTs two sizes smaller than maxLUTSize to be 0.75xsubSlice_area
            val = self.maxLUTSize - 3
            large_lut_indices = torch.where(self.lut_type == val)[0]
            if (large_lut_indices.shape[0] > 0):
                resource_areas[large_lut_indices] = 0.75*self.subSlice_area
            return resource_areas

        for i in range(self.num_bins_l):
            lut_fracture[i][self.lutFracturesMap[i]] = 1

        if pos.is_cuda:
            areaMap = clustering_compatibility_cuda.lut_compatibility(
                    pos.view(pos.numel()),
                    self.lut_indices,
                    self.lut_type,
                    self.node_size_x,
                    self.node_size_y,
                    lut_fracture,
                    self.num_bins_x,
                    self.num_bins_y, 
                    self.num_bins_l, 
                    self.xl,
                    self.yl,
                    self.xh,
                    self.yh,
                    self.inst_stddev_x, 
                    self.inst_stddev_y, 
                    1.0/self.inst_stddev_x,
                    1.0/self.inst_stddev_y,
                    ext_bin,
                    self.inst_stddev_x * self.inst_stddev_y, 
                    1/math.sqrt(2.0),
                    self.deterministic_flag,
                    lutType_DemMap, 
                    resource_areas
                    )
        else:
            areaMap = clustering_compatibility_cpp.lut_compatibility(
                    pos.view(pos.numel()),
                    self.lut_indices,
                    self.lut_type,
                    self.node_size_x,
                    self.node_size_y,
                    lut_fracture,
                    self.num_bins_x,
                    self.num_bins_y, 
                    self.num_bins_l, 
                    self.num_threads, 
                    self.inst_stddev_x, 
                    self.inst_stddev_y, 
                    1.0/self.inst_stddev_x,
                    1.0/self.inst_stddev_y,
                    ext_bin,
                    self.inst_stddev_x * self.inst_stddev_y, 
                    1/math.sqrt(2.0),
                    demandX,
                    demandY,
                    lutType_DemMap, 
                    resource_areas
                    )

        # Include post-processing if any here
        resource_areas /= self.SLICE_CAPACITY

        return resource_areas


class FFCompatibility(nn.Module):
    def __init__(self,
                 flop_indices, flop_ctrlSets, node_size_x, node_size_y,
                 num_bins_x, num_bins_y, num_bins_ck, num_bins_ce,
                 placedb, deterministic_flag,
                 num_threads
                 ):
        super(FFCompatibility, self).__init__()
        self.flop_indices = flop_indices
        self.flop_ctrlSets = flop_ctrlSets
        self.node_size_x = node_size_x
        self.node_size_y = node_size_y
        self.num_bins_x = num_bins_x
        self.num_bins_y = num_bins_y
        self.num_bins_ck = num_bins_ck
        self.num_bins_ce = num_bins_ce
        self.num_threads = num_threads
        self.deterministic_flag = deterministic_flag
        self.xl = placedb.xl
        self.yl = placedb.yl
        self.xh = placedb.xh
        self.yh = placedb.yh
        self.inst_stddev_x = placedb.instDemStddevX 
        self.inst_stddev_y = placedb.instDemStddevY
        self.inst_stddev_trunc = placedb.instDemStddevTrunc
        self.SLICE_CAPACITY = placedb.SLICE_CAPACITY

        self.half_ctrl_mode = 0
        if placedb.sliceFF_ctrl_mode == "HALF":
            self.half_ctrl_mode = 1

    def forward(self, pos):
        resource_areas = torch.zeros(len(self.node_size_x), dtype=pos.dtype, device=pos.device)

        if self.half_ctrl_mode == 0 and self.num_bins_ck == 1:
            resource_areas[self.flop_indices.long()] = (self.node_size_x*self.node_size_y)[self.flop_indices.long()]
            return resource_areas

        flopType_DemMap = torch.zeros((self.num_bins_x, self.num_bins_y, self.num_bins_ck, self.num_bins_ce), dtype=pos.dtype, device=pos.device)

        ext_bin = max(round(self.inst_stddev_trunc - 0.5), 0)
        demandX = torch.zeros((2 * ext_bin + 1), dtype=pos.dtype, device=pos.device)
        demandY = torch.zeros_like(demandX)

        if pos.is_cuda:
            areaMap = clustering_compatibility_cuda.flop_compatibility(
                    pos.view(pos.numel()),
                    self.flop_indices,
                    self.flop_ctrlSets,
                    self.node_size_x,
                    self.node_size_y,
                    self.num_bins_x,
                    self.num_bins_y, 
                    self.num_bins_ck, 
                    self.num_bins_ce, 
                    self.xl,
                    self.yl,
                    self.xh,
                    self.yh,
                    self.inst_stddev_x, 
                    self.inst_stddev_y, 
                    1.0/self.inst_stddev_x,
                    1.0/self.inst_stddev_y,
                    ext_bin,
                    self.inst_stddev_x * self.inst_stddev_y, 
                    1/math.sqrt(2.0),
                    self.SLICE_CAPACITY,
                    self.deterministic_flag,
                    flopType_DemMap, 
                    resource_areas
                    )
        else:
            areaMap = clustering_compatibility_cpp.flop_compatibility(
                    pos.view(pos.numel()),
                    self.flop_indices,
                    self.flop_ctrlSets,
                    self.node_size_x,
                    self.node_size_y,
                    self.num_bins_x,
                    self.num_bins_y, 
                    self.num_bins_ck, 
                    self.num_bins_ce, 
                    self.num_threads, 
                    self.inst_stddev_x, 
                    self.inst_stddev_y, 
                    1.0/self.inst_stddev_x,
                    1.0/self.inst_stddev_y,
                    ext_bin,
                    self.inst_stddev_x * self.inst_stddev_y, 
                    1/math.sqrt(2.0),
                    self.SLICE_CAPACITY,
                    demandX,
                    demandY,
                    flopType_DemMap, 
                    resource_areas
                    )

        # Include post-processing if any here
        resource_areas /= self.SLICE_CAPACITY

        return resource_areas
 

##
# @file   draw_place.py
# @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Jan 2021
# @brief  Plot placement to an image 
#

import os 
import sys 
import torch 
from torch.autograd import Function

import dreamplacefpga.ops.draw_place.draw_place_cpp as draw_place_cpp
import dreamplacefpga.ops.draw_place.PlaceDrawer as PlaceDrawer 
import pdb
import numpy as np

class DrawPlaceFunction(Function):
    @staticmethod
    def forward(
            pos, 
            node_size_x, node_size_y, 
            pin_offset_x, pin_offset_y, 
            pin2node_map, 
            xl, yl, xh, yh, 
            site_width, row_height, 
            bin_size_x, bin_size_y, 
            num_movable_nodes, num_filler_nodes, 
            filename
            ):
        ret = draw_place_cpp.forward(
                pos, 
                node_size_x, node_size_y, 
                pin_offset_x, pin_offset_y, 
                pin2node_map, 
                xl, yl, xh, yh, 
                site_width, row_height, 
                bin_size_x, bin_size_y, 
                num_movable_nodes, num_filler_nodes, 
                filename
                )
        # if C/C++ API failed, try with python implementation 
        if not filename.endswith(".gds") and not ret:
            ret = PlaceDrawer.PlaceDrawer.forward(
                    pos, 
                    node_size_x, node_size_y, 
                    pin_offset_x, pin_offset_y, 
                    pin2node_map, 
                    xl, yl, xh, yh, 
                    site_width, row_height, 
                    bin_size_x, bin_size_y, 
                    num_movable_nodes, num_filler_nodes, 
                    filename
                    )
        return ret 

class DrawPlace(object):
    """ 
    @brief Draw placement
    """
    def __init__(self, placedb):
        """
        @brief initialization 
        """
        self.node_size_x = torch.from_numpy(placedb.node_size_x).float()
        self.node_size_y = torch.from_numpy(placedb.node_size_y).float()
        self.pin_offset_x = torch.FloatTensor(placedb.pin_offset_x).float()
        self.pin_offset_y = torch.FloatTensor(placedb.pin_offset_y).float()
        self.pin2node_map = torch.from_numpy(placedb.pin2node_map)
        self.xl = placedb.xl 
        self.yl = placedb.yl 
        self.xh = placedb.xh 
        self.yh = placedb.yh 
        self.site_width = placedb.width
        self.row_height = placedb.height 
        self.bin_size_x = placedb.bin_size_x 
        self.bin_size_y = placedb.bin_size_y
        self.num_movable_nodes = placedb.num_movable_nodes
        self.num_filler_nodes = placedb.num_filler_nodes

    def forward(self, pos, filename): 
        """ 
        @param pos cell locations, array of x locations and then y locations 
        @param filename suffix specifies the format 
        """
        return DrawPlaceFunction.forward(
                pos, 
                self.node_size_x, 
                self.node_size_y, 
                self.pin_offset_x, 
                self.pin_offset_y, 
                self.pin2node_map, 
                self.xl, 
                self.yl, 
                self.xh, 
                self.yh, 
                self.site_width, 
                self.row_height, 
                self.bin_size_x, 
                self.bin_size_y, 
                self.num_movable_nodes, 
                self.num_filler_nodes, 
                filename
                )

    def __call__(self, pos, filename):
        """
        @brief top API 
        @param pos cell locations, array of x locations and then y locations 
        @param filename suffix specifies the format 
        """
        return self.forward(pos, filename)

# FPGA version - Added by Rachel
class DrawPlaceFunctionFPGA(Function):
    @staticmethod
    def forward(
            pos, 
            node_size_x, node_size_y, 
            pin_offset_x, pin_offset_y, 
            pin2node_map, 
            xl, yl, xh, yh, 
            bin_size_x, bin_size_y, 
            num_physical_nodes, num_filler_nodes, 
            node2fence_region_map,
            is_cc_node,
            ffIdx, lutIdx, addIdx,
            bramIdx, m9kIdx, m144kIdx,
            dspIdx,
            ioIdx,pllIdx,
            filename
            ):
        ret = draw_place_cpp.fpga(
                pos, 
                node_size_x, node_size_y, 
                pin_offset_x, pin_offset_y, 
                pin2node_map, 
                xl, yl, xh, yh, 
                bin_size_x, bin_size_y, 
                num_physical_nodes, num_filler_nodes, 
                node2fence_region_map,
                is_cc_node,
                ffIdx, lutIdx, addIdx,
                bramIdx, m9kIdx, m144kIdx,
                dspIdx,
                ioIdx,pllIdx,
                filename
                )
        # if C/C++ API failed, try with python implementation 
        if not filename.endswith(".gds") and not ret:
            ret = PlaceDrawer.PlaceDrawer.forward(
                    pos, 
                    node_size_x, node_size_y, 
                    pin_offset_x, pin_offset_y, 
                    pin2node_map, 
                    xl, yl, xh, yh, 
                    site_width, row_height, 
                    bin_size_x, bin_size_y, 
                    num_movable_nodes, num_filler_nodes, 
                    filename
                    )
        return ret 

class DrawPlaceFPGA(object):
    """ 
    @brief Draw placement
    """
    def __init__(self, placedb):
        """
        @brief initialization 
        """
        if placedb.num_ccNodes > 0:
            self.is_cc_node = torch.from_numpy(placedb.is_cc_node)
            nodeSizeX = placedb.node_size_x
            nodeSizeX[:placedb.num_physical_nodes][placedb.is_cc_node == 1] = 0.5
            self.node_size_x = torch.from_numpy(nodeSizeX)
        else:
            self.is_cc_node = torch.zeros(placedb.num_physical_nodes, dtype=torch.int32)
            self.node_size_x = torch.from_numpy(placedb.node_size_x)
        self.node_size_y = torch.from_numpy(placedb.node_size_y)
        self.pin_offset_x = torch.from_numpy(placedb.pin_offset_x)
        self.pin_offset_y = torch.from_numpy(placedb.pin_offset_y)
        self.pin2node_map = torch.from_numpy(placedb.pin2node_map)
        self.xl = placedb.xl 
        self.yl = placedb.yl 
        self.xh = placedb.xh 
        self.yh = placedb.yh 
        self.bin_size_x = placedb.bin_size_x 
        self.bin_size_y = placedb.bin_size_y
        self.num_physical_nodes = placedb.num_physical_nodes
        self.num_filler_nodes = placedb.num_filler_nodes
        self.node2fence_region_map = torch.from_numpy(placedb.node2fence_region_map)
        self.fmask = torch.from_numpy(placedb.io_mask)
        self.node_x = torch.from_numpy(placedb.node_x)
        self.node_y = torch.from_numpy(placedb.node_y)
        self.num_ccNodes = placedb.num_ccNodes

        ##Use resource type identifier for color coding
        self.ffIdx = placedb.rFFIdx
        self.lutIdx = placedb.rLUTIdx
        self.addIdx = placedb.rADDIdx
        self.bramIdx = placedb.rBRAMIdx
        self.m9kIdx = placedb.rM9KIdx
        self.m144kIdx = placedb.rM144KIdx
        self.dspIdx = placedb.rDSPIdx
        self.ioIdx = placedb.rIOIdx
        self.pllIdx = placedb.rPLLIdx

    def forward(self, pos, filename): 
        """ 
        @param pos cell locations, array of x locations and then y locations 
        @param filename suffix specifies the format 
        """
        fillers = torch.tensor(np.zeros(self.num_filler_nodes)).bool()
        fmask = torch.cat((self.fmask,fillers,self.fmask, fillers),0)
        allLoc = torch.cat((self.node_x, fillers.to(dtype=pos.dtype), self.node_y, fillers.to(dtype=pos.dtype)),0)
        omask = ~fmask
        newpos = pos*omask.to(dtype=pos.dtype) + allLoc*fmask.to(dtype=pos.dtype) 

        return DrawPlaceFunctionFPGA.forward(
                newpos, self.node_size_x, self.node_size_y, 
                self.pin_offset_x,  self.pin_offset_y, 
                self.pin2node_map, self.xl, self.yl, 
                self.xh, self.yh, self.bin_size_x, 
                self.bin_size_y, self.num_physical_nodes, 
                self.num_filler_nodes, self.node2fence_region_map,
                self.is_cc_node, self.ffIdx, self.lutIdx,
                self.addIdx, self.bramIdx, self.m9kIdx,
                self.m144kIdx, self.dspIdx, self.ioIdx,
                self.pllIdx, filename)

    def __call__(self, pos, filename):
        """
        @brief top API 
        @param pos cell locations, array of x locations and then y locations 
        @param filename suffix specifies the format 
        """
        return self.forward(pos, filename)

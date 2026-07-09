##
# @file   PlaceDB.py
# @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Oct 2020
# @brief  FPGA placement database 
#

import sys
import os
import re
import math
import time 
import numpy as np 
import logging
import Params
import dreamplacefpga 
import dreamplacefpga.ops.place_io.place_io as place_io 
import pdb 
from enum import IntEnum 

datatypes = {
        'float32' : np.float32, 
        'float64' : np.float64
        }

class PlaceDBFPGA (object):
    """
    initialization
    To avoid the usage of list, flatten everything.  
    """
    def __init__(self):
        self.rawdb = None # raw placement database, a C++ object
        self.num_physical_nodes = 0 # number of real nodes, including movable nodes, terminals, and terminal_NIs
        self.node_names = [] # name of instances 
        self.node_name2id_map = {} # map instance name to instance id 
        self.node_types = [] # instance types 
        self.node_x = [] # site location
        self.node_y = [] # site location 
        self.node_z = [] # site specific location
        self.ctrlSets = [] #Used for Flops
        self.flat_ctrlSets = [] #Used for Flops
        self.flop2ctrlSetId_map = [] #Used for Flop to ctrlset Id map
        self.node_size_x = []# 1D array, cell width  
        self.node_size_y = []# 1D array, cell height
        self.resource_size_x = None# 1D array, resource type-based cell width  
        self.resource_size_y = None# 1D array, resource type-based cell height
        #Legalization
        self.spiral_accessor = []

        self.pin_names = [] # pin names 
        self.pin_types = [] # pin types 
        self.pin_offset_x = []# 1D array, pin offset x to its node 
        self.pin_offset_y = []# 1D array, pin offset y to its node 
        self.lg_pin_offset_x = []# 1D array, pin offset x to its node 
        self.lg_pin_offset_y = []# 1D array, pin offset y to its node 
        self.pin2nodeType_map = [] # 1D array, pin to node type map
        self.node2pin_map = [] # nested array of array to record pins in each instance 
        self.flat_node2pin_map = [] #Flattened array of node2pin_map
        self.flat_node2pin_start_map = [] #Contains start index for flat_node2pin_map
        self.pin2node_map = [] # map pin to node 

        self.net_names = [] # net names 
        self.net2pin_map = [] # nested array of array to record pins in each net 
        self.flat_net2pin_map = [] # flattend version of net2pin_map
        self.flat_net2pin_start_map = [] # starting point for flat_net2pin_map
        self.pin2net_map = None # map pin to net 

        self.num_bins_x = None# number of bins in horizontal direction 
        self.num_bins_y = None# number of bins in vertical direction 
        self.bin_size_x = None# bin width, currently 1 site  
        self.bin_size_y = None# bin height, currently 1 site  

        self.num_sites_x = None # number of sites in horizontal direction
        self.num_sites_y = None # number of sites in vertical direction 
        self.site_type_map = None # site type of each site 
        self.lg_siteXYs = None # site type of each site 
        self.dspSiteXYs = [] #Sites for DSP instances
        self.ramSite0XYs = [] #Sites for RAM instances
        self.ramSite1XYs = [] #Sites for RAM instances

        self.xWirelenWt = None #X-directed wirelength weight
        self.yWirelenWt = None #Y-directed wirelength weight
        self.baseWirelenGammaBinRatio = None # The base wirelenGamma is <this value> * average bin size
        self.instDemStddevTrunc = None # We truncate Gaussian distribution outside the instDemStddevTrunc * instDemStddev
        # Resource Area Parameters
        self.gpInstStddev = None 
        self.gpInstStddevTrunc = None 
        self.instDemStddevX = None
        self.instDemStddevY = None
        # Routability and pin density optimization parameters
        self.unitHoriRouteCap = 0
        self.unitVertRouteCap = 0
        self.unitPinCap = 0

        #Area type parameters
        self.filler_size_x = [] #Filler size X for each resourceType
        self.filler_size_y = [] #Filler size Y for each resourceType
        self.targetOverflow = [] #Target overflow
        self.overflowInstDensityStretchRatio = [] #OVFL density stretch ratio

        self.rawdb = None # raw placement database, a C++ object 

        self.num_movable_nodes = 0# number of movable nodes
        self.num_terminals = 0# number of IOs, essentially fixed instances
        self.num_ccNodes= 0# number of carry chains
        self.net_weights = None # weights for each net

        self.xl = None 
        self.yl = None 
        self.xh = None 
        self.yh = None 

        self.num_movable_pins = None 

        self.total_movable_node_area = None # total movable cell area 
        self.total_fixed_node_area = None # total fixed cell area 
        self.total_space_area = None # total placeable space area excluding fixed cells 

        # enable filler cells 
        # the Idea from e-place and RePlace 
        self.total_filler_node_area = None 
        self.num_filler_nodes = 0 

        self.routing_grid_xl = None 
        self.routing_grid_yl = None 
        self.routing_grid_xh = None 
        self.routing_grid_yh = None 
        self.num_routing_grids_x = None
        self.num_routing_grids_y = None
        self.num_routing_layers = None
        self.unit_horizontal_capacity = None # per unit distance, projected to one layer 
        self.unit_vertical_capacity = None # per unit distance, projected to one layer 
        self.unit_horizontal_capacities = None # per unit distance, layer by layer 
        self.unit_vertical_capacities = None # per unit distance, layer by layer 
        self.initial_horizontal_demand_map = None # routing demand map from fixed cells, indexed by (grid x, grid y), projected to one layer  
        self.initial_vertical_demand_map = None # routing demand map from fixed cells, indexed by (grid x, grid y), projected to one layer  
        self.dtype = None
        #Use Fence region structure for different resource type placement
        self.regions = 0 #FF, LUT, DSP, RAM & IO
        self.flat_region_boxes = []# flat version of regionsLimits
        self.flat_region_boxes_start = []# start indices of regionsLimits, length of num regions + 1
        self.node2fence_region_map = []# map cell to a region, maximum integer if no fence region
        self.node_count = [] #Count of nodes based on resource type
        #Introduce masks
        self.flop_mask = None
        self.lut_mask = None
        self.lut_type = None
        self.cluster_lut_type = None
        self.ram0_mask = None
        self.ram1_mask = None
        self.dsp_mask = None

        self.fixed_rsrcIds = []
        self.slice_rsrcIds = []
        self.slice_compIds = []
        self.dsp_ram_rsrcIds = []
        self.dsp_ram_compIds= []

    """
    @return number of nodes
    """
    @property
    def num_nodes_nofiller(self):
        return self.num_physical_nodes
    """
    @return number of nodes
    """
    @property
    def num_nodes(self):
        return self.num_physical_nodes + self.num_filler_nodes
    """
    @return number of nets
    """
    @property
    def num_nets(self):
        return len(self.net2pin_map)
    """
    @return number of pins 
    """
    @property 
    def num_pins(self):
        return len(self.pin2node_map)

    @property
    def width(self):
        """
        @return width of layout
        """
        return int(self.xh-self.xl)

    @property
    def height(self):
        """
        @return height of layout
        """
        return int(self.yh-self.yl)

    @property
    def area(self):
        """
        @return area of layout
        """
        return self.width*self.height

    @property
    def routing_grid_size_x(self):
        return (self.routing_grid_xh - self.routing_grid_xl) / self.num_routing_grids_x 

    @property 
    def routing_grid_size_y(self):
        return (self.routing_grid_yh - self.routing_grid_yl) / self.num_routing_grids_y 

    def num_bins(self, l, h, bin_size):
        """
        @brief compute number of bins
        @param l lower bound
        @param h upper bound
        @param bin_size bin size
        @return number of bins
        """
        return int(np.ceil((h-l)/bin_size))

    """
    read all files including .inst, .pin, .net, .routingUtil files 
    """
    def read(self, params):
        self.dtype = datatypes[params.dtype]

        self.rawdb = place_io.PlaceIOFunction.read(params)

        self.initialize_from_rawdb(params)

        self.lut_mask = self.node2fence_region_map == self.rLUTIdx
        self.flop_mask = self.node2fence_region_map == self.rFFIdx
        self.lut_flop_mask = self.lut_mask | self.flop_mask

        if self.num_ccNodes > 0:
            self.org_lut_mask = self.org_node2fence_region_map == self.rLUTIdx
            self.org_flop_mask = self.org_node2fence_region_map == self.rFFIdx
            self.org_lut_flop_mask = self.org_lut_mask | self.org_flop_mask

        if self.rLUTIdx != -1:
            self.slice_rsrcIds.append(self.rLUTIdx)
        if self.rFFIdx != -1:
            self.slice_rsrcIds.append(self.rFFIdx)

        self.dsp_ram_mask = self.node2fence_region_map == -1
        if self.rDSPIdx != -1:
            self.dsp_mask = self.node2fence_region_map == self.rDSPIdx
            self.dsp_ram_mask |= self.dsp_mask
            self.dsp_ram_rsrcIds.append(self.rDSPIdx)
        if self.rBRAMIdx != -1:
            self.ram0_mask = self.node2fence_region_map == self.rBRAMIdx
            self.dsp_ram_mask |= self.ram0_mask
            self.dsp_ram_rsrcIds.append(self.rBRAMIdx)
        if self.rM9KIdx != -1:
            self.ram0_mask = self.node2fence_region_map == self.rM9KIdx
            self.dsp_ram_mask |= self.ram0_mask
            self.dsp_ram_rsrcIds.append(self.rM9KIdx)
        if self.rM144KIdx != -1:
            self.ram1_mask = self.node2fence_region_map == self.rM144KIdx
            self.dsp_ram_mask |= self.ram1_mask
            self.dsp_ram_rsrcIds.append(self.rM144KIdx)
        self.dsp_ram_rsrcIds = np.array(self.dsp_ram_rsrcIds, dtype=np.int32)

        self.io_mask = self.node2fence_region_map == -1
        if self.rIOIdx!= -1:
            self.fixed_rsrcIds.append(self.rIOIdx)
            self.io_mask |= self.node2fence_region_map == self.rIOIdx
        if self.rPLLIdx != -1:
            self.fixed_rsrcIds.append(self.rPLLIdx)
            self.io_mask |= self.node2fence_region_map == self.rPLLIdx
        self.fixed_rsrcIds = np.array(self.fixed_rsrcIds, dtype=np.int32)

    def initialize_from_rawdb(self, params):
        """
        @brief initialize data members from raw database
        @param params parameters
        """
        pydb = place_io.PlaceIOFunction.pydb(self.rawdb)

        self.num_terminals = pydb.num_terminals
        self.num_movable_nodes = pydb.num_movable_nodes
        self.num_physical_nodes = pydb.num_physical_nodes
        self.node_count = np.array(pydb.node_count, dtype=np.int32)

        #Do not use numpy array for names as it could result in
        # large memory usage for large designs with long names
        self.node_names = pydb.node_names
        self.node_name2id_map = pydb.node_name2id_map
        self.node_size_x = np.array(pydb.node_size_x, dtype=self.dtype)
        self.node_size_y = np.array(pydb.node_size_y, dtype=self.dtype)
        self.node_types = np.array(pydb.node_types, dtype=np.str_)
        self.node2fence_region_map = np.array(pydb.node2fence_region_map, dtype=np.int32)
        self.node_x = np.array(pydb.node_x, dtype=self.dtype)
        self.node_y = np.array(pydb.node_y, dtype=self.dtype)
        self.node_z = np.array(pydb.node_z, dtype=np.int32)
        
        self.node2pin_map = pydb.node2pin_map
        self.flat_node2pin_map = np.array(pydb.flat_node2pin_map, dtype=np.int32)
        self.flat_node2pin_start_map = np.array(pydb.flat_node2pin_start_map, dtype=np.int32)
        self.node2pincount_map = np.array(pydb.node2pincount_map, dtype=np.int32)
        self.net2pincount_map = np.array(pydb.net2pincount_map, dtype=np.int32)
        self.node2outpinIdx_map = np.array(pydb.node2outpinIdx_map, dtype=np.int32)
        self.flop_indices = np.array(pydb.flop_indices)
        self.lut_type = np.array(pydb.lut_type).astype(np.int32)
        #Use for clustering aware instance area update. LUT0 is ignored and other types have N-1 for type LUTN
        self.cluster_lut_type = np.array(pydb.cluster_lut_type).astype(np.int32)

        #TODO - For Stratix-IV: mlab is treated as lut type as sites for MLAB/LAB are not distinguished
        self.is_mlab_node = self.lut_type > 9
        self.num_mlab_nodes = self.is_mlab_node.sum()

        self.pin_offset_x = np.array(pydb.pin_offset_x, dtype=self.dtype)
        self.pin_offset_y = np.array(pydb.pin_offset_y, dtype=self.dtype)
        self.pin2nodeType_map = np.array(pydb.pin2nodeType_map, dtype=np.int32)

        self.pin_names = pydb.pin_names
        self.pin_types = np.array(pydb.pin_types, dtype=np.str_)
        self.pin_typeIds = np.array(pydb.pin_typeIds, dtype=np.int32)
        self.pin2node_map = np.array(pydb.pin2node_map, dtype=np.int32)
        self.pin2net_map = np.array(pydb.pin2net_map, dtype=np.int32)
        self.spiral_accessor = np.array(pydb.spiral_accessor, dtype=np.int32)
        self.spiral_maxVal = pydb.spiral_maxVal

        self.net_names = pydb.net_names
        self.net2pin_map = pydb.net2pin_map

        self.flat_net2pin_map = np.array(pydb.flat_net2pin_map, dtype=np.int32)
        self.flat_net2pin_start_map = np.array(pydb.flat_net2pin_start_map, dtype=np.int32)
        self.net_name2id_map = pydb.net_name2id_map
        self.net_weights = np.array(np.ones(len(self.net_names)), dtype=self.dtype)

        self.num_sites_x = pydb.num_sites_x
        self.num_sites_y = pydb.num_sites_y
        self.siteTypes = np.array(pydb.siteTypes, dtype=np.str_)
        self.siteWidths = np.array(pydb.siteWidths, dtype=self.dtype)
        self.siteHeights = np.array(pydb.siteHeights, dtype=self.dtype)
        self.rsrcTypes = np.array(pydb.rsrcTypes, dtype=np.str_)
        self.rsrcInstWidths = np.array(pydb.rsrcInstWidths, dtype=self.dtype)
        self.rsrcInstHeights = np.array(pydb.rsrcInstHeights, dtype=self.dtype)
        #TODO: Cell dimensions read in for FF/LUT are square values
        self.rsrcInstWidths[self.rsrcInstWidths < 1.0] = np.sqrt(self.rsrcInstWidths[self.rsrcInstWidths < 1.0])
        self.rsrcInstHeights[self.rsrcInstHeights < 1.0] = np.sqrt(self.rsrcInstHeights[self.rsrcInstHeights < 1.0])
        self.siteResources = pydb.siteResources
        self.rsrcInsts = pydb.rsrcInsts
        self.rsrcInstTypes = np.array(pydb.rsrcInstTypes, dtype=np.str_)
        self.rsrc2siteMap = pydb.rsrc2siteMap
        self.inst2rsrcMap = pydb.inst2rsrcMap
        self.siteRsrc2CountMap = pydb.siteRsrc2CountMap
        self.siteType2indexMap = pydb.siteType2indexMap
        self.rsrcType2indexMap = pydb.rsrcType2indexMap
        self.rsrcInstType2indexMap = pydb.rsrcInstType2indexMap
        self.sliceElements = pydb.sliceElements
        self.lut_maxShared = pydb.lut_maxShared
        self.lutTypeInSliceUnit = pydb.lut_type_in_sliceUnit
        self.lutFracturesMap = pydb.lutFracturesMap
        self.sliceFF_ctrl_mode = pydb.sliceFF_ctrl_mode
        self.sliceFFCtrls = pydb.sliceFFCtrls
        self.sliceUnitFFCtrls = pydb.sliceUnitFFCtrls
        self.siteOutCoordinates = np.array(pydb.siteOutCoordinates, dtype=np.str_)
        self.siteOutValues = np.array(pydb.siteOutValues, dtype=np.int32)
        self.site_type_map = np.array(pydb.site_type_map, dtype=np.int32)
        self.lg_siteXYs = np.array(pydb.lg_siteXYs, dtype=self.dtype)

        #Compute Indices for rsrcTypes
        self.rFFIdx = -1
        self.rLUTIdx = -1
        self.rMlabIdx = -1
        self.rADDIdx = -1
        self.rIOIdx = -1
        self.rPLLIdx = -1
        self.rBRAMIdx = -1
        self.rM9KIdx = -1
        self.rM144KIdx = -1
        self.rDSPIdx = -1
        self.rEMPTYIdx = -1

        if 'FF' in self.rsrcType2indexMap:
            self.rFFIdx = self.rsrcType2indexMap['FF']
        elif 'dffeas' in self.rsrcType2indexMap:
            self.rFFIdx = self.rsrcType2indexMap['dffeas']
        if 'LUT' in self.rsrcType2indexMap:
            self.rLUTIdx = self.rsrcType2indexMap['LUT']
        elif 'lcell_comb' in self.rsrcType2indexMap:
            self.rLUTIdx = self.rsrcType2indexMap['lcell_comb']
        elif 'stratixiv_lcell_comb' in self.rsrcType2indexMap:
            self.rLUTIdx = self.rsrcType2indexMap['stratixiv_lcell_comb']

        fVal = [value for key, value in self.rsrcType2indexMap.items() if 'mlab' in key.lower()]
        if len(fVal) > 0:
            self.rMlabIdx = fVal[0]
        
        if 'ADD' in self.rsrcType2indexMap:
            self.rADDIdx = self.rsrcType2indexMap['ADD']
        if 'IO' in self.rsrcType2indexMap:
            self.rIOIdx = self.rsrcType2indexMap['IO']
        elif 'io' in self.rsrcType2indexMap:
            self.rIOIdx = self.rsrcType2indexMap['io']
        if 'PLL' in self.rsrcType2indexMap:
            self.rPLLIdx= self.rsrcType2indexMap['PLL']
        if 'DSP' in self.rsrcType2indexMap:
            self.rDSPIdx = self.rsrcType2indexMap['DSP']
        elif 'DSP48E2' in self.rsrcType2indexMap:
            self.rDSPIdx = self.rsrcType2indexMap['DSP48E2']
        if 'BRAM' in self.rsrcType2indexMap:
            self.rBRAMIdx = self.rsrcType2indexMap['BRAM']
        elif 'RAMB36E2' in self.rsrcType2indexMap:
            self.rBRAMIdx = self.rsrcType2indexMap['RAMB36E2']
        if 'M9K' in self.rsrcType2indexMap:
            self.rM9KIdx = self.rsrcType2indexMap['M9K']
        if 'M144K' in self.rsrcType2indexMap:
            self.rM144KIdx = self.rsrcType2indexMap['M144K']
        if 'EMPTY' in self.rsrcType2indexMap:
            self.rEMPTYIdx = self.rsrcType2indexMap['EMPTY']
        elif 'empty' in self.rsrcType2indexMap:
            self.rEMPTYIdx = self.rsrcType2indexMap['empty']

        self.lg_pin_offset_x = self.pin_offset_x.copy()
        self.lg_pin_offset_y = self.pin_offset_y.copy()
        #Initialize pin offsets for LUT/FF/IO to 0.0 during legalization
        dsp_ram_pin_mask = (self.pin2nodeType_map == self.rDSPIdx) | (self.pin2nodeType_map == self.rBRAMIdx) | (self.pin2nodeType_map == self.rM9KIdx) | (self.pin2nodeType_map == self.rM144KIdx)
        self.lg_pin_offset_x[~dsp_ram_pin_mask] = 0.0
        self.lg_pin_offset_y[~dsp_ram_pin_mask] = 0.0

        #Indices for siteTypes 
        self.sSLICEIdx = pydb.sliceIdx
        self.sDSPIdx = pydb.dspIdx
        self.sBRAMIdx = pydb.bramIdx 
        self.sM9KIdx = pydb.m9kIdx
        self.sM144KIdx = pydb.m144kIdx
        self.sIOIdx = pydb.ioIdx
        self.sPLLIdx = pydb.pllIdx

        self.sliceSiteXYs = np.array(pydb.sliceSiteXYs, dtype=self.dtype)
        self.slice_x_min = np.min(self.sliceSiteXYs[:,0])
        self.slice_y_min = np.min(self.sliceSiteXYs[:,1])
        self.slice_x_max = np.max(self.sliceSiteXYs[:,0])
        self.slice_y_max = np.max(self.sliceSiteXYs[:,1])

        self.dspSiteXYs = np.array(pydb.dspSiteXYs, dtype=self.dtype)
        if self.sBRAMIdx != -1 or self.sM9KIdx != -1:
            self.ramSite0XYs = np.array(pydb.ramSite0XYs, dtype=self.dtype)
        if self.sM144KIdx != -1:
            self.ramSite1XYs = np.array(pydb.ramSite1XYs, dtype=self.dtype)

        self.lutName = [key for key, val in self.rsrcType2indexMap.items() if val==self.rLUTIdx][0]
        self.slice_lut_capacity=self.siteRsrc2CountMap[self.lutName]
        self.SLICE_CAPACITY = self.slice_lut_capacity
        self.HALF_SLICE_CAPACITY = self.SLICE_CAPACITY//2 

        self.regions = self.rsrcTypes.shape[0]
        self.flat_region_boxes = np.array(pydb.flat_region_boxes, dtype=self.dtype)
        self.flat_region_boxes_start = np.array(pydb.flat_region_boxes_start, dtype=np.int32)
        self.ctrlSets = np.array(pydb.ctrlSets, dtype=np.int32)
        self.flat_ctrlSets = self.ctrlSets.flatten()
        self.flop2ctrlSetId_map = np.zeros(self.num_physical_nodes, dtype=np.int32)
        self.flop2ctrlSetId_map[self.node2fence_region_map == self.rFFIdx] = np.arange(self.node_count[self.rFFIdx])
        #For 'SHARED' flop ctrls
        self.extended_ctrlSets = np.array(pydb.extended_ctrlSets, dtype=np.int32)
        self.ext_ctrlSet_start_map = np.array(pydb.ext_ctrlSet_start_map, dtype=np.int32)

        ##Carry chains
        self.num_ccNodes = pydb.num_ccNodes
        self.num_carry_chains = 0
        #self.flat_cc2node_map = np.array(pydb.flat_cc2node_map, dtype=np.int32)
        #self.flat_cc2node_start_map = np.array(pydb.flat_cc2node_start_map, dtype=np.int32)

        if self.num_ccNodes > 0:
            self.node2ccId_map = np.array(pydb.node2ccId_map, dtype=np.int32)
            self.cc2nodeId_map = np.array(pydb.cc2nodeId_map, dtype=np.int32)
            self.cc_element_count= np.array(pydb.cc_element_count, dtype=np.int32)
            self.is_cc_node = np.array(pydb.is_cc_node, dtype=np.int32)
            self.cc_site_height = np.ceil(self.node_size_y[self.is_cc_node == 1]).astype(np.int32)

            self.org_num_movable_nodes = pydb.org_num_movable_nodes
            self.org_num_physical_nodes = pydb.org_num_movable_nodes + pydb.num_terminals
            self.org_node_name2id_map = pydb.org_node_name2id_map
            self.org_node_names = pydb.org_node_names
            self.org_node_types = np.array(pydb.org_node_types, dtype=np.str_)
            self.org_node_size_x = np.array(pydb.org_node_size_x, dtype=self.dtype)
            self.org_node_size_y = np.array(pydb.org_node_size_y, dtype=self.dtype)
            self.org_node_x = np.array(pydb.org_node_x, dtype=self.dtype)
            self.org_node_y = np.array(pydb.org_node_y, dtype=self.dtype)
            self.org_node_z = np.array(pydb.org_node_z, dtype=np.int32)
            self.org_node2fence_region_map = np.array(pydb.org_node2fence_region_map, dtype=np.int32)
            self.org_node_count = np.array(pydb.org_node_count, dtype=np.int32)
            self.org_is_cc_node = np.array(pydb.org_is_cc_node, dtype=np.int32)
            self.org_flop_indices = np.array(pydb.org_flop_indices)
            self.org_lut_type = np.array(pydb.org_lut_type).astype(np.int32)
            self.org_node2ccId_map = np.array(pydb.org_node2ccId_map, dtype=np.int32)
            self.org_pin_offset_x = np.array(pydb.org_pin_offset_x, dtype=self.dtype)
            self.org_pin_offset_y = np.array(pydb.org_pin_offset_y, dtype=self.dtype)
            self.org_pin2nodeType_map = np.array(pydb.org_pin2nodeType_map, dtype=np.int32)
            self.org_node2pincount_map = np.array(pydb.org_node2pincount_map, dtype=np.int32)
            self.org_pin2node_map = np.array(pydb.org_pin2node_map, dtype=np.int32)
            self.org_node2outpinIdx_map = np.array(pydb.org_node2outpinIdx_map, dtype=np.int32)
            self.org_flat_node2pin_map = np.array(pydb.org_flat_node2pin_map, dtype=np.int32)
            self.org_flat_node2pin_start_map = np.array(pydb.org_flat_node2pin_start_map, dtype=np.int32)
            self.org_flat_cc2node_map = np.array(pydb.org_flat_cc2node_map, dtype=np.int32)
            self.org_flat_cc2node_start_map = np.array(pydb.org_flat_cc2node_start_map, dtype=np.int32)
            self.org_node2ccId_map = np.array(pydb.org_node2ccId_map, dtype=np.int32)
            self.new2org_node_map = np.array(pydb.new2org_node_map, dtype=np.int32)
            ## FF Ctrl
            self.org_ctrlSets = np.array(pydb.org_ctrlSets, dtype=np.int32)
            self.flat_org_ctrlSets = self.org_ctrlSets.flatten()
            self.org_flop2ctrlSetId_map = np.zeros(self.org_num_physical_nodes, dtype=np.int32)
            self.org_flop2ctrlSetId_map[self.org_node2fence_region_map == self.rFFIdx] = np.arange(self.org_node_count[self.rFFIdx])
            #For 'SHARED' flop ctrls
            self.org_extended_ctrlSets = np.array(pydb.org_extended_ctrlSets, dtype=np.int32)
            self.org_ext_ctrlSet_start_map = np.array(pydb.org_ext_ctrlSet_start_map, dtype=np.int32)
            self.org_is_mlab_node = self.org_lut_type > 9

            self.org_lg_pin_offset_x = self.org_pin_offset_x.copy()
            self.org_lg_pin_offset_y = self.org_pin_offset_y.copy()
            #Initialize pin offsets for LUT/FF/IO to 0.0 during legalization
            dsp_ram_pin_mask = (self.org_pin2nodeType_map == self.rDSPIdx) | (self.org_pin2nodeType_map == self.rBRAMIdx) | (self.org_pin2nodeType_map == self.rM9KIdx) | (self.org_pin2nodeType_map == self.rM144KIdx)
            self.org_lg_pin_offset_x[~dsp_ram_pin_mask] = 0.0
            self.org_lg_pin_offset_y[~dsp_ram_pin_mask] = 0.0


        else:
            self.is_cc_node = np.zeros(self.num_nodes, dtype=np.int32)
            self.org_is_cc_node = np.zeros_like(self.is_cc_node)

        self.num_routing_grids_x = pydb.xh
        self.num_routing_grids_y = pydb.yh
        self.routing_grid_xl = self.dtype(pydb.routing_grid_xl)
        self.routing_grid_yl = self.dtype(pydb.routing_grid_yl)
        self.routing_grid_xh = self.dtype(pydb.routing_grid_xh)
        self.routing_grid_yh = self.dtype(pydb.routing_grid_yh)

        self.xl = self.dtype(pydb.xl)
        self.yl = self.dtype(pydb.yl)
        self.xh = self.dtype(pydb.xh)
        self.yh = self.dtype(pydb.yh)

        self.ff_ctrl_type = pydb.ff_ctrl_type
        self.num_routing_layers = 1
        self.xWirelenWt = pydb.wl_weightX
        self.yWirelenWt = pydb.wl_weightY
        self.unitPinCap = pydb.pinRouteCap
        self.unit_horizontal_capacity = 0.95 * pydb.routeCapH
        self.unit_vertical_capacity = 0.95 * pydb.routeCapV

        #Use for debug when node and net names are long
        if params.name_map_file_dump == 1:
            tt = time.time()
            #Dump out design.nodes
            content=""

            for nodeId in range(len(self.node_names)):
                upd_node_name = "inst_"+str(nodeId)
                content += "%s %s\n" % (upd_node_name, self.node_types[nodeId])
                
            mNames_file = "mapped_design.nodes"
            with open(mNames_file, "w") as f:
                f.write(content)
            logging.info("write out node name mapping to %s took %.3f seconds" % (mNames_file, time.time()-tt))

            #Dump out design.nets
            content=""

            for netId in range(len(self.net_names)):
                upd_net_name = "net_"+str(netId)
                content += "net %s %d\n" % (upd_net_name, self.net2pincount_map[netId])

                n2pStart = self.flat_net2pin_start_map[netId]
                n2pEnd = self.flat_net2pin_start_map[netId+1]

                for pId in range(n2pStart, n2pEnd):
                    pinId = self.flat_net2pin_map[pId]
                    nodeId = self.pin2node_map[pinId]
                    upd_node_name = "inst_"+str(nodeId)
                    content += "\t%s %s\n" % (upd_node_name, self.pin_names[pinId])

                content += "endnet\n"
                
            mNets_file = "mapped_design.nets"
            with open(mNets_file, "w") as f:
                f.write(content)
            logging.info("write out node net mapping to %s took %.3f seconds" % (mNets_file, time.time()-tt))


    def print_node(self, node_id):
        """
        @brief print node information
        @param node_id cell index
        """
        logging.debug("node %s(%d), size (%g, %g), pos (%g, %g)" % (self.node_names[node_id], node_id, self.node_size_x[node_id], self.node_size_y[node_id], self.node_x[node_id], self.node_y[node_id]))
        pins = "pins "
        for pin_id in self.node2pin_map[node_id]:
            pins += "%s(%s, %d) " % (self.node_names[self.pin2node_map[pin_id]], self.net_names[self.pin2net_map[pin_id]], pin_id)
        logging.debug(pins)

    def print_net(self, net_id):
        """
        @brief print net information
        @param net_id net index
        """
        logging.debug("net %s(%d)" % (self.net_names[net_id], net_id))
        pins = "pins "
        for pin_id in self.net2pin_map[net_id]:
            pins += "%s(%s, %d) " % (self.node_names[self.pin2node_map[pin_id]], self.net_names[self.pin2net_map[pin_id]], pin_id)
        logging.debug(pins)

    def flatten_nested_map(self, net2pin_map):
        """
        @brief flatten an array of array to two arrays like CSV format
        @param net2pin_map array of array
        @return a pair of (elements, cumulative column indices of the beginning element of each row)
        """
        # flat netpin map, length of #pins
        flat_net2pin_map = np.zeros(len(pin2net_map), dtype=np.int32)
        # starting index in netpin map for each net, length of #nets+1, the last entry is #pins
        flat_net2pin_start_map = np.zeros(len(net2pin_map)+1, dtype=np.int32)
        count = 0
        for i in range(len(net2pin_map)):
            flat_net2pin_map[count:count+len(net2pin_map[i])] = net2pin_map[i]
            flat_net2pin_start_map[i] = count
            count += len(net2pin_map[i])
        assert flat_net2pin_map[-1] != 0
        flat_net2pin_start_map[len(net2pin_map)] = len(pin2net_map)

        return flat_net2pin_map, flat_net2pin_start_map

    def __call__(self, params):
        """
        @brief top API to read placement files 
        @param params parameters 
        """
        tt = time.time()

        self.read(params)
        self.initialize(params)

        logging.info("reading benchmark takes %g seconds" % (time.time()-tt))

    def calc_num_filler_for_fence_region(self, region_id, node2fence_region_map, filler_size_x, filler_size_y):
        '''
        @description: calculate number of fillers for each fence region
        @param fence_regions{type}
        @return:
        '''
        fence_region_mask = (node2fence_region_map == region_id)

        if region_id in self.fixed_rsrcIds:
            return 0, 0, self.num_terminals

        #If no cells of particular resourceType
        if np.sum(fence_region_mask) == 0:
            return 0, 0, 0.0

        movable_node_size_x = self.node_size_x[fence_region_mask]
        movable_node_size_y = self.node_size_y[fence_region_mask]

        #Calcuation based on region size 
        region = self.flat_region_boxes[self.flat_region_boxes_start[region_id]:self.flat_region_boxes_start[region_id+1]]
        placeable_area = np.sum((region[:, 2]-region[:, 0])*(region[:, 3]-region[:, 1]))

        total_movable_node_area = np.sum(movable_node_size_x*movable_node_size_y)

        total_filler_node_area = max(placeable_area-total_movable_node_area, 0.0)

        #TODO - For Stratix-IV: mlab is treated as lut type as sites for MLAB/LAB are not distinguished
        #Add pseudo filler nodes for FFs
        if region_id == self.rFFIdx and self.num_mlab_nodes > 0:
            total_filler_node_area -= self.num_mlab_nodes
            num_filler = int(math.floor(total_filler_node_area/(filler_size_x*filler_size_y))) + self.num_mlab_nodes
        else:
            num_filler = int(math.floor(total_filler_node_area/(filler_size_x*filler_size_y)))

        #TODO - For Stratix-IV: mlab is treated as lut type as sites for MLAB/LAB are not distinguished
        if region_id == self.rLUTIdx and self.num_mlab_nodes > 0:
            logging.info("Region: %d [%s] #movable_nodes = %d (%s) + %d (mlab) = %d, movable_node_area = %.1f, placeable_area = %.1f, filler_node_area = %.1f, #fillers = %d, filler size = %.4g x %g\n" 
                        % (region_id, self.rsrcTypes[region_id], fence_region_mask.sum()-self.num_mlab_nodes, self.rsrcTypes[region_id], self.num_mlab_nodes, fence_region_mask.sum(), total_movable_node_area, placeable_area, total_filler_node_area, num_filler, filler_size_x, filler_size_y))
        else:            
            logging.info("Region: %d [%s] #movable_nodes = %d movable_node_area = %.1f, placeable_area = %.1f, filler_node_area = %.1f, #fillers = %d, filler size = %.4g x %g\n" 
                        % (region_id, self.rsrcTypes[region_id], fence_region_mask.sum(), total_movable_node_area, placeable_area, total_filler_node_area, num_filler, filler_size_x, filler_size_y))

        #Ensure there is sufficient space available for placement
        if total_movable_node_area > placeable_area:
            logging.error("Provided %d x %d site_map is not large enough to accomodate all %s instances. Use a larger site_map.\n" % (self.num_sites_x, self.num_sites_y, self.rsrcTypes[region_id]))
            sys.exit(0)

        return num_filler, total_movable_node_area, np.sum(fence_region_mask)


    def initialize(self, params):
        """
        @brief initialize data members after reading 
        @param params parameters 
        """
        self.resource_size_x = self.siteWidths
        self.resource_size_y = self.siteHeights

        #Parameter initialization - Can be changed later through params
        if self.xWirelenWt == None or self.xWirelenWt == 0:
            self.xWirelenWt = 1.0
        if self.yWirelenWt == None or self.yWirelenWt == 0:
            self.yWirelenWt = 1.0
        self.instDemStddevTrunc = 2.5
        
        #Resource area parameter
        self.gpInstStddev = math.sqrt(2.5e-4 * self.num_nodes) / (2.0 * self.instDemStddevTrunc)
        self.gpInstStddevTrunc = self.instDemStddevTrunc
        
        self.instDemStddevX = self.gpInstStddev
        self.instDemStddevY = self.gpInstStddev

        #Parameter for Direct Legalization
        self.nbrDistEnd = 1.2 * self.gpInstStddev * self.gpInstStddevTrunc
        
        # Routability and pin density optimization parameters
        self.unitPinCap = 0

        #Area type parameters - Consider default fillerstrategy of FIXED_SHAPE
        self.filler_size_x = np.zeros(self.regions - self.fixed_rsrcIds.size)
        self.filler_size_y = np.zeros(self.regions - self.fixed_rsrcIds.size)
        self.targetOverflow = np.zeros(self.regions - self.fixed_rsrcIds.size)
        self.overflowInstDensityStretchRatio = np.zeros(self.regions - self.fixed_rsrcIds.size)
        self.node_area_adjust_overflow = np.ones_like(self.targetOverflow)
        self.node_area_adjust_overflow *= params.node_area_adjust_overflow

        self.rsrc2compId_map = np.ones(self.regions, dtype=np.int32) 
        self.rsrc2compId_map *= -1
        self.comp2rsrcId_map = np.ones_like(self.rsrc2compId_map)
        self.comp2rsrcId_map *= -1

        tId = 0
        for rId in range(self.regions):
            if rId not in self.fixed_rsrcIds:
                if self.node_count[rId] > 0:
                    #Do not consider large instances such as carry chains while determining filler sizes
                    largeNodes = self.is_cc_node[self.node2fence_region_map == rId]
                    if rId == self.rLUTIdx:
                        largeNodes |= self.is_mlab_node[self.node2fence_region_map == rId]
                    max_x = np.max(self.node_size_x[self.node2fence_region_map == rId][largeNodes == 0])
                    max_y = np.max(self.node_size_y[self.node2fence_region_map == rId][largeNodes == 0])
                    self.filler_size_x[tId] = math.sqrt(round(max_x*max_x,4))
                    self.filler_size_y[tId] = math.sqrt(round(max_y*max_y,4))
                    if max_x < 1.0 and max_y < 1.0:
                        self.targetOverflow[tId] = 0.1
                        self.overflowInstDensityStretchRatio[tId] = math.sqrt(2.0)
                    else:
                        self.targetOverflow[tId] = 0.2
                        self.node_area_adjust_overflow[tId] = 0.25
                    self.rsrc2compId_map[rId] = tId
                    self.comp2rsrcId_map[tId] = rId
                    tId = tId + 1

        ##Set FF filler size to be same as LUT
        self.filler_size_x[self.rFFIdx] = self.filler_size_x[self.rLUTIdx]
        self.filler_size_y[self.rFFIdx] = self.filler_size_y[self.rLUTIdx]

        #Resize based on available resources in the design
        maxVal = self.rsrc2compId_map.max()+1
        self.filler_size_x = self.filler_size_x[:maxVal]
        self.filler_size_y = self.filler_size_y[:maxVal]
        self.targetOverflow = self.targetOverflow[:maxVal]
        self.overflowInstDensityStretchRatio = self.overflowInstDensityStretchRatio[:maxVal]

        if self.rLUTIdx != -1 and self.rsrc2compId_map[self.rLUTIdx] != -1:
            self.slice_compIds.append(self.rsrc2compId_map[self.rLUTIdx])
        if self.rFFIdx != -1 and self.rsrc2compId_map[self.rFFIdx] != -1:
            self.slice_compIds.append(self.rsrc2compId_map[self.rFFIdx])

        if self.rDSPIdx != -1 and self.rsrc2compId_map[self.rDSPIdx] != -1:
            self.dsp_ram_compIds.append(self.rsrc2compId_map[self.rDSPIdx])
        if self.rBRAMIdx != -1 and self.rsrc2compId_map[self.rBRAMIdx] != -1:
            self.dsp_ram_compIds.append(self.rsrc2compId_map[self.rBRAMIdx])
        if self.rM9KIdx != -1 and self.rsrc2compId_map[self.rM9KIdx] != -1:
            self.dsp_ram_compIds.append(self.rsrc2compId_map[self.rM9KIdx])
        if self.rM144KIdx != -1 and self.rsrc2compId_map[self.rM144KIdx] != -1:
            self.dsp_ram_compIds.append(self.rsrc2compId_map[self.rM144KIdx])

        #set number of bins
        self.num_bins_x = params.num_bins_x
        self.num_bins_y = params.num_bins_y
        self.bin_size_x = self.width/self.num_bins_x
        self.bin_size_y = self.height/self.num_bins_y

        # set total cell area
        self.total_movable_node_area = self.dtype(np.sum(self.lut_flop_mask)*self.filler_size_x[self.rLUTIdx]*self.filler_size_y[self.rLUTIdx])
        if self.dsp_ram_mask.sum() > 0:
            self.total_movable_node_area += self.dtype(np.sum(self.node_size_x[self.dsp_ram_mask]*self.node_size_y[self.dsp_ram_mask]))

        # total fixed node area should exclude the area outside the layout and the area of terminal_NIs
        self.total_fixed_node_area = self.dtype(self.num_terminals)
        self.total_space_area = self.width * self.height

        self.region_boxes = []

        #For FPGA, the regions are fixed for each resourceType
        for region_id in range(self.regions):
            idx = self.rsrc2compId_map[region_id]
            if idx != -1:
                region = self.flat_region_boxes[self.flat_region_boxes_start[region_id]:self.flat_region_boxes_start[region_id+1]] 
                self.region_boxes.append(region)

        # insert filler nodes
        ### calculate fillers for different resourceTypes
        self.filler_size_x_fence_region = []
        self.filler_size_y_fence_region = []
        self.num_filler_nodes = 0
        self.num_filler_nodes_fence_region = []
        self.num_movable_nodes_fence_region = []
        self.total_movable_node_area_fence_region = []
        self.target_density_fence_region = []
        self.filler_start_map = None
        filler_node_size_x_list = []
        filler_node_size_y_list = []
        self.total_filler_node_area = 0

        for idx in range(self.regions):
            i = self.rsrc2compId_map[idx]
            if i != -1:
                num_filler_i, total_movable_node_area_i, num_movable_nodes_i = self.calc_num_filler_for_fence_region(idx, self.node2fence_region_map,
                                                                                                    self.filler_size_x[i], self.filler_size_y[i])
                self.num_movable_nodes_fence_region.append(num_movable_nodes_i)
                self.num_filler_nodes_fence_region.append(num_filler_i)
                self.total_movable_node_area_fence_region.append(total_movable_node_area_i)
                self.target_density_fence_region.append(self.targetOverflow[i])
                self.filler_size_x_fence_region.append(self.filler_size_x[i])
                self.filler_size_y_fence_region.append(self.filler_size_y[i])
                self.num_filler_nodes += num_filler_i

                #TODO - For Stratix-IV: mlab is treated as lut type as sites for MLAB/LAB are not distinguished
                #Add pseudo filler nodes for FFs
                if i == self.rFFIdx and self.num_mlab_nodes > 0:
                    filler_count = num_filler_i - self.num_mlab_nodes
                    tmp_filler_size_x = np.full(self.num_mlab_nodes, fill_value=self.rsrcInstWidths[self.rMlabIdx], dtype=self.node_size_x.dtype)
                    tmp_filler_size_x = np.concatenate((tmp_filler_size_x, np.full(filler_count, fill_value=self.filler_size_x[i], dtype=self.node_size_x.dtype)))
                    filler_node_size_x_list.append(tmp_filler_size_x)
                    tmp_filler_size_y = np.full(self.num_mlab_nodes, fill_value=self.rsrcInstHeights[self.rMlabIdx], dtype=self.node_size_y.dtype)
                    tmp_filler_size_y = np.concatenate((tmp_filler_size_y, np.full(filler_count, fill_value=self.filler_size_y[i], dtype=self.node_size_y.dtype)))
                    filler_node_size_y_list.append(tmp_filler_size_y)
                    filler_node_area_i = filler_count * (self.filler_size_x[i]*self.filler_size_y[i]) + self.num_mlab_nodes
                else:
                    filler_node_size_x_list.append(np.full(num_filler_i, fill_value=self.filler_size_x[i], dtype=self.node_size_x.dtype))
                    filler_node_size_y_list.append(np.full(num_filler_i, fill_value=self.filler_size_y[i], dtype=self.node_size_y.dtype))
                    filler_node_area_i = num_filler_i * (self.filler_size_x[i]*self.filler_size_y[i])
                self.total_filler_node_area += filler_node_area_i

        for rId in self.fixed_rsrcIds:
            if self.node_count[rId] > 0:
                logging.info("Region: %d [%s] #fixed_nodes = %d \n" 
                            % (rId, self.rsrcTypes[rId], self.node_count[rId]))

        self.total_movable_node_area_fence_region = np.array(self.total_movable_node_area_fence_region, dtype=self.dtype)
        self.num_movable_nodes_fence_region = np.array(self.num_movable_nodes_fence_region, dtype=np.int32)

        if params.enable_fillers:
            # the way to compute this is still tricky; we need to consider place_io together on how to
            # summarize the area of fixed cells, which may overlap with each other.
            self.filler_start_map = np.cumsum([0]+self.num_filler_nodes_fence_region)
            self.num_filler_nodes_fence_region = np.array(self.num_filler_nodes_fence_region, dtype=np.int32)
            self.node_size_x = np.concatenate([self.node_size_x] + filler_node_size_x_list)
            self.node_size_y = np.concatenate([self.node_size_y] + filler_node_size_y_list)
        else:
            self.total_filler_node_area = 0
            self.num_filler_nodes = 0
            filler_size_x, filler_size_y = 0, 0
            if(len(self.region_boxes) > 0):
                self.filler_start_map = np.zeros(len(self.region_boxes)+1, dtype=np.int32)
                self.num_filler_nodes_fence_region = np.zeros(len(self.num_filler_nodes_fence_region), dtype=np.int32)

        #TODO - For Stratix-IV: mlab is treated as lut type as sites for MLAB/LAB are not distinguished
        if self.num_mlab_nodes > 0:
            self.is_mlab_filler_node = np.zeros(self.num_nodes, dtype=np.int32)
            self.is_mlab_filler_node[self.filler_start_map[self.rFFIdx]:self.filler_start_map[self.rFFIdx]+self.num_mlab_nodes] = 1

    def write(self, pl_file):
        """
        @brief write placement solution as .pl file
        @Use as intermediate - does not contain VPR output format
        @param pl_file .pl file 
        """
        tt = time.time()
        #logging.info("writing to %s" % (pl_file))

        if self.num_ccNodes == 0:
            node_x = self.node_x
            node_y = self.node_y
            node_z = self.node_z
            str_node_names = self.node_names
            node_area = self.node_size_x*self.node_size_y
        else:
            node_x = self.org_node_x
            node_y = self.org_node_y
            node_z = self.org_node_z
            str_node_names = self.org_node_names
            node_area = self.org_node_size_x*self.org_node_size_y

            #cc_length = self.cc_site_height
            #cc_node_x = node_x[self.is_cc_node == 1].astype(np.int32)
            #cc_node_y = node_y[self.is_cc_node == 1].astype(np.int32)

        content = ""

        for i in range(self.num_physical_nodes):
            #if self.is_cc_node[i] == 1:
            #    ccId = self.node2ccId_map[i]
            #    ccXloc = cc_node_x[ccId]
            #    #solution is the starting Slice
            #    currY = cc_node_y[ccId] + self.cc_site_height[ccId] -1
            #    ccZloc = 0
            #    ccElArea = round(self.node_size_y[i]/self.cc_element_count[ccId], 4)
            #    rStart = self.org_flat_cc2node_start_map[ccId]
            #    rEnd = self.org_flat_cc2node_start_map[ccId+1]
            #    for mId in range(rStart, rEnd):
            #        orgNodeId = self.org_flat_cc2node_map[mId]
            #        content += "%s %.6E %.6E %g %.6E" % (
            #                self.org_node_names[orgNodeId],
            #                ccXloc, 
            #                currY, 
            #                ccZloc,
            #                ccElArea
            #                )
            #        if mId < rEnd-1:
            #            content += "\n"
            #        ccZloc = ccZloc+1
            #        if ccZloc == self.slice_lut_capacity:
            #            ccZloc = 0;
            #            currY = currY-1
            #else:
            content += "%s %.6E %.6E %g %.6E" % (
                    str_node_names[i],
                    node_x[i], 
                    node_y[i], 
                    node_z[i],
                    node_area[i]
                    )
            if i < self.num_physical_nodes-1:
                content += "\n"

        with open(pl_file, "w") as f:
            f.write(content)
        logging.info("write placement solution to %s took %.3f seconds" % (pl_file, time.time()-tt))

    def writeFinalSolution(self, pl_file):
        """
        @brief write placement solution as .pl file
        @param pl_file .pl file 
        """
        tt = time.time()
        #logging.info("writing to %s" % (pl_file))

        if self.num_ccNodes == 0:
            node_x = self.node_x
            node_y = self.node_y
            node_z = self.node_z
            node_types = self.node_types
            str_node_names = self.node_names
            node2fence_region_map = self.node2fence_region_map
        else:
            node_x = self.org_node_x
            node_y = self.org_node_y
            node_z = self.org_node_z
            node_types = self.org_node_types
            str_node_names = self.org_node_names
            node2fence_region_map = self.org_node2fence_region_map

            #cc_length = self.cc_site_height
            #cc_node_x = node_x[self.is_cc_node == 1].astype(np.int32)
            #cc_node_y = node_y[self.is_cc_node == 1].astype(np.int32)

        content = ""
        #node_area = self.node_size_x*self.node_size_y

        if self.siteOutValues.shape[0] == 0:
            for i in range(self.num_physical_nodes):
                #if self.is_cc_node[i] == 1:
                #    ccId = self.node2ccId_map[i]
                #    ccXloc = cc_node_x[ccId]
                #    #solution is the starting Slice
                #    currY = cc_node_y[ccId] + self.cc_site_height[ccId] -1
                #    ccZloc = 0
                #    rStart = self.org_flat_cc2node_start_map[ccId]
                #    rEnd = self.org_flat_cc2node_start_map[ccId+1]
                #    for mId in range(rStart, rEnd):
                #        orgNodeId = self.org_flat_cc2node_map[mId]
                #        content += "%s %d %d %g" % (
                #                self.org_node_names[orgNodeId],
                #                ccXloc, 
                #                currY, 
                #                ccZloc
                #                )
                #        if mId < rEnd-1:
                #            content += "\n"
                #        ccZloc = ccZloc+1
                #        if ccZloc == self.slice_lut_capacity:
                #            ccZloc = 0;
                #            currY = currY-1
                #else:
                content += "%s %d %d %g" % (
                        str_node_names[i],
                        node_x[i], 
                        node_y[i], 
                        node_z[i]
                        )
                if i < self.num_physical_nodes-1:
                    content += "\n"
        else:
            for i in range(self.num_physical_nodes):
                #if self.is_cc_node[i] == 1:
                #    siteId = self.siteType2indexMap[self.rsrc2siteMap[self.rsrcTypes[node2fence_region_map[i]]]]
                #    zVal = 0
                #    sVal = 0
                #    ccId = self.node2ccId_map[i]
                #    ccXloc = cc_node_x[ccId]
                #    #solution is the starting Slice
                #    currY = cc_node_y[ccId] + self.cc_site_height[ccId] -1
                #    ccZloc = 0
                #    ccElArea = round(self.node_size_y[i]/self.cc_element_count[ccId], 4)
                #    rStart = self.org_flat_cc2node_start_map[ccId]
                #    rEnd = self.org_flat_cc2node_start_map[ccId+1]
                #    for mId in range(rStart, rEnd):
                #        orgNodeId = self.org_flat_cc2node_map[mId]
                #        if self.siteOutCoordinates[siteId] == 'z':
                #            sVal = ccZloc
                #            zVal = self.siteOutValues[siteId]
                #        elif self.siteOutCoordinates[siteId] == 's':
                #            zVal = ccZloc
                #            sVal = self.siteOutValues[siteId]
                #        content += "%s %d %d %g %g %s" % (
                #                self.org_node_names[orgNodeId],
                #                ccXloc, 
                #                currY, 
                #                zVal,
                #                sVal,
                #                self.org_node_types[orgNodeId]
                #                )
                #        if mId < rEnd-1:
                #            content += "\n"
                #        ccZloc = ccZloc+1
                #        if ccZloc == self.slice_lut_capacity:
                #            ccZloc = 0;
                #            currY = currY-1
                #else:
                siteId = self.siteType2indexMap[self.rsrc2siteMap[self.rsrcTypes[node2fence_region_map[i]]]]
                zVal = 0
                sVal = 0
                if self.siteOutCoordinates[siteId] == 'z':
                    sVal = node_z[i]
                    zVal = self.siteOutValues[siteId]
                elif self.siteOutCoordinates[siteId] == 's':
                    zVal = node_z[i]
                    sVal = self.siteOutValues[siteId]
                content += "%s %d %d %g %g %s" % (
                        str_node_names[i],
                        node_x[i], 
                        node_y[i], 
                        zVal,
                        sVal,
                        node_types[i]
                        )
                if i < self.num_physical_nodes-1:
                    content += "\n"

        with open(pl_file, "w") as f:
            f.write(content)
        logging.info("write placement solution to %s took %.3f seconds" % (pl_file, time.time()-tt))

    #Use for debug - Does not support macro mode
    def writeMapSolution(self):
        """
        @brief write mapped placement solution as .pl file
        """
        tt = time.time()
        #logging.info("writing to %s" % (pl_file))

        node_x = self.node_x
        node_y = self.node_y
        node_z = self.node_z

        pl_file = "mapped_design_final.pl"

        content = ""

        if self.siteOutValues.shape[0] == 0:
            for i in range(self.num_physical_nodes):
                content += "%s %d %d %g" % (
                            "inst_"+str(i),
                            node_x[i], 
                            node_y[i], 
                            node_z[i]
                            )
                if i < self.num_physical_nodes-1:
                    content += "\n"
        else:
            for i in range(self.num_physical_nodes):
                siteId = self.siteType2indexMap[self.rsrc2siteMap[self.rsrcTypes[self.node2fence_region_map[i]]]]
                zVal = 0
                sVal = 0
                if self.siteOutCoordinates[siteId] == 'z':
                    sVal = node_z[i]
                    zVal = self.siteOutValues[siteId]
                elif self.siteOutCoordinates[siteId] == 's':
                    zVal = node_z[i]
                    sVal = self.siteOutValues[siteId]
                content += "%s %d %d %g %g %s" % (
                        "inst_"+str(i),
                        node_x[i], 
                        node_y[i], 
                        zVal,
                        sVal,
                        self.node_types[i]
                        )
                if i < self.num_physical_nodes-1:
                    content += "\n"

        with open(pl_file, "w") as f:
            f.write(content)
        logging.info("write out mapped solution to %s took %.3f seconds" % (pl_file, time.time()-tt))

    def apply(self, node_x, node_y, node_z):
        """
        @brief apply placement solution and update database 
        """

        if self.num_ccNodes == 0:
            # assign solution
            self.node_x[:self.num_movable_nodes] = node_x[:self.num_movable_nodes]
            self.node_y[:self.num_movable_nodes] = node_y[:self.num_movable_nodes]
            self.node_z[:self.num_movable_nodes] = node_z[:self.num_movable_nodes]
            node_x = self.node_x
            node_y = self.node_y
            node_z = self.node_z
        else:
            # assign solution
            self.org_node_x[:self.num_movable_nodes] = node_x[:self.num_movable_nodes]
            self.org_node_y[:self.num_movable_nodes] = node_y[:self.num_movable_nodes]
            self.org_node_z[:self.num_movable_nodes] = node_z[:self.num_movable_nodes]
            node_x = self.org_node_x
            node_y = self.org_node_y
            node_z = self.org_node_z

        # update raw database 
        place_io.PlaceIOFunction.apply(self.rawdb, node_x.astype(self.dtype), node_y.astype(self.dtype), node_z.astype(np.int32))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        logging.error("One input parameters in json format in required")

    params = Params.Params()
    params.load(sys.argv[sys.argv[1]])
    logging.info("parameters = %s" % (params))

    db = PlaceDB()
    db(params)

    db.print_node(1)
    db.print_net(1)
    db.print_row(1)

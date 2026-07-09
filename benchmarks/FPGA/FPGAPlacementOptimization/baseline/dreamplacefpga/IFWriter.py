##
# @file   IFWriter.py
# @author Zhili Xiong
# @date   Dec 2022
# @brief  Convert bookshelf outputs to interchange .phys file.
#

import capnp
import capnp.lib.capnp
capnp.remove_import_hook()

import os
import sys 
import time
import gzip 
import enum
import numpy as np 
import logging
import Params
import dreamplacefpga 
import dreamplacefpga.ops.place_io.place_io as place_io 
import pdb 
from collections import namedtuple
from Params import *
from PlaceDB import *


NO_TRAVERSAL_LIMIT = 2**63 - 1

NESTING_LIMIT = 1024

PhysicalNet = namedtuple('PhysicalNet', 'name type sources stubs stubNodes')


class IFWriter():
    """ IFWirter calss to write out IF file from phys_netlist. 
    phys_netlist - object input, contains all the data of each field in PhysicalNetlist.capnp
    """
    def __init__(self, schema_dir):
        """ initialize and compile PhysicalNetlist.capnp """
        import_path = [os.path.dirname(os.path.dirname(capnp.__file__))]
        # import_path.append(os.path.join(schema_dir, '../../schema'))
        import_path.append('IFsupport')
        self.physical_netlist_capnp = capnp.load(os.path.join(schema_dir, 'PhysicalNetlist.capnp'), imports=import_path)
        self.strList = []
        self.str2idx = {}

    def StringIdx(self, string):
        """ build strList and return the index """
        if string not in self.str2idx:
            self.str2idx[string] = len(self.strList)
            self.strList.append(string)

        return self.str2idx[string]
 
    def build_IF(self, phys_netlist):
        """ build IF object from phys_netlist 
        
        phys_netlist - object input, contains all the data of each field in PhysicalNetlist.capnp
        struct PhysNetlist {
            part         @0 : Text;
            placements   @1 : List(CellPlacement);
            physNets     @2 : List(PhysNet);
            physCells    @3 : List(PhysCell);
            strList      @4 : List(Text) $hashSet();
            siteInsts    @5 : List(SiteInstance);
            properties   @6 : List(Property);
            nullNet      @7 : PhysNet;
        }
        """
        # initialize a new capnp object 
        physical_netlist = self.physical_netlist_capnp.PhysNetlist.new_message()
 
        # part name in textStringIdx
        # part         @0 : Text;
        physical_netlist.part = phys_netlist.part
        
        # List of placement
        # placements   @1 : List(CellPlacement);
        placements = physical_netlist.init('placements', len(phys_netlist.placements))
        for i in range(len(phys_netlist.placements)): 
        #   struct CellPlacement {
        #   cellName      @0 : StringIdx $stringRef();
        #   type          @1 : StringIdx $stringRef();
        #   site          @2 : StringIdx $stringRef();
        #   bel           @3 : StringIdx $stringRef();
        #   pinMap        @4 : List(PinMapping);
        #   otherBels     @5 : List(StringIdx) $stringRef();
        #   isBelFixed    @6 : Bool;
        #   isSiteFixed   @7 : Bool;
        #   altSiteType   @8 : StringIdx $stringRef();
        # }
            placement = phys_netlist.placements[i]
            # cellName
            placements[i].cellName = self.StringIdx(placement.cell_name)
            # type
            placements[i].type = self.StringIdx(placement.cell_type)
            # site
            placements[i].site = self.StringIdx(placement.site_name)
            # bel
            placements[i].bel = self.StringIdx(placement.bel_name)
            # pinMap
            pinMap = placements[i].init('pinMap', len(placement.pins))
            for j in range(len(placement.pins)):
            #   struct PinMapping {
            #   cellPin    @0 : StringIdx $stringRef();
            #   bel        @1 : StringIdx $stringRef();
            #   belPin     @2 : StringIdx $stringRef();
            #   isFixed    @3 : Bool;
            #   union {
            #   multi     @4 : Void;
            #   otherCell @5 : MultiCellPinMapping;
            #   }
                pins = placement.pins[j]
                # cellPin
                pinMap[j].cellPin = self.StringIdx(pins[0])
                pinMap[j].bel = self.StringIdx(pins[1])
                pinMap[j].belPin = self.StringIdx(pins[2])
                pinMap[j].isFixed = False

            placements[i].isBelFixed = True
            placements[i].isSiteFixed = True
            placements[i].altSiteType = self.StringIdx('SLICE_X57Y129')
        
        # siteInsts
        site_insts = physical_netlist.init('siteInsts', len(phys_netlist.siteInsts))
        for idx, (key, value) in enumerate(phys_netlist.siteInsts.items()):
            site_insts[idx].site = self.StringIdx(key)
            site_insts[idx].type = self.StringIdx(value)

        # physCells
        phys_cells = physical_netlist.init('physCells', len(phys_netlist.physCells))
        for idx, (cell_name, cell_type) in enumerate(phys_netlist.physCells.items()):
            phys_cells[idx].cellName = self.StringIdx(cell_name)
            phys_cells[idx].physType = self.physical_netlist_capnp.PhysNetlist.PhysCellType.__dict__[
                cell_type.lower()]

        # properties
        properties = physical_netlist.init('properties', 2)
        properties[0].key = self.StringIdx('DISABLE_AUTO_IO_BUFFERS')
        properties[0].value = self.StringIdx('0')
        properties[1].key = self.StringIdx('OUT_OF_CONTEXT')
        properties[1].value = self.StringIdx('0')

        # nullNet
        physical_netlist.nullNet.name = self.StringIdx('SLICE_X57Y129')

        # PhysNet
        nets = physical_netlist.init('physNets', len(phys_netlist.nets))
        
        for idx, net in enumerate(phys_netlist.nets):
            net_obj = nets[idx]

            net_obj.name = self.StringIdx(net.name)
            net_obj.init('sources', len(net.sources))
            for root_obj, root in zip(net_obj.sources, net.sources):
                root.output_interchange(root_obj, self.StringIdx)

            net_obj.init('stubs', len(net.stubs))
            for stub_obj, stub in zip(net_obj.stubs, net.stubs):
                stub.output_interchange(stub_obj, self.StringIdx)

            net_obj.type = self.physical_netlist_capnp.PhysNetlist.NetType.__dict__[
                net.type.name.lower()]
            
        # strList
        physical_netlist.init('strList', len(self.strList))

        for idx, s in enumerate(self.strList):
            physical_netlist.strList[idx] = s

        return physical_netlist 

    def write_IF(self, physical_netlist, if_file):
        """ Write out IF into file 
        The file name is the design_name
        """
        # zipped the file into gzip file
        with gzip.open(if_file, 'wb') as f_zip:
            f_zip.write(physical_netlist.to_bytes())


class Cellplacement():
    """ Cellplacement class for constructing placement of a single cell.
        struct CellPlacement {
            cellName      @0 : StringIdx $stringRef();
            type          @1 : StringIdx $stringRef();
            site          @2 : StringIdx $stringRef();
            bel           @3 : StringIdx $stringRef();
            pinMap        @4 : List(PinMapping);
            otherBels     @5 : List(StringIdx) $stringRef();
            isBelFixed    @6 : Bool;
            isSiteFixed   @7 : Bool;
            altSiteType   @8 : StringIdx $stringRef();
        }
    """
    def __init__(self, cell_name, cell_type, site_name, bel_name):
        """ initialize placement information """
        self.cell_name = cell_name
        self.cell_type = cell_type
        self.site_name = site_name
        self.bel_name = bel_name
        self.pins = []


    def add_pins(self, cellpin, belpin):
        """ add pins for cell
        struct PinMapping {
            cellPin    @0 : StringIdx $stringRef();
            bel        @1 : StringIdx $stringRef();
            belPin     @2 : StringIdx $stringRef();
            isFixed    @3 : Bool;
            union {
            multi     @4 : Void;
            otherCell @5 : MultiCellPinMapping;
        }
        """
        self.pins.append((cellpin, self.bel_name, belpin))


def add_branch(branch_obj, phys_node, string_idx):
    """ Add a branch to continue outputting the interchange to capnp object. 
    
    branch_obj - One RouteBranch capnp object from PhysicalNetlist
    phys_node - an object of PhysicalBelpin or PhysicalSitepip
    
    """
    branch_obj.init('branches', len(phys_node.branches))

    for branch_obj, branch in zip(branch_obj.branches, phys_node.branches):
        branch.output_interchange(branch_obj, string_idx)


class PhysicalBelPin():
    """ PhysicalBelpin class for intra-site routing.
    struct PhysBelPin {
        site @0 : StringIdx $stringRef();
        bel  @1 : StringIdx $stringRef();
        pin  @2 : StringIdx $stringRef();
    }
    """

    def __init__(self, site_name, bel_name, pin_name):
        self.site_name = site_name
        self.bel_name = bel_name
        self.pin_name = pin_name

        self.branches = []

    def output_interchange(self, branch_obj, string_idx):
        """ Add one route segment and all the branches under it.
        branch_obj - One RouteBranch capnp object from PhysicalNetlist
        
        struct RouteBranch {
            routeSegment : union {
            belPin  @0 : PhysBelPin;
            sitePin @1 : PhysSitePin;
            pip     @2 : PhysPIP;
            sitePIP @3 : PhysSitePIP;
            }
            branches @4 : List(RouteBranch);
        }
        string_idx - function that returns the index of strList in PhysicalNetlist
        """
        branch_obj.routeSegment.init('belPin') 
        branch_obj.routeSegment.belPin.site = string_idx(self.site_name)
        branch_obj.routeSegment.belPin.bel = string_idx(self.bel_name)
        branch_obj.routeSegment.belPin.pin = string_idx(self.pin_name)

        add_branch(branch_obj, self, string_idx)

    def get_device_resource(self, site_types, device_resources):
        """ Get device resource that corresponds to this class. """
        return device_resources.bel_pin(self.site_name, site_types[self.site_name],
                                        self.bel_name, self.pin_name)

    def to_tuple(self):
        """ Create tuple suitable for sorting this object.
        This tuple is used for sorting against other routing branch objects
        to generate a canonical routing tree.
        """
        return ('bel_pin', self.site_name, self.bel_name, self.pin_name)


class PhysicalSitePip():
    """ PhysicalSitepip class for intra-site routing.
    struct PhysSitePIP {
        site    @0 : StringIdx $stringRef();
        bel     @1 : StringIdx $stringRef();
        pin     @2 : StringIdx $stringRef();
        isFixed @3 : Bool;
        union {
        isInverting @4 : Bool;
        inverts     @5 : Void;
        }
    }
    """

    def __init__(self, site_name, bel_name, pin_name):
        self.site_name = site_name
        self.bel_name = bel_name
        self.pin_name = pin_name
        self.is_inverting = False

        self.branches = []

    def output_interchange(self, branch_obj, string_idx):
        """ Add one route segment and all the branches under it.
        """
        branch_obj.routeSegment.init('sitePIP') 
        branch_obj.routeSegment.sitePIP.site = string_idx(self.site_name)
        branch_obj.routeSegment.sitePIP.bel = string_idx(self.bel_name)
        branch_obj.routeSegment.sitePIP.pin = string_idx(self.pin_name)
        branch_obj.routeSegment.sitePIP.isFixed = False
        branch_obj.routeSegment.sitePIP.isInverting = False

        add_branch(branch_obj, self, string_idx)

    def get_device_resource(self, site_types, device_resources):
        """ Get device resource that corresponds to this class. """
        return device_resources.site_pip(self.site_name, site_types[self.site_name],
                                         self.bel_name, self.pin_name)

    def to_tuple(self):
        """ Create tuple suitable for sorting this object.
        This tuple is used for sorting against other routing branch objects
        to generate a canonical routing tree.
        """
        return ('site_pip', self.site_name, self.bel_name, self.pin_name, self.is_inverting)


def convert_tuple_to_object(site, tup):
    """ Convert physical netlist tuple to object.
    Physical netlist tuples are light weight ways to represent the physical
    net tree.
    site (Site) - Site object that tuple belongs too.
    tup (tuple) - Tuple that is either a bel pin or site pip.
    Returns - PhysicalBelPin or PhysicalSitePip based on
              tuple.
    """
    if tup[0] == 'bel_pin':
        _, bel, pin = tup
        return PhysicalBelPin(site.name, bel, pin)
    elif tup[0] == 'site_pip':
        _, bel, pin = tup
        return PhysicalSitePip(site.name, bel, pin)
    else:
        return False


def add_site_routing_children(site, parent_obj, parent_key, site_routing):
    """ Convert site_routing map into Physical* python objects.
    site (Site) - Site object that contains site routing.
    parent_obj (Physical* python object) - Parent Physical* object to add new
                                         branches too.
    parent_key (tuple) - Site routing tuple for current parent_obj.
    site_routing (dict) - Map of parent site routing tuple to a set of
                          child site routing tuples.
    inverted_root (list) - List of physical net sources for the inverted
                           signal (e.g. a constant 1 net inverts to the
                           constant 0 net)
    """
    if parent_key in site_routing:
        for child in site_routing[parent_key]:

            obj = convert_tuple_to_object(site, child)
            parent_obj.branches.append(obj)

            add_site_routing_children(site, obj, child, site_routing)



def create_site_routing(site, net_roots, site_routing):
    """ Convert site_routing into map of nets to site local sources.
    site (Site) - SiteInst object that contains site routing.
    net_roots (dict) - Map of root site routing tuples to the net name for
                       this root.
    site_routing (dict) - Map of parent site routing tuple to a set of
                          child site routing tuples.
    Returns dict of nets to Physical* objects that represent the site local
    sources for that net.
    """
    nets = {}

    for root, net_name in net_roots.items():
        if net_name not in nets:
            nets[net_name] = []

        root_obj = convert_tuple_to_object(site, root)
        add_site_routing_children(site, root_obj, root, site_routing)
        

        nets[net_name].append(root_obj)

    return nets

class SiteInst():
    """
    This class has the site router and site instances;
    """
    def __init__(self, name):
        self.name = name
        self.cells = {}
        self.net_belpins = {}
        self.lut_map = {}

    def add_cells(self, node_name, cellplacement):
        """ map from a node name in bookshelf to a list of cellplacement objetcs. """
        if node_name not in self.cells:
            self.cells[node_name] = []
            
        self.cells[node_name].append(cellplacement)

    def add_belpins(self, net_name, belpin_tup):
        """ map from a net name to a list of belpin tuples """
        if net_name not in self.net_belpins:
            self.net_belpins[net_name] = []

        self.net_belpins[net_name].append(belpin_tup)

    def A6_LUT(self):
        """ sorted luts """

        vcc_tup = []
        A6_sitein = {
            'A': ('bel_pin', 'A6', 'A6'),
            'B': ('bel_pin', 'B6', 'B6'),
            'C': ('bel_pin', 'C6', 'C6'),
            'D': ('bel_pin', 'D6', 'D6'),
            'E': ('bel_pin', 'E6', 'E6'),
            'F': ('bel_pin', 'F6', 'F6'),
            'G': ('bel_pin', 'G6', 'G6'),
            'H': ('bel_pin', 'H6', 'H6')
        }
        self.lut_map = {
            'A': [],
            'B': [],
            'C': [],
            'D': [],
            'E': [],
            'F': [],
            'G': [],
            'H': []
        }

        for node, cellplacements in self.cells.items():
            for cell in cellplacements:
                if cell.bel_name[-3:] == 'LUT':
                    self.lut_map[cell.bel_name[0]].append(cell)

        for key, cells in self.lut_map.items():
            if len(self.lut_map[key]) == 2 and '/' not in self.lut_map[key][0].cell_name:
                vcc_tup.append(A6_sitein[key])

        return vcc_tup


    def site_router(self, routing_graph, site_in, site_out):
        
        nets = {}
        net_roots = {}
        site_routing = {}
        net_source = {}
        constant_nets = {
            0 : 'GLOBAL_LOGIC0',
            1 : 'GLOBAL_LOGIC1'
        }

        clk_net = 'clk_BUFGP_net_top_wire'
    
        gnd_tup = ('bel_pin', 'HARD0GND', '0')

        # add the us+ rst
        rst_tup = [('bel_pin', 'SRST_B1', 'SRST_B1'), ('bel_pin', 'SRST_B2', 'SRST_B2'), ('bel_pin', 'SRST1', 'SRST1'), ('bel_pin', 'SRST2', 'SRST2')]

        bufce_tup = [('bel_pin', 'CE_PRE_OPTINV', 'CE_PRE_OPTINV')]

        vcc_tup = self.A6_LUT()
        
        for net_name, belpins in self.net_belpins.items():

            is_source = False
            stubs = []
            skip_flag = False

            for belpin in belpins:
                # the net has its source in this site
                # belpin is source 
                if belpin in routing_graph:
                    net_roots[belpin] = net_name
                    site_routing[belpin] = []
                    net_source[net_name] = belpin
                    is_source = True

                    bel_name = belpin[1]
                    if bel_name[-4:] == '6LUT' and len(self.lut_map[bel_name[0]]) == 2:
                        skip_flag = True

                    if skip_flag == False:
                        for child_tup in routing_graph[belpin]:
                            # through site pip
                            if child_tup[0] == 'site_pip':
                                sitepip_in = child_tup
                                sitepip_out = routing_graph[sitepip_in]
                                for out in routing_graph[sitepip_out]:
                                    if out in site_out:
                                        site_routing[belpin].append(sitepip_in)
                                        site_routing[sitepip_in] = []
                                        site_routing[sitepip_in].append(sitepip_out)
                                        site_routing[sitepip_out] = []

                # belpin is stub
                else: 
                    stubs.append(belpin)

            for stub in stubs:
                parent_found = False

                for parent in site_routing:
                    if stub in routing_graph[parent]:
                        site_routing[parent].append(stub)
                        parent_found = True

                if parent_found == True:
                    continue

                if is_source == True:
                    source = net_source[net_name]
                    # site wire
                    if stub in routing_graph[source]:
                        site_routing[source].append(stub)
                        parent_found = True

                    # sitepip
                    else:
                        for child in routing_graph[source]:
                            if child[0] == 'site_pip':
                                sitepip_in = child
                                sitepip_out = routing_graph[sitepip_in]
                                if stub in routing_graph[sitepip_out]:
                                    site_routing[source].append(sitepip_in)
                                    site_routing[sitepip_in] = []
                                    site_routing[sitepip_in].append(sitepip_out)
                                    site_routing[sitepip_out] = []
                                    site_routing[sitepip_out].append(stub)
                                    parent_found = True

                if parent_found == True:
                    continue
            
                for site_pin in site_in:
                    site_in_found = False
                    # site wire
                    if stub in routing_graph[site_pin]:
                        net_roots[site_pin] = net_name
                        site_routing[site_pin] = []
                        site_routing[site_pin].append(stub)
                        site_in_found = True

                    # site pip
                    else:
                        for pin in routing_graph[site_pin]:
                            if pin[0] == 'site_pip':
                                sitepip_in = pin
                                sitepip_out = routing_graph[sitepip_in]
                                if stub in routing_graph[sitepip_out] : 
                                    net_roots[site_pin] = net_name
                                    site_routing[site_pin] = []
                                    site_routing[site_pin].append(sitepip_in)
                                    site_routing[sitepip_in] = []
                                    site_routing[sitepip_in].append(sitepip_out)
                                    site_routing[sitepip_out] = []
                                    site_routing[sitepip_out].append(stub)
                                    site_in_found = True

                    if site_in_found == True:
                        break

        if self.name[:5] == 'SLICE':
            # for rst_in in rst_tup:
            #     if rst_in not in site_routing and rst_in in site_in:
            #         net_roots[rst_in] = constant_nets[1]
            #         child = routing_graph[rst_in][0]
            #         site_routing[rst_in] = []
            #         site_routing[rst_in].append(child)
            #         child2 = routing_graph[child]
            #         site_routing[child2] = []
            #         net_roots[child2] = constant_nets[0]
            
            net_roots[gnd_tup] = constant_nets[0]
            site_routing[gnd_tup] = []


            for vcc_in in vcc_tup:
                net_roots[vcc_in] = constant_nets[1]
                site_routing[vcc_in] = []

        if self.name[:3] == 'DSP':
            dsp_bel_map = {}
            dsp_pin_map = {}
            dsp_cell_pin = {}
            for node_name in self.cells:
                for cellplacement in self.cells[node_name]:
                    cell_name = cellplacement.cell_name
                    bel_name = cellplacement.bel_name
                    dsp_bel_map[bel_name] = node_name
                    for pin in cellplacement.pins:
                        pin_name = pin[0].replace('[', '<')
                        pin_name = pin_name.replace(']', '>')
                        dsp_pin_map[pin[2]] = pin_name
                        if pin[2][:7] == 'PATTERN':
                            cell_pin = pin[0].replace('_','')
                            dsp_cell_pin[pin[2]] = cell_pin
                        else:
                            dsp_cell_pin[pin[2]] = pin[0]


            for bel_out in routing_graph:                
                if bel_out not in site_routing and bel_out[1] in dsp_bel_map:
                    site_routing[bel_out] = []
                    for bel_in in routing_graph[bel_out]:
                        if bel_in not in site_out: 
                            net_name = dsp_bel_map[bel_out[1]] + '/' + bel_out[1] + '.' + dsp_pin_map[bel_out[2]]              
                            site_routing[bel_out].append(bel_in)
                            net_roots[bel_out] = net_name
                        else:
                            if bel_out[2] in dsp_cell_pin:
                                net_name = dsp_bel_map[bel_out[1]] + '/' + dsp_cell_pin[bel_out[2]]
                                net_roots[bel_out] = net_name


        if self.name[:3] == 'RAM':
            if gnd_tup in routing_graph:
                net_roots[gnd_tup] = constant_nets[1]
                site_routing[gnd_tup] = []
                for gnd_child in routing_graph[gnd_tup]:
                    site_routing[gnd_tup].append(gnd_child)   
                         
                       
        nets = create_site_routing(self, net_roots, site_routing)


        return nets, net_source


class PhysicalNetType(enum.Enum):
    # Net is just a signal, not a VCC or GND tied net.
    Signal = 0
    # Net is tied to GND.
    Gnd = 1
    # Net is tied to VCC.
    Vcc = 2

class PhysicalNetlist:
    """ Physical Netlist class for adding each field into an object
    self.add_cellplacement() 
    self.add_site_instance()
    self.add_physical_cell()
    """
    def __init__(self, part):
        self.part = part
        self.placements = []
        self.nets = []
        self.physCells = {}
        self.siteInsts = {}
        self.null_nets = []

    def add_cellplacement(self, cellplacement):
        """ Add cellplacement into a  list 
        cellplacement (object) - object of cellplacement
        """
        self.placements.append(cellplacement)

    def add_site_instance(self, site_name, site_type):
        """ Add site instance to a  map """
        self.siteInsts[site_name] = site_type
    
    def add_physical_cell(self, cell_name, cell_type):
        """ Add physical cell instance
        cell_name (str) - Name of physical cell instance
        cell_type (str) - Value of physical_netlist.PhysCellType
        PhysicalSitePip
        """
        self.physCells[cell_name] = cell_type

    def add_physical_net(self,
                         net_name,
                         sources,
                         stubs,
                         stubNodes,
                         net_type=PhysicalNetType.Signal):
        """ Adds a physical net to the physical netlist.
        net_name (str) - Name of net.
        sources (list of
            physical_netlist.PhysicalBelPin - or -
            physical_netlist.PhysicalSitePin - or -
            physical_netlist.PhysicalSitePip - or -
            physical_netlist.PhysicalPip
            ) - Sources of this net.
        stubs (list of
            physical_netlist.PhysicalBelPin - or -
            physical_netlist.PhysicalSitePin - or -
            physical_netlist.PhysicalSitePip - or -
            physical_netlist.PhysicalPip
            ) - Stubs of this net.
        net_type (PhysicalNetType) - Type of net.
        """
        self.nets.append(
            PhysicalNet(
                name=net_name, type=net_type, sources=sources, stubs=stubs, stubNodes=stubNodes))

class CellBel():
    """ Map cell into bel, mainly for the pin mapping.
    strs - strList from DeviceResources
    mapping - cellBelMap from DeviceResources
    """
    def __init__(self, strs, mapping):
        """ Build a pin map from cell pin to bel pin. 
        
        Now only used the common pins.
        
        Find a cell's pin mapping by its [site_type, bel]
        
        """
        self.cell = strs[mapping.cell]
        self.site_types_and_bels = set()
        self.common_pins = {}
        self.parameter_pins = {}
        self.site_bel_map = {}

        # This is for common pin mapping 
        for common_pins in mapping.commonPins:
            pin_map = {}

            for pin in common_pins.pins:
                bel_pin = strs[pin.belPin]
                pin_map[bel_pin] = strs[pin.cellPin]

            for site_type_and_bels in common_pins.siteTypes:
                site_type = strs[site_type_and_bels.siteType]
                for bel_idx in site_type_and_bels.bels:
                    bel = strs[bel_idx]
                    self.site_types_and_bels.add((site_type, bel))
                    self.common_pins[site_type, bel] = pin_map

        for parameter_pins in mapping.parameterPins:
            pin_map = {}

            for pin in parameter_pins.pins:
                bel_pin = strs[pin.belPin]

                pin_map[bel_pin] = strs[pin.cellPin]

            for parameter_site_type_and_bel in parameter_pins.parametersSiteTypes:
                site_type = strs[parameter_site_type_and_bel.siteType]
                bel = strs[parameter_site_type_and_bel.bel]

                self.site_types_and_bels.add((site_type, bel))

                parameter = parameter_site_type_and_bel.parameter
                key = strs[parameter.key]

                parameter_which = parameter.which()
                if parameter_which == 'textValue':
                    value = strs[parameter.textValue]
                elif parameter_which == 'intValue':
                    value = str(parameter.intValue)
                elif parameter_which == 'boolValue':
                    value = str(parameter.boolValue)


                self.parameter_pins[site_type, bel, key, value] = pin_map



class Cell():
    def __init__(self, name, capnp_index=0, property_map={}):
        """ Create a new cell. """
        self.name = name
        self.property_map = property_map
        self.view = "netlist"
        self.capnp_index = capnp_index
        self.cell_instances = {}
    
class Library():
    """ Library of cells. """

    def __init__(self, name):
        self.name = name
        self.cells = {}

    def add_cell(self, cell):
        assert cell.name not in self.cells, cell.name
        self.cells[cell.name] = cell

class Site(
        namedtuple(
            'Site',
            'tile_index tile_name_index site_index tile_type_site_type_index site_type_index alt_index site_type_name'
        )):
    pass


class SiteWire(
        namedtuple('SiteWire', 'tile_index site_index site_wire_index')):
    def name(self, site_type):
        """
        struct SiteWire {
            name   @0 : StringIdx $stringRef();
            pins   @1 : List(BELPinIdx) $belPinRef();
        }
        """
        return site_type.site_wire_names[self.site_wire_index]


class SitePinNames(
        namedtuple('SitePinNames',
                   'tile_name site_name site_type_name pin_name wire_name')):
    pass


class Bel():
    def __init__(self, site_type, strs, bel):
        self.site_type = site_type
        self.name = strs[bel.name]
        self.category = bel.category
        self.type = strs[bel.type]
        self.bel_pins = [bel_pin for bel_pin in bel.pins]

    def yield_pins(self, site, direction=None):
        for bel_pin in self.bel_pins:
            bel_name, bel_pin_name = self.site_type.bel_pin_index[bel_pin]
            bel_pin = self.site_type.bel_pin(site, bel_name, bel_pin_name)

            if direction and bel_pin.direction == direction:
                yield bel_pin


class SitePip():
    """ Site pip device resource object. """

    def __init__(self, site, in_bel_pin_index, out_bel_pin_index,
                 in_site_wire_index, out_site_wire_index):
        self.site = site
        self.in_bel_pin_index = in_bel_pin_index
        self.out_bel_pin_index = out_bel_pin_index
        self.in_site_wire_index = in_site_wire_index
        self.out_site_wire_index = out_site_wire_index


class BelPin():
    """ BEL Pin device resource object. """

    def __init__(self, site, name, bel_pin_index, site_wire_index, direction,
                 is_site_pin):
        self.site = site
        self.site_wire_index = site_wire_index
        self.name = name
        self.bel_pin_index = bel_pin_index
        self.direction = direction
        self.is_site_pin = is_site_pin


class SitePin():
    """ Site pin device resource object. """

    def __init__(self, site, site_pin_index, bel_pin_index, site_wire_index, direction):
        self.site = site
        self.site_pin_index = site_pin_index
        self.bel_pin_index = bel_pin_index
        self.site_wire_index = site_wire_index
        self.direction = direction


class Direction(enum.Enum):
    input = 0
    output = 1
    inout = 2


class SiteType():
    """ Object for looking up device resources from a site type.
    struct SiteType {
        name         @0 : StringIdx $stringRef();
        belPins      @1 : List(BELPin); # All BEL Pins in site type
        pins         @2 : List(SitePin);
        lastInput    @3 : UInt32; # Index of the last input pin
        bels         @4 : List(BEL);
        sitePIPs     @5 : List(SitePIP);
        siteWires    @6 : List(SiteWire);
        altSiteTypes @7 : List(SiteTypeIdx);
    }
    """
    def __init__(self, strs, site_type, site_type_index):
        self.site_type = strs[site_type.name]
        self.site_type_index = site_type_index


        bel_pin_index_to_site_wire_index = {}
        self.site_wire_names = []
        for site_wire_index, site_wire in enumerate(site_type.siteWires):
            self.site_wire_names.append(strs[site_wire.name])
            for bel_pin_index in site_wire.pins:
                bel_pin_index_to_site_wire_index[
                    bel_pin_index] = site_wire_index

        self.bel_pin_index = []
        self.bel_pins = {}
        for bel_pin_index, bel_pin in enumerate(site_type.belPins):
            bel_name = strs[bel_pin.bel]
            bel_pin_name = strs[bel_pin.name]
            direction = Direction[bel_pin.dir]
            if bel_pin_index in bel_pin_index_to_site_wire_index:
                site_wire_index = bel_pin_index_to_site_wire_index[
                    bel_pin_index]
            else:
                site_wire_index = None

            key = (bel_name, bel_pin_name)
            self.bel_pins[key] = bel_pin_index, site_wire_index, direction
            self.bel_pin_index.append(key)

        self.bel_pin_to_site_pins = {}
        self.site_pins = {}
        for site_pin_index, site_pin in enumerate(site_type.pins):
            site_pin_name = strs[site_pin.name]
            bel_pin_index = site_pin.belpin

            self.bel_pin_to_site_pins[bel_pin_index] = site_pin_index

            if bel_pin_index in bel_pin_index_to_site_wire_index:
                site_wire_index = bel_pin_index_to_site_wire_index[
                    bel_pin_index]
            else:
                site_wire_index = None

            self.site_pins[site_pin_name] = (site_pin_index, bel_pin_index,
                                             site_wire_index,
                                             Direction[site_pin.dir])

        self.site_pips = {}
        for site_pip in site_type.sitePIPs:
            out_bel_pin = site_type.belPins[site_pip.outpin]
            self.site_pips[site_pip.inpin] = strs[out_bel_pin.name]



        self.bels = []
        for bel in site_type.bels:
            self.bels.append(Bel(self, strs, bel))

    def bel_pin(self, site, bel, pin):
        """ Return BelPin device resource for BEL pin in site.
        site (Site) - Site tuple
        bel (str) - BEL name
        pin (str) - BEL pin name
        """
        bel_pin_index, site_wire_index, direction = self.bel_pins[bel, pin]

        return BelPin(
            site=site,
            bel_pin_index=bel_pin_index,
            name=pin,
            site_wire_index=site_wire_index,
            direction=direction,
            is_site_pin=bel_pin_index in self.bel_pin_to_site_pins,
        )

    def site_pin(self, site, device_resources, pin):
        """ Return SitePin device resource for site pin in site.
        site (Site) - Site tuple
        pin (str) - Site pin name
        """

        site_pin_index, bel_pin_index, site_wire_index, direction = self.site_pins[
            pin]

        site_pin_names = device_resources.get_site_pin(site, site_pin_index)

        return SitePin(
            site=site,
            site_pin_index=site_pin_index,
            bel_pin_index=bel_pin_index,
            site_wire_index=site_wire_index,
            direction=direction)

    def site_pip(self, site, bel, pin):
        """ Return SitePip device resource for site PIP in site.
        site (Site) - Site tuple
        bel (str) - BEL name containing site PIP.
        pin (str) - BEL pin name for specific edge.
        """

        key = bel, pin
        in_bel_pin_index, in_site_wire_index, direction = self.bel_pins[key]

        out_pin = self.site_pips[in_bel_pin_index]
        out_bel_pin_index, out_site_wire_index, direction = self.bel_pins[
            bel, out_pin]

        return SitePip(
            site=site,
            in_bel_pin_index=in_bel_pin_index,
            out_bel_pin_index=out_bel_pin_index,
            in_site_wire_index=in_site_wire_index,
            out_site_wire_index=out_site_wire_index)


    def site_routing_graph(self):
        """ Return routing graph for every site type 
        routing_graph (dict) - Map of parent site routing tuple to a set of
                          child site routing tuples.
        
        key - tuple of parent belpin
        value - tuples of children belpin
        3 cases here:
        1. belpin -> belpin, through sitewire
        2. belpin -> sitepip, through sitewire
        3. sitepip -> belpin, through sitepip
        """

        # from one belpin to another belpins through either sitewire or sitepip
        site_routing_graph = {}
        site_in = []
        site_out = []

        sitewire_parent = {}
        children_sitewire = {}

      
        for key, value in self.bel_pins.items():
            bel_name, bel_pin_name = key 
            bel_pin_index, site_wire_index, direction = value

            if bel_pin_index in self.site_pips and bel_name[2:] != 'LUT':
                in_bel_pin_index = bel_pin_index
                sitepip_in = 'site_pip', bel_name, bel_pin_name

                out_pin = self.site_pips[in_bel_pin_index]
                sitepip_out = 'bel_pin', bel_name, out_pin
                site_routing_graph[sitepip_in] = sitepip_out

            if direction in [Direction.output, Direction.inout]:
                # parent tuple
                parent_tup = 'bel_pin', bel_name, bel_pin_name
                site_routing_graph[parent_tup] = []
                sitewire_parent[site_wire_index] = parent_tup
                if bel_name in self.site_pins:
                    site_in.append(parent_tup)

            else:
                child_key = bel_name, bel_pin_name
                children_sitewire[child_key] = site_wire_index 
     

        
        for child_key, site_wire_index in children_sitewire.items():
            bel_name, bel_pin_name = child_key
            bel_pin_index, site_wire_index, direction =  self.bel_pins[child_key]

            if site_wire_index in sitewire_parent:
                parent_tup = sitewire_parent[site_wire_index]

                if bel_pin_index in self.site_pips and bel_name[2:] != 'LUT':
                    child_tup = 'site_pip', bel_name, bel_pin_name
                    site_routing_graph[parent_tup].append(child_tup)

                else:
                    child_tup = 'bel_pin', bel_name, bel_pin_name
                    site_routing_graph[parent_tup].append(child_tup)
                    if bel_name in self.site_pins:
                        site_out.append(child_tup)


        return site_routing_graph, site_in, site_out


class LogicalNetlist:
    """
    Parse Logical Netlist file. 
    This is for parameter pin mapping in BRAMs.
    However, all the parameter pins have the same properties and value in ISPD16 benchmarks.
    So the parameter pins have been hard-coded.
    For example,
    para_map['DOA_REG'] = '1'
    para_map['WRITE_WIDTH_A'] = '1'
    para_map['WRITE_WIDTH_B'] = '72'
    para_map['DOB_REG'] = '1'
    """
    def __init__(self, schema_dir):
        """ Read and compile logical netlist for FPGA02-12 benchmarks 
        
        """
        import_path = [os.path.dirname(os.path.dirname(capnp.__file__))]
        # add import path from the rapidwright java.capnp
        # import_path.append(os.path.join(schema_dir, '../../schema'))
        import_path.append('IFsupport')
        self.logical_netlist_capnp = capnp.load(os.path.join(schema_dir, 'LogicalNetlist.capnp'), imports=import_path)

        with open('FPGA02_rapidwright.netlist', 'rb') as in_f:
            f_comp = gzip.GzipFile(fileobj = in_f, mode='rb')

            with self.logical_netlist_capnp.Netlist.from_bytes(f_comp.read(), traversal_limit_in_words=NO_TRAVERSAL_LIMIT, nesting_limit=NESTING_LIMIT) as message:
                self.logical_netlist = message 

        self.strs = [s for s in self.logical_netlist.strList]

        self.string_index = {}
        for idx, s in enumerate(self.strs):
            self.string_index[s] = idx

        self.cell_list = self.logical_netlist.instList
        
        # for parameterPin mapping
        self.cell_prop_map = {}

        for cell_instance in self.cell_list:
            entries = cell_instance.propMap.entries
            cell_name = self.strs[cell_instance.name]
            if cell_name not in self.cell_prop_map:
                self.cell_prop_map[cell_name] = []

            for parameter in entries:
                key = self.strs[parameter.key]
                parameter_which = parameter.which()
                if parameter_which == 'textValue':
                    value = self.strs[parameter.textValue]
                elif parameter_which == 'intValue':
                    value = str(parameter.intValue)
                elif parameter_which == 'boolValue':
                    value = str(parameter.boolValue)

                self.cell_prop_map[cell_name].append((key,value))

                

class DeviceResources:
    """DeviceResources class to parse the part's placement resources.
    yield_cell_bel_mappings(self)
    get_library(self)
    get_macro_instance(self)
    get_site_type(self)
    get_packages
    """
    def __init__(self, schema_dir, part_name):
        """ Read and compile device resources for part assigned by part_name
        
        """
        import_path = [os.path.dirname(os.path.dirname(capnp.__file__))]
        # add import path from the rapidwright java.capnp
        # import_path.append(os.path.join(schema_dir, '../../schema'))
        import_path.append('IFsupport')
        self.device_resources_capnp = capnp.load(os.path.join(schema_dir, 'DeviceResources.capnp'), imports=import_path)
        
        device_file = os.path.join('IFsupport', part_name)
        with open(device_file + '.device', 'rb') as in_f:
            f_comp = gzip.GzipFile(fileobj = in_f, mode='rb')

            with self.device_resources_capnp.Device.from_bytes(f_comp.read(), traversal_limit_in_words=NO_TRAVERSAL_LIMIT, nesting_limit=NESTING_LIMIT) as message:
                self.device_resources = message 
        
        self.strs = [s for s in self.device_resources.strList]

        self.string_index = {}
        for idx, s in enumerate(self.strs):
            self.string_index[s] = idx

        self.site_type_names = []
        self.site_type_name_to_index = {}
        self.site_type_bels = {}
        # generate site_type object
        for site_type_index, site_type in enumerate(self.device_resources.siteTypeList):
            site_obj = SiteType(self.strs, site_type, site_type_index)
            site_type_name = self.strs[site_type.name]
            self.site_type_names.append(site_type_name)
            self.site_type_name_to_index[site_type_name] = site_type_index
            self.site_type_bels[site_type_name] = []
            site_bels = site_obj.bels
            for site_bel in site_bels:
                site_bel_name = site_bel.name
                self.site_type_bels[site_type_name].append(site_bel_name)

        tiletype_list = self.device_resources.tileTypeList
        sitetype_list = self.device_resources.siteTypeList
        
        self.site_types = {}
        self.site_type_map = {}
        self.alt_site_type_map = {}
        self.site_name_to_site = {}
        self.altPinsToPrimPins = {} 


        for tile_idx, tile in enumerate(self.device_resources.tileList):
            tile_name = self.strs[tile.name]
            tile_name_index = self.string_index[tile_name]

            for site_idx, site in enumerate(tile.sites):
                site_in_tile = self.strs[site.name]
                self.site_name_to_site[site_in_tile] = {}

                tile_type_site_type_index = site.type
                site_types = tiletype_list[tile.type].siteTypes  
                site_type_index = site_types[site.type].primaryType
                site_type_name = self.strs[sitetype_list[site_type_index].name]

                self.site_type_map[site_in_tile] = site_type_name

                self.site_name_to_site[site_in_tile][site_type_name] = Site(
                    tile_index=tile_idx,
                    tile_name_index=tile_name_index,
                    site_index=site_idx,
                    tile_type_site_type_index=tile_type_site_type_index,
                    site_type_index=site_type_index,
                    alt_index=None,
                    site_type_name=site_type_name)

                for alt_index, alt_site_type_index in enumerate(sitetype_list[site_type_index].altSiteTypes):
                    site_type_name = self.site_type_names[alt_site_type_index]
                    self.alt_site_type_map[site_in_tile] = site_type_name
                    self.site_name_to_site[site_in_tile][site_type_name] = Site(
                        tile_index=tile_idx,
                        tile_name_index=tile_name_index,
                        site_index=site_idx,
                        tile_type_site_type_index=tile_type_site_type_index,
                        site_type_index=alt_site_type_index,
                        alt_index=alt_index,
                        site_type_name=site_type_name)

        # self.tile_types = {}
        self.tile_wire_index_to_node_index = None


    def get_site_type_index(self, site_type_name):
        return self.site_type_name_to_index[site_type_name]

    def get_site_type(self, site_type_index):
        """ Get SiteType object for specified site type index. """
        if site_type_index not in self.site_types:
            self.site_types[site_type_index] = SiteType(
                self.strs,
                self.device_resources.siteTypeList[site_type_index],
                site_type_index)

        return self.site_types[site_type_index]


    def get_tile_name_at_site_name(self, site_name):
        """ Get Tile name at site name. """
        
        sites_dict = self.site_name_to_site[site_name]

        # Get the first site in the dict. Assume all alternative sites are at
        # the same tile
        site = list(sites_dict.values())[0]
        return self.strs[site.tile_name_index]

    def bel_pin(self, site_name, site_type, bel, pin):
        """ Return BelPin device resource for BEL pin in site.
        site_name (str) - Name of site
        site_type (str) - Name of specific site type being queried.
        bel (str) - BEL name containing site PIP.
        pin (str) - BEL pin name for specific edge.
        """
        site = self.site_name_to_site[site_name][site_type]
        return self.get_site_type(site.site_type_index).bel_pin(site, bel, pin)

    def site_pin(self, site_name, site_type, pin):
        """ Return SitePin device resource for site pin in site.
        site_name (str) - Name of site
        site_type (str) - Name of specific site type being queried.
        pin (str) - Site pin name
        """
        site = self.site_name_to_site[site_name][site_type]
        return self.get_site_type(site.site_type_index).site_pin(
            site, self, pin)

    def site_pip(self, site_name, site_type, bel, pin):
        """ Return SitePip device resource for site PIP in site.
        site_name (str) - Name of site
        site_type (str) - Name of specific site type being queried.
        bel (str) - BEL name containing site PIP.
        pin (str) - BEL pin name for specific edge.
        """
        site = self.site_name_to_site[site_name][site_type]
        return self.get_site_type(site.site_type_index).site_pip(
            site, bel, pin)


    def get_site_pin(self, site, site_pin_index):
        """ Get SitePinNames for specified site pin.
        site (Site) - Site tuple
        site_pin_index (int) - Index into SiteType.pins list.
        Site pin to tile relationships are estabilished through the site type
        in tile type data.
        If the site tuple indicates this is a primary site type, then the
        tile wire can be returned directly.
        If the site tuple indicates this is an alternate site type, then the
        tile wire is found by first mapping the site pin from the alternate
        site type to the primary site type.  At that point, the tile wire can
        be found.
        """
        tile = self.device_resources.tileList[site.tile_index]
        tile_type_index = tile.type
        tile_type = self.device_resources.tileTypeList[tile_type_index]
        site_type_in_tile_type = tile_type.siteTypes[site.
                                                     tile_type_site_type_index]
        if site.alt_index is None:
            # This site type is the primary site type, return the tile wire
            # directly.
            site_type = self.device_resources.siteTypeList[
                site_type_in_tile_type.primaryType]
            site_type_name = self.strs[site_type.name]
            pin_name = self.strs[site_type.pins[site_pin_index].name]
            wire_name = self.strs[site_type_in_tile_type.
                                  primaryPinsToTileWires[site_pin_index]]
        else:
            # This site type is an alternate site type.
            prim_site_type = self.device_resources.siteTypeList[
                site_type_in_tile_type.primaryType]
            site_type = self.device_resources.siteTypeList[
                prim_site_type.altSiteTypes[site.alt_index]]
            site_type_name = self.strs[site_type.name]
            pin_name = self.strs[site_type.pins[site_pin_index].name]

            # First translate the site_pin_index from the alternate site type
            # To the primary site type pin index.
            prim_site_pin_index = site_type_in_tile_type.altPinsToPrimaryPins[
                site.alt_index].pins[site_pin_index]
            prim_site_pin_name = self.strs[site_type.pins[prim_site_pin_index].name]
            self.altPinsToPrimPins[site_type_name][pin_name] = prim_site_pin_name
            # Then lookup the tile wire using the primary site pin index.
            wire_name = self.strs[site_type_in_tile_type.
                                  primaryPinsToTileWires[prim_site_pin_index]]

        return SitePinNames(
            tile_name=self.strs[tile.name],
            site_name=self.strs[tile.sites[site.site_index].name],
            site_type_name=site_type_name,
            pin_name=pin_name,
            wire_name=wire_name)
    

    def yield_cell_bel_mappings(self):
        """ yield cell bel mapping """
        for cell_bel_mapping in self.device_resources.cellBelMap:
            yield CellBel(self.strs, cell_bel_mapping)

    def get_library(self):
        """Build library for primitives and macros from device resources
        Didn't fully parse the property map.
        """
        netlist = self.device_resources.primLibs
 
        libraries = {}
        for cell_capnp in netlist.cellList:
            cell_decl = netlist.cellDecls[cell_capnp.index]
            prop_map = {}
            for prop in cell_decl.propMap.entries:
                key = self.strs[prop.key]
                if prop.which() == 'textValue':
                    value = self.strs[prop.textValue]
                elif prop.which() == 'intValue':
                    value = prop.intValue
                else:
                    assert prop.which() == 'boolValue'
                    value = prop.boolValue
                prop_map[key] = value
            cell = Cell(
                name=self.strs[cell_decl.name],
                capnp_index=cell_capnp.index,
                property_map=prop_map,
            )
            cell.view = self.strs[cell_decl.view]
            for inst in cell_capnp.insts:
            # struct CellInstance {
            #     name     @0 : StringIdx $stringRef();
            #     propMap  @1 : PropertyMap;
            #     view     @2 : StringIdx $stringRef();
            #     cell     @3 : CellIdx $cellRef();
            # }
                cell_instance_name = self.strs[netlist.instList[inst].name]
                cell_name = self.strs[netlist.cellDecls[netlist.instList[inst].cell].name]
                cell.cell_instances[cell_instance_name] = (cell_instance_name, cell_name)

            library = self.strs[cell_decl.lib]
            if library not in libraries:
                libraries[library] = Library(name=library)
            libraries[library].add_cell(cell)
        return libraries

    def get_macro_instance(self):
        """ Get macros from device resources
        macro_inst - build a map for macros and their instances.
        One macro consists of more than one primitives.
        """
        macro_lib = self.get_library()['macros']
        macro_inst = {}

        for cell_name, cell in sorted(
                macro_lib.cells.items(), key=lambda x: x[0]):
            macro_name = cell_name
            macro_inst[macro_name] = {}

            for inst_name, inst in sorted(
                    cell.cell_instances.items(), key=lambda x: x[0]):
                macro_inst[macro_name][inst_name] = inst[1]
                
        return macro_inst 

    def get_packages(self):
        """ Get the device package for debugging. """
        package_list = self.device_resources.packages

        for package in package_list:
            package_name = self.strs[package.name]


class db_to_physicalnetlist():
    def __init__(self, placedb, schema_dir, part_name):
        self.part = part_name
        self.schema_dir = schema_dir
        self.sitemap = {}
        # self.SLICE = {}
        self.DSP = []
        self.BRAM = []
        self.IO = []
        bram_y_num = placedb. num_sites_y / 5
        dsp_y_num = placedb. num_sites_y / 2.5


        slice_index_x = 0
        # initialize sitemap
        for i in range(placedb.num_sites_x):
            slice_flag = False
            # slice_index_y = 0
            for j in range(placedb.num_sites_y):
                # LUT/FF
                if placedb.site_type_map[i, j] == 1: 
                    slice_flag = True
                    for k in range(0, 16):
                        self.sitemap[i, j, k] = "SLICE_X" + str(slice_index_x) + "Y" + str(j)
                    # slice_index_y += 1
                # DSP
                elif placedb.site_type_map[i, j] == 2:
                    self.DSP.append((i, j))
                    idx = len(self.DSP) - 1
                    index_x = int(idx / dsp_y_num)
                    index_y = int(idx - index_x * dsp_y_num)
                    self.sitemap[i, j, 0] = "DSP48E2_X" + str(index_x) + "Y" + str(index_y)
                # BRAM
                elif placedb.site_type_map[i, j] == 3:
                    self.BRAM.append((i, j))
                    idx = len(self.BRAM) - 1
                    index_x = int(idx / bram_y_num)
                    index_y = int(idx - index_x * bram_y_num)
                    self.sitemap[i, j, 0] = "RAMB36_X" + str(index_x) + "Y" + str(index_y)
                # IO
                elif placedb.site_type_map[i, j] == 4:
                    self.IO.append((i, j))

            if slice_flag:
                slice_index_x += 1

            # if slice_index_x == 90:
            #     print(i)

        IOB_col = []
        BUFGCE_col = []
        for loc in self.IO:
            x, y = loc
            if x != 0 and x != placedb.num_sites_x - 1:
                if x not in IOB_col and x not in BUFGCE_col:
                    IOB_col.append(x) 
                    BUFGCE_col.append(x+1)


        self.Site_LUTs = {}
        self.shared_LUT = []

        # map from node name to cellplacement obj 
        self.node_placement = {}
        # map from port name to cellplacement obj 
        self.port_placement = {}

        # map from site name to SiteInst object
        self.site_instances = {}
        # map from node name to site name
        self.node_site_map = {}

        self.device_resource = DeviceResources(self.schema_dir, part_name)



        sitetypes_prefix = ['SLICEM', 'SLICEL', 'HPIOB', 'HRIO', 'BUFGCE', 'RAMB36', 'DSP48E2']
        sitetypes = []
        for site_type_name in self.device_resource.site_type_names:
            for prefix in sitetypes_prefix:
                if prefix in site_type_name:
                    sitetypes.append(site_type_name)

        # print(sitetypes)
        
        self.routing_graphs = {}
        self.site_in = {}
        self.site_out = {}
        self.dsp_bel_pins = {}
       

        for sitetype in sitetypes:
            site_index = self.device_resource.get_site_type_index(sitetype)
            sitetype_obj = self.device_resource.get_site_type(site_index)
            routing_graph, site_in, site_out = sitetype_obj.site_routing_graph()
            self.routing_graphs[sitetype] = routing_graph
            self.site_in[sitetype] = site_in
            self.site_out[sitetype] = site_out
            if sitetype == 'DSP48E2':
                for key in sitetype_obj.bel_pins:
                    bel_name, bel_pin_name = key
                    if bel_name not in self.dsp_bel_pins:
                        self.dsp_bel_pins[bel_name] = []
                    self.dsp_bel_pins[bel_name].append(bel_pin_name)


    def Map_bel(self, node_z, node_type):
        if node_type[:3] == "LUT":
            switcher = {
                0: "A5LUT",
                1: "A6LUT",
                2: "B5LUT",
                3: "B6LUT",
                4: "C5LUT",
                5: "C6LUT",
                6: "D5LUT",
                7: "D6LUT",
                8: "E5LUT",
                9: "E6LUT",
                10:"F5LUT",
                11:"F6LUT",
                12:"G5LUT",
                13:"G6LUT",
                14:"H5LUT",
                15:"H6LUT",
            }
            return switcher[node_z]
        elif node_type[:4] == "FDRE":
            switcher = {
                0: "AFF",
                1: "AFF2",
                2: "BFF",
                3: "BFF2",
                4: "CFF",
                5: "CFF2",
                6: "DFF",
                7: "DFF2",
                8: "EFF",
                9: "EFF2",
                10:"FFF",
                11:"FFF2",
                12:"GFF",
                13:"GFF2",
                14:"HFF",
                15:"HFF2",
            }
            return switcher[node_z]
        elif node_type[:4] == "BUFG":
            return "BUFCE"
        elif node_type[:4] == "OBUF":
            return "OUTBUF"
        elif node_type[:3] == "RAM":
            return "RAMB36E2"
        else:
            return "None"


    def prevent_pin_overlap(self, placedb, phys_netlist):
        """ For the cell bel pin mapping, especially for LUT packing

        The shared inputs of 5LUT and 6LUT must be connected to the same nets.
        In addition, when 5LUT and 6LUT are both used, A6 pin must be connected to VCC.
        The higher the pin number is, the less the delay.
        e.g: A5 has higher pin number than A4, etc

        My pin mapping scheme: I map the shared inputs first and start from higher pin number,
        and then move to the not shared ones.

        This is probably different from how vivado copes with pin mapping!

        """

        bel_pins = ['A5', 'A4', 'A3', 'A2', 'A1']

        for site in self.Site_LUTs:
            LUT_map = {
                'A': [],
                'B': [],
                'C': [],
                'D': [],
                'E': [],
                'F': [],
                'G': [],
                'H': [],
            }
            for lut_placement in self.Site_LUTs[site]:
                if lut_placement.bel_name[:1] == 'A':
                    LUT_map['A'].append(lut_placement)
                elif lut_placement.bel_name[:1] == 'B':
                    LUT_map['B'].append(lut_placement)
                elif lut_placement.bel_name[:1] == 'C':
                    LUT_map['C'].append(lut_placement)
                elif lut_placement.bel_name[:1] == 'D':
                    LUT_map['D'].append(lut_placement)
                elif lut_placement.bel_name[:1] == 'E':
                    LUT_map['E'].append(lut_placement)
                elif lut_placement.bel_name[:1] == 'F':
                    LUT_map['F'].append(lut_placement)
                elif lut_placement.bel_name[:1] == 'G':
                    LUT_map['G'].append(lut_placement)
                elif lut_placement.bel_name[:1] == 'H':
                    LUT_map['H'].append(lut_placement)
                else:
                    continue
            
            sharedluts_insite = []

            for key in LUT_map:
                if len(LUT_map[key]) == 2:
                    self.shared_LUT.append((LUT_map[key][0], LUT_map[key][1]))
                    sharedluts_insite.append((LUT_map[key][0], LUT_map[key][1]))
                
                #single 5LUT detection
                elif len(LUT_map[key]) == 1 and LUT_map[key][0].bel_name.endswith('5LUT'):
                    LUT_map[key][0].bel_name = LUT_map[key][0].bel_name[:1] + '6LUT'
                    
                    # build new pinmap
                    new_pinmap = []
                    for pin in LUT_map[key][0].pins:
                        if pin[0][:1] == 'O':
                            new_pin = (pin[0], 'O6')
                        elif pin[0][:1] == 'I':
                            new_pin = (pin[0], pin[2])
                        new_pinmap.append(new_pin)
                    
                    LUT_map[key][0].pins.clear()

                    for new_pin in new_pinmap:
                        LUT_map[key][0].add_pins(new_pin[0], new_pin[1])
       
                else:
                    continue
            
            for lut_pair in sharedluts_insite:
                lut_name_0 = lut_pair[0].cell_name
                node_id_0 = placedb.node_name2id_map[lut_name_0]

                lut_name_1 = lut_pair[1].cell_name
                node_id_1 = placedb.node_name2id_map[lut_name_1]

                pin2net_0 = {}

                for pin_id in placedb.node2pin_map[node_id_0]:
                    pin2net_0[placedb.pin_names[pin_id]] = placedb.pin2net_map[pin_id]
                
                pin2net_1 = {}
                for pin_id in placedb.node2pin_map[node_id_1]:
                    pin2net_1[placedb.pin_names[pin_id]] = placedb.pin2net_map[pin_id] 
                
                error_cnt = 0
                for pin_0 in lut_pair[0].pins:
                    cellpin_0 = pin_0[0]
                    belpin_0 = pin_0[2]
                    if belpin_0 == 'A6':
                        error_cnt += 1
                        break

                    for pin_1 in lut_pair[1].pins:
                        cellpin_1 = pin_1[0]
                        belpin_1 = pin_1[2]
                        if belpin_1 == 'A6':
                            error_cnt += 1
                            break

                        if belpin_0 == belpin_1:
                            if cellpin_0 in pin2net_0 and cellpin_1 in pin2net_1:
                                if pin2net_0[cellpin_0] == pin2net_1[cellpin_1]:
                                    pass
                                else:
                                    error_cnt += 1
                                    break


                # fix the wrong mapping
                
                if error_cnt != 0:

                    shared_pins_0 = []
                    shared_pins_1 = []
                    un_shared_pins_0 = []
                    un_shared_pins_1 = []
                    input_pins_0 = []
                    output_pin_0 = None
                    input_pins_1 = []
                    output_pin_1  = None

                    for pin_0 in lut_pair[0].pins:
                        cellpin_0 = pin_0[0]
                        if cellpin_0[:1] == 'I':
                            input_pins_0.append(cellpin_0)
                        else:
                            output_pin_0 = pin_0
                            
                    for pin_1 in lut_pair[1].pins:
                        cellpin_1 = pin_1[0]
                        if cellpin_1[:1] == 'I':
                            input_pins_1.append(cellpin_1)
                        else:
                            output_pin_1 = pin_1

                    lut_pair[0].pins.clear()
                    lut_pair[1].pins.clear()

                    
                    for cellpin_0 in input_pins_0:
                        if cellpin_0 not in shared_pins_0:
                            for cellpin_1 in input_pins_1:
                                if cellpin_1 not in shared_pins_1:
                                    if cellpin_0 in pin2net_0 and cellpin_1 in pin2net_1:
                                        if pin2net_0[cellpin_0] == pin2net_1[cellpin_1]:
                                            net_name = placedb.net_names[pin2net_0[cellpin_0]]
                                            shared_pins_0.append(cellpin_0)
                                            shared_pins_1.append(cellpin_1)  
                                            break                             


                    for cellpin_0 in input_pins_0:
                        if cellpin_0 not in shared_pins_0:
                            for cellpin_1 in input_pins_1:
                                if cellpin_1 not in shared_pins_1:
                                    if cellpin_0 in pin2net_0 and cellpin_1 not in pin2net_1:
                                        shared_pins_0.append(cellpin_0)
                                        shared_pins_1.append(cellpin_1)
                    
                                    elif cellpin_0 not in pin2net_0 and cellpin_1 in pin2net_1:
                                        shared_pins_0.append(cellpin_0)
                                        shared_pins_1.append(cellpin_1)


                    for cellpin_0 in input_pins_0:
                        if cellpin_0 not in shared_pins_0:
                            for cellpin_1 in input_pins_1:
                                if cellpin_1 not in shared_pins_1:
                                    if cellpin_0 not in pin2net_0 and cellpin_1 not in pin2net_1:
                                        shared_pins_0.append(cellpin_0)
                                        shared_pins_1.append(cellpin_1)


                    # self.pins.append((cellpin, self.bel_name, belpin))
                    for idx, pin in enumerate(shared_pins_0):
                        lut_pair[0].add_pins(shared_pins_0[idx], bel_pins[idx])
                        lut_pair[1].add_pins(shared_pins_1[idx], bel_pins[idx])


                    for pin_0 in input_pins_0:
                        if pin_0 not in shared_pins_0:
                            un_shared_pins_0.append(pin_0)
                    for pin_1 in input_pins_1:
                        if pin_1 not in shared_pins_1:
                            un_shared_pins_1.append(pin_1)

                    for idx, un_shared_pin in enumerate(un_shared_pins_0):
                        lut_pair[0].add_pins(un_shared_pin, bel_pins[idx + len(shared_pins_0)])
                    
                    for idx, un_shared_pin in enumerate(un_shared_pins_1):
                        lut_pair[1].add_pins(un_shared_pin, bel_pins[idx + len(un_shared_pins_0) + len(shared_pins_1)])


                    lut_pair[0].add_pins(output_pin_0[0], output_pin_0[2])
                    lut_pair[1].add_pins(output_pin_1[0], output_pin_1[2])
                

    def stitch_routing(self, placedb, phys_netlist):
        """
        Do intra-site routing through site_routing graph.
        call function site_router(), this is the clean way to do intra-site routing for each site.
        """

        nets = {}
        net_source = {}
        io_nets = {}
        vcc_nets = []
        gnd_nets = []
        constant_nets = {
            0 : 'GLOBAL_LOGIC0',
            1 : 'GLOBAL_LOGIC1'
        }

        ram_pin_pair = {
            'ADDRENAL' : 'ADDRENAU',
            'ADDRENBL' : 'ADDRENBU',
            'CLKARDCLKL' : 'CLKARDCLKU',
            'CLKBWRCLKL' : 'CLKBWRCLKU',  
            'ECCPIPECEL': 'ECCPIPECEU',
            'ENARDENL' : 'ENARDENU',
            'ENBWRENL' : 'ENBWRENU',
            'REGCEAREGCEL' : 'REGCEAREGCEU',
            'REGCEBL' : 'REGCEBU',
            'REGCLKARDRCLKL' : 'REGCLKARDRCLKU',
            'REGCLKBL' : 'REGCLKBU',
            'RSTRAMARSTRAML' : 'RSTRAMARSTRAMU',
            'RSTRAMBL' : 'RSTRAMBU',
            'RSTREGARSTREGL' : 'RSTREGARSTREGU',
            'RSTREGBL' : 'RSTREGBU',
            'SLEEPL' : 'SLEEPU'
        } 

        
        # sort nets 
        for net_id in range(len(placedb.net2pin_map)):
            net_name = placedb.net_names[net_id]
            sources = []
            stubs = []

            for pin_id in placedb.net2pin_map[net_id]:
                pin_name = placedb.pin_names[pin_id]
                node_name = placedb.node_names[placedb.pin2node_map[pin_id]]
                node_id = placedb.node_name2id_map[node_name]
                node_type = placedb.node_types[node_id]

                # ignore the pseudo VCC, GND nodes
                if node_type == 'LUT0': 
                    if node_name == 'VCC':
                        vcc_nets.append(net_name)
                    else:
                        gnd_nets.append(net_name)
                           
                    continue

                site_name = self.node_site_map[node_name]


                # net_roots
                site_obj = self.site_instances[site_name]
                cells = site_obj.cells

                # This pin is somehow not to be mapped 
                if pin_name == 'RSTREGB':
                    continue

                if node_type[:3] == 'DSP' and pin_name[0] == 'D':
                    pin_name = pin_name.replace('D', 'DIN')

                # primary cells
                if len(cells[node_name]) == 1:
                    cell_placement = cells[node_name][0]                 
                    bel_name = cell_placement.bel_name  
        
                    for pin in cell_placement.pins:
                        if pin[0] == pin_name:
                            bel_pin = pin[2]
                            belpin_tup = 'bel_pin', bel_name, bel_pin
                            site_obj.add_belpins(net_name, belpin_tup)
                            if bel_pin in ram_pin_pair:
                                belup_tup = 'bel_pin', bel_name, ram_pin_pair[bel_pin]
                                site_obj.add_belpins(net_name, belup_tup)

                            break

                else: 
                    for cell in cells[node_name]:
                        cell_placement = cell
                        bel_name = cell_placement.bel_name

                        belpin_tup = None
                        for pin in cell_placement.pins:
                            if pin[0] == pin_name:
                                bel_pin = pin[2]
                                belpin_tup = 'bel_pin', bel_name, bel_pin
                                break 
                            elif bel_name.endswith('LUT') and pin_name.startswith('O'):
                                belpin_tup = 'bel_pin', bel_name, pin_name

                        if bel_name == 'INBUF':
                            ctrl_tup = 'bel_pin', 'IBUFCTRL', 'I'
                            out_net = node_name + '/OUT'
                            site_obj.add_belpins(out_net, ctrl_tup)
                            site_obj.add_belpins(out_net, belpin_tup)

                        elif bel_name == 'IBUFCTRL':
                            o_net = node_name + '/O'
                            io_nets[net_name] = o_net
                            site_obj.add_belpins(o_net, belpin_tup)


                        elif belpin_tup != None:                                               
                            site_obj.add_belpins(net_name, belpin_tup)


        # site router
        for site_name, site_obj in self.site_instances.items():    
            site_type = phys_netlist.siteInsts[site_name]  
            site_nets, site_net_source = site_obj.site_router(self.routing_graphs[site_type], self.site_in[site_type], self.site_out[site_type])

            for net_name, root_list in site_nets.items():      
                if net_name in io_nets:
                    net_name = io_nets[net_name]
                if net_name not in nets:
                    nets[net_name] = root_list
                else:
                    for root in root_list:
                        nets[net_name].append(root)

            for net_name, source in site_net_source.items():
                if net_name not in net_source:
                    net_source[net_name] = source

        
        vcc_stubs = []
        gnd_stubs = []
        # Build physical nets for normal nets
        # Extend the stub lists for vcc and gnd nets
        for net_name, root_list in nets.items():
            sources = []
            stubs = []
            
            for root in root_list:
                if net_name in net_source and root.bel_name == net_source[net_name][1]:
                    sources.append(root)
                else:
                    stubs.append(root)

            if net_name == constant_nets[0] or net_name in gnd_nets:
                gnd_stubs.extend(stubs)
            
            elif net_name == constant_nets[1] or net_name in vcc_nets:
                vcc_stubs.extend(stubs)

            else:
                phys_netlist.add_physical_net(net_name=net_name,
                    sources=sources,
                    stubs=stubs,
                    stubNodes=[],
                    net_type=PhysicalNetType.Signal)

        # Finally build physical nets for vcc and gnd
        # For gnd and vcc nets, they don't have sources
        phys_netlist.add_physical_net(net_name=constant_nets[0],
                    sources=[],
                    stubs=gnd_stubs,
                    stubNodes=[],
                    net_type=PhysicalNetType.Gnd)

        phys_netlist.add_physical_net(net_name=constant_nets[1],
                    sources=[],
                    stubs=vcc_stubs,
                    stubNodes=[],
                    net_type=PhysicalNetType.Vcc)
        
        

    def build_physicalnetlist(self, placedb, out_file):
        phys_netlist = PhysicalNetlist(self.part)

        # cell_prop_map = self.logical_netlist.cell_prop_map
        
        mappings = self.device_resource.yield_cell_bel_mappings()
        site_type_map = self.device_resource.site_type_map
        alt_site_type_map = self.device_resource.alt_site_type_map
        site_type_bels =  self.device_resource.site_type_bels
        macro_inst = self.device_resource.get_macro_instance()

        pinmap = {}
        parameter_pinmap = {}
        for mapping in mappings:
            cell = mapping.cell
            pinmap[cell] = mapping.common_pins
            parameter_pinmap[cell] = mapping.parameter_pins

        with open(out_file, 'r') as fin:
            for line in fin:
                node_name, x, y, z = line.split()
                x = int(x)
                y = int(y)
                z = int(z)
                node_id = placedb.node_name2id_map[node_name]
                node_type = placedb.node_types[node_id]

                # ignore the pseudo VCC, GND nodes
                if node_type == 'LUT0':
                    continue

                self.node_placement[node_name] = [] 

                if node_type in macro_inst:
                    LUT6_2_flag = False
                    for inst in macro_inst[node_type]:
                        cell_type = macro_inst[node_type][inst]
                        cell_name = node_name + "/" + inst
                        site_name = self.sitemap[x, y, z]
                            
                        if site_type_map[site_name][:5] == 'SLICE' and LUT6_2_flag == False:
                            bel_name = self.Map_bel(z-1, node_type)
                            LUT6_2_flag = True
                        elif LUT6_2_flag == True:
                            bel_name = self.Map_bel(z, node_type)
                        else:
                            bel_name = cell_type

                        self.node_site_map[node_name] = site_name

                        # build siteinst obj
                        if site_name not in self.site_instances:
                            site_instance  = SiteInst(site_name)
                            self.site_instances[site_name] = site_instance


                        # For site instances
                        if site_name not in phys_netlist.siteInsts:
                            site_type = site_type_map[site_name]
                            phys_netlist.add_site_instance(site_name, site_type) 

                            self.site_instances[site_name] = SiteInst(site_name)

                        else:
                            site_type = phys_netlist.siteInsts[site_name]

                        # add cell instance
                        cellplacement = Cellplacement(cell_name, cell_type, site_name, bel_name)
                        self.node_placement[node_name].append(cellplacement)

                        # add pins for cell instance
                        for key, value in pinmap[cell_type][site_type, bel_name].items():
                            belpin = key
                            cellpin = value
                            if cellpin == "GND": 
                                continue
                            elif node_type == 'DSP48E2':
                                if belpin in self.dsp_bel_pins[bel_name]:
                                    cellplacement.add_pins(cellpin, belpin)
                                else:
                                    break
                            else:
                                cellplacement.add_pins(cellpin, belpin)
                        phys_netlist.add_cellplacement(cellplacement)

                        self.site_instances[site_name].add_cells(node_name, cellplacement)                            

                # primary insts
                else: 
                    cell_type = node_type
                    cell_name = node_name
                    site_name = self.sitemap[x, y, z]
                    bel_name = self.Map_bel(z, node_type)
                    self.node_site_map[node_name] = site_name

                    if site_name not in self.site_instances:
                        site_instance  = SiteInst(site_name)
                        self.site_instances[site_name] = site_instance


                    # For site instances
                    if site_name not in phys_netlist.siteInsts:
                        if cell_type == "RAMB36E2":
                            site_type = alt_site_type_map[site_name]
                        else:
                            site_type = site_type_map[site_name]
                        phys_netlist.add_site_instance(site_name, site_type)
                    else:
                        site_type = phys_netlist.siteInsts[site_name]


                    # add cell instance
                    cellplacement = Cellplacement(cell_name, cell_type, site_name, bel_name)
                    self.node_placement[node_name].append(cellplacement)
                    self.site_instances[site_name].add_cells(node_name, cellplacement)

                    # add pins for cell instance
                    for key, value in pinmap[cell_type][site_type, bel_name].items():
                        belpin = key
                        cellpin = value
                        if cellpin == "GND": 
                            continue
                        else:
                            cellplacement.add_pins(cellpin, belpin)


                    if cell_type == 'RAMB36E2':
                        para_belcell = {}
                        para_map = {}
                        para_map['DOA_REG'] = '1'
                        para_map['WRITE_WIDTH_A'] = '1'
                        para_map['WRITE_WIDTH_B'] = '72'
                        para_map['DOB_REG'] = '1'


                        for prop_key, prop_value in para_map.items():           
                            for key, value in parameter_pinmap[cell_type][site_type, bel_name, prop_key, prop_value].items():
                                belpin = key
                                cellpin = value
                                
                                #   hardcode this need to find a clean way 
                                if belpin == 'DINBDIN1':
                                    cellpin = 'DINBDIN[1]'

                                if cellpin == "GND" or cellpin == "VCC": 
                                    continue
                                elif belpin not in para_belcell:
                                    para_belcell[belpin] = cellpin
                                    cellplacement.add_pins(cellpin, belpin)
                                    

                    phys_netlist.add_cellplacement(cellplacement)

                    if site_name[:5] == 'SLICE':
                        if site_name not in self.Site_LUTs:
                            in_site_luts = []
                            if cell_type[:3] == 'LUT':
                                in_site_luts.append(cellplacement)
                            self.Site_LUTs[site_name] = in_site_luts
                        else:
                            if cell_type[:3] == 'LUT':
                                self.Site_LUTs[site_name].append(cellplacement)
                                

        self.prevent_pin_overlap(placedb, phys_netlist)

        self.stitch_routing(placedb, phys_netlist)

        return phys_netlist

            
class tcl_generator():
    """ generate a tcl script for the golden reference IF file

    file_name - "place_cells.tcl"
    place cells one by one by using vivado tcl command place_cell;
    place each cell to its corresponding site.

    """
    def __init__(self):
        self.file_name = 'place_cells.tcl'

    def write_tcl(self, phys_netlist):
        """ write out the tcl script """
        with open(self.file_name, 'w') as tcl_file:
            for placement in phys_netlist.placements:
                if placement.cell_name.endswith('/LUT5'):
                    continue
                elif placement.cell_name.endswith('/LUT6'):
                    placement.cell_name = placement.cell_name[:-5]
                line = 'place_cell ' + placement.cell_name + ' ' + placement.site_name + '/' + placement.bel_name
                tcl_file.write(line + os.linesep)



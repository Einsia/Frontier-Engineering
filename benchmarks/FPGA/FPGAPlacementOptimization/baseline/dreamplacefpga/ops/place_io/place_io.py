##
# @file   place_io.py
# @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Mar 2021
#

from torch.autograd import Function

import dreamplacefpga.ops.place_io.place_io_cpp as place_io_cpp
import pdb

class PlaceIOFunction(Function):
    @staticmethod
    def read(params):
        """
        @brief read design and store in placement database
        """
        args = params.aux_input
        if "aux_input" in params.__dict__ and params.aux_input:
            return place_io_cpp.forward(args)

    @staticmethod
    def pydb(raw_db): 
        """
        @brief convert to python database 
        @param raw_db original placement database 
        """
        return place_io_cpp.pydb(raw_db)

    @staticmethod 
    def write(raw_db, filename, node_x, node_y, node_z):
        """
        @brief write solution in specific format 
        @param raw_db original placement database 
        @param filename output file 
        @param sol_file_format solution file format, DEF|DEFSIMPLE|BOOKSHELF|BOOKSHELFALL - Always *.pl for FPGA
        @param node_x x coordinates of cells, only need movable cells; if none, use original position 
        @param node_y y coordinates of cells, only need movable cells; if none, use original position
        """
        return place_io_cpp.write(raw_db, filename, node_x, node_y, node_z)

    @staticmethod 
    def apply(raw_db, node_x, node_y, node_z):
        """
        @brief apply solution 
        @param raw_db original placement database 
        @param node_x x coordinates of cells, only need movable cells
        @param node_y y coordinates of cells, only need movable cells
        @param node_z z coordinates of cells, only need movable cells
        """
        return place_io_cpp.apply(raw_db, node_x, node_y, node_z)


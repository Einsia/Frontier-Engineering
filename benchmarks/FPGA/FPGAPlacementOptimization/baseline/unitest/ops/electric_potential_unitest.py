##
# @file   electric_potential_unitest.py
# @author Yibo Lin (DREAMPlace) Rachel Selina (DREAMPlaceFPGA)
# @date   Mar 2024
#

import time
import numpy as np
import unittest
import logging
import random

import torch
from torch.autograd import Function, Variable
import os
import sys
import gzip

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
from dreamplacefpga.ops.dct import dct
from dreamplacefpga.ops.dct import discrete_spectral_transform
from dreamplacefpga.ops.electric_potential import electric_potential
sys.path.pop()

if sys.version_info[0] < 3:
    import cPickle as pickle
else:
    import _pickle as pickle
import inspect
import pdb
from scipy import fftpack

import matplotlib
matplotlib.use('Agg')
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt

class PlaceDB (object):
    def __init__(self):
        self.num_nodes = 0
        self.num_terminals = 0
        self.num_movable_nodes = 0
        self.num_filler_nodes = 0
        self.xWirelenWt = 1.0
        self.yWirelenWt = 1.0
        self.filler_start_map = []
        self.overflowInstDensityStretchRatio = []

class ElectricPotentialOpTest(unittest.TestCase):
    def test_densityOverflowRandom(self):
        dtype = np.float64

        stretchRatio = np.sqrt(2.0)
        ## Create a database
        placedb = PlaceDB()
        placedb.num_nodes = 84
        placedb.num_terminals = 1
        placedb.num_movable_nodes = placedb.num_nodes - placedb.num_terminals
        placedb.filler_start_map = np.array([0, 0, 0, 0, 0, 0], dtype=np.int32)
        placedb.overflowInstDensityStretchRatio = np.array([stretchRatio, stretchRatio, 1.0, 1.0, 0], dtype=dtype)

        xl = 0.0
        yl = 0.0
        xh = 100.0
        yh = 360.0

        xx = np.array([random.randint(int(xl),int(xh)) for i in range(placedb.num_nodes)]).astype(dtype)
        yy = np.array([random.randint(int(yl),int(yh)) for i in range(placedb.num_nodes)]).astype(dtype)
        node2fence_region_map = np.array([0 for i in range(placedb.num_nodes)]).astype(np.int32)
        #Keep last entry as fixed
        xx[-1] = 0
        yy[-1] = 0
        node2fence_region_map[-1] = 4

        node_size_x = np.array([
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.5, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.5, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 1.0
        ]).astype(dtype)
        node_size_y = np.array([
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.5, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.5, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
            0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 1.0
        ]).astype(dtype)

        region_id = 0

        num_bins_x = 256 
        num_bins_y = 256
        bin_size_x = (xh - xl) / num_bins_x
        bin_size_y = (yh - yl) / num_bins_y
        initial_density_map = np.zeros([num_bins_x, num_bins_y], dtype=dtype)
        fixed_cols = int(num_bins_x/(xh-xl)) + 1 
        for val in range(fixed_cols):
            initial_density_map[val] = bin_size_x*bin_size_y
            initial_density_map[:,val] = bin_size_x*bin_size_y

        print("target_area = ", bin_size_x * bin_size_y)

        if dtype == np.float64:
            dtype = torch.float64
        elif dtype == np.float32:
            dtype = torch.float32

        movable_size_x = node_size_x[:placedb.num_movable_nodes]
        _, sorted_node_map = torch.sort(
            torch.tensor(movable_size_x, requires_grad=False, dtype=dtype))
        sorted_node_map = sorted_node_map.to(torch.int32).contiguous()

        # test cpu
        custom = electric_potential.ElectricPotential(
            torch.tensor(node_size_x, requires_grad=False, dtype=dtype),
            torch.tensor(node_size_y, requires_grad=False, dtype=dtype),
            xl=xl,
            yl=yl,
            xh=xh,
            yh=yh,
            bin_size_x=bin_size_x,
            bin_size_y=bin_size_y,
            num_movable_nodes=placedb.num_movable_nodes,
            num_terminals=placedb.num_terminals,
            num_filler_nodes=0,
            deterministic_flag=True,
            sorted_node_map=sorted_node_map,
            region_id=region_id,
            fence_regions=torch.tensor(initial_density_map, requires_grad=False, dtype=dtype),
            node2fence_region_map=torch.tensor(node2fence_region_map, requires_grad=False, dtype=torch.int32),
            placedb=placedb,
            stretchRatio=stretchRatio)

        pos = Variable(torch.from_numpy(np.concatenate([xx, yy])),
                       requires_grad=True)
        result = custom.forward(pos)
        print("custom_result = ", result)
        print(result.type())
        result.backward()
        grad = pos.grad.clone()
        print("custom_grad = ", grad)

        # test cuda
        if torch.cuda.device_count():
            custom_cuda = electric_potential.ElectricPotential(
                torch.tensor(node_size_x, requires_grad=False,
                             dtype=dtype).cuda(),
                torch.tensor(node_size_y, requires_grad=False,
                             dtype=dtype).cuda(),
                xl=xl,
                yl=yl,
                xh=xh,
                yh=yh,
                bin_size_x=bin_size_x,
                bin_size_y=bin_size_y,
                num_movable_nodes=placedb.num_movable_nodes,
                num_terminals=placedb.num_terminals,
                num_filler_nodes=0,
                deterministic_flag=False,
                sorted_node_map=sorted_node_map.cuda(),
                region_id=region_id,
                fence_regions=torch.tensor(initial_density_map, requires_grad=False,
                                            dtype=dtype).cuda(),
                node2fence_region_map=torch.tensor(node2fence_region_map, requires_grad=False,
                                                    dtype=torch.int32).cuda(),
                placedb=placedb,
                stretchRatio=stretchRatio)

            pos = Variable(torch.from_numpy(np.concatenate([xx, yy])).cuda(),
                           requires_grad=True)
            #pos.grad.zero_()
            result_cuda = custom_cuda.forward(pos)
            print("custom_result_cuda = ", result_cuda.data.cpu())
            print(result_cuda.type())
            result_cuda.backward()
            grad_cuda = pos.grad.clone()
            print("custom_grad_cuda = ", grad_cuda.data.cpu())

            np.testing.assert_allclose(result.detach().numpy(),
                                       result_cuda.data.cpu().detach().numpy())
            np.testing.assert_allclose(grad.detach().numpy(),
                                       grad_cuda.data.cpu().detach().numpy())


def plot(plot_count, density_map, padding, name):
    """
    density map contour and heat map
    """
    density_map = density_map[padding:density_map.shape[0] - padding,
                              padding:density_map.shape[1] - padding]
    print("max density = %g" % (np.amax(density_map)))
    print("mean density = %g" % (np.mean(density_map)))

    fig = plt.figure()
    ax = fig.gca(projection='3d')

    x = np.arange(density_map.shape[0])
    y = np.arange(density_map.shape[1])

    x, y = np.meshgrid(x, y)
    # looks like x and y should be swapped
    ax.plot_surface(y, x, density_map, alpha=0.8)

    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('density')

    # plt.tight_layout()
    plt.savefig(name + ".3d.png")
    plt.close()

    # plt.clf()

    #fig, ax = plt.subplots()

    # ax.pcolor(density_map)

    # Loop over data dimensions and create text annotations.
    # for i in range(density_map.shape[0]):
    # for j in range(density_map.shape[1]):
    # text = ax.text(j, i, density_map[i, j],
    # ha="center", va="center", color="w")
    # fig.tight_layout()
    #plt.savefig(name+".2d.%d.png" % (plot_count))
    # plt.close()


def eval_runtime(design):
    ## e.g., adaptec1_density.pklz
    #with gzip.open(design, "rb") as f:
    #    node_size_x, node_size_y, bin_center_x, bin_center_y, xl, yl, xh, yh, bin_size_x, bin_size_y, num_movable_nodes, num_terminals, num_filler_nodes = pickle.load(
    #        f)

    dtype = torch.float64
    num_threads = 10
    torch.set_num_threads(num_threads)
    print("num_threads = %d" % (torch.get_num_threads()))
    movable_size_x = node_size_x[:placedb.num_movable_nodes]
    _, sorted_node_map = torch.sort(
        torch.tensor(movable_size_x, requires_grad=False, dtype=dtype).cuda())
    sorted_node_map = sorted_node_map.to(torch.int32).contiguous()
    node2fence_region_map = node2fence_region_map.to(torch.int32).contiguous()
    initial_density_map = initial_density_map.to(dtype).contiguous()

    pos_var = Variable(torch.empty(len(node_size_x) * 2,
                                   dtype=dtype).uniform_(xl, xh),
                       requires_grad=True)
    custom = electric_potential.ElectricPotential(
        torch.tensor(node_size_x, requires_grad=False, dtype=dtype).cpu(),
        torch.tensor(node_size_y, requires_grad=False, dtype=dtype).cpu(),
        xl=xl,
        yl=yl,
        xh=xh,
        yh=yh,
        bin_size_x=bin_size_x,
        bin_size_y=bin_size_y,
        num_movable_nodes=placedb.num_movable_nodes,
        num_terminals=placedb.num_terminals,
        num_filler_nodes=num_filler_nodes,
        deterministic_flag=True,
        sorted_node_map=sorted_node_map.cpu(),
        region_id=region_id,
        fence_regions=initial_density_map.cpu(),
        node2fence_region_map=node2fence_region_map.cpu(),
        placedb=placedb,
        stretchRatio=stretchRatio)

    custom_cuda = electric_potential.ElectricPotential(
        torch.tensor(node_size_x, requires_grad=False, dtype=dtype).cuda(),
        torch.tensor(node_size_y, requires_grad=False, dtype=dtype).cuda(),
        xl=xl,
        yl=yl,
        xh=xh,
        yh=yh,
        bin_size_x=bin_size_x,
        bin_size_y=bin_size_y,
        num_movable_nodes=placedb.num_movable_nodes,
        num_terminals=placedb.num_terminals,
        num_filler_nodes=num_filler_nodes,
        deterministic_flag=False,
        sorted_node_map=sorted_node_map,
        region_id=region_id,
        fence_regions=initial_density_map,
        node2fence_region_map=node2fence_region_map,
        placedb=placedb,
        stretchRatio=stretchRatio)

    torch.cuda.synchronize()
    iters = 100
    tbackward = 0
    tt = time.time()
    for i in range(iters):
        result = custom.forward(pos_var)
        ttb = time.time()
        result.backward()
        tbackward += time.time() - ttb
    torch.cuda.synchronize()
    print("custom takes %.3f ms, backward %.3f ms" %
          ((time.time() - tt) / iters * 1000, (tbackward / iters * 1000)))

    pos_var = pos_var.cuda()
    tt = time.time()
    for i in range(iters):
        result = custom_cuda.forward(pos_var)
        result.backward()
    torch.cuda.synchronize()
    print("custom_cuda takes %.3f ms" % ((time.time() - tt) / iters * 1000))


if __name__ == '__main__':
    logging.root.name = 'DREAMPlaceFPGA'
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(levelname)-7s] %(name)s - %(message)s',
                        stream=sys.stdout)
    if len(sys.argv) < 2:
        unittest.main()
    else:
        design = sys.argv[1]
        eval_runtime(design)

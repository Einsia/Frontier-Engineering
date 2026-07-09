##
# @file   hpwl_unitest.py
# @author Yibo Lin (DREAMPlace) Rachel Selina (DREAMPlaceFPGA)
# @date   Mar 2024
#

import os 
import sys
import numpy as np
import unittest

import torch
from torch.autograd import Function, Variable
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dreamplacefpga.ops.hpwl import hpwl
sys.path.pop()
import pdb 

"""
return hpwl of a net 
"""
def net_hpwl(x, y, net2pin_map, net_weights, net_id): 
    pins = net2pin_map[net_id]
    hpwl_x = np.amax(x[pins]) - np.amin(x[pins])
    hpwl_y = np.amax(y[pins]) - np.amin(y[pins])

    return (hpwl_x+hpwl_y)*net_weights[net_id]

"""
return hpwl of all nets
"""
def all_hpwl(x, y, net2pin_map, net_weights):
    wl = 0
    for net_id in range(len(net2pin_map)):
        wl += net_hpwl(x, y, net2pin_map, net_weights, net_id)
    return wl 

class HPWLOpTest(unittest.TestCase):
    def test_hpwlRandom(self):
        pin_pos = np.array([[0.0, 0.0], [1.0, 2.0], [1.5, 0.2], [0.5, 3.1], [0.6, 1.1]], dtype=np.float32)
        net2pin_map = [[0, 4], [1, 2, 3]]
        num_nets = 2
        # net weights 
        net_weights = np.array([1, 2], dtype=np.float32)
        print("net_weights = ", net_weights)

        pin_x = pin_pos[:, 0]
        pin_y = pin_pos[:, 1]

        # construct flat_net2pin_map and flat_net2pin_start_map
        # flat netpin map, length of #pins
        flat_net2pin_map = np.array([0, 4, 1, 2, 3], dtype=np.int32)
        # starting index in netpin map for each net, length of #nets+1, the last entry is #pins  
        flat_net2pin_start_map = np.array([0, 2, 5], dtype=np.int32)
        count = 0
        #for i in range(len(net2pin_map)):
        #    flat_net2pin_map[count:count+len(net2pin_map[i])] = net2pin_map[i]
        #    flat_net2pin_start_map[i] = count 
        #    count += len(net2pin_map[i])
        #flat_net2pin_start_map[len(net2pin_map)] = len(pin_pos)
        
        print("flat_net2pin_map = ", flat_net2pin_map)
        print("flat_net2pin_start_map = ", flat_net2pin_start_map)

        # construct pin2net_map 
        pin2net_map = np.zeros(len(pin_pos), dtype=np.int32)
        for i in range(num_nets):
            for pin_id in net2pin_map[i]:
                pin2net_map[pin_id] = i 
        print("pin2net_map = ", pin2net_map)

        # net degrees 
        net_degrees = np.array([2, 3], dtype=np.int32)
        net_mask = (net_degrees <= np.amax(net_degrees)).astype(np.uint8)
        print("net_mask = ", net_mask)

        golden_value = all_hpwl(pin_x, pin_y, net2pin_map, net_weights)
        print("golden_value = ", golden_value)

        # test cpu 
        print(np.transpose(pin_pos))
        pin_pos_var = Variable(torch.from_numpy(pin_pos))
        print(pin_pos_var)
        # clone is very important, because the custom op cannot deep copy the data 
        pin_pos_var = torch.t(pin_pos_var).contiguous()
        custom = hpwl.HPWL(
                xWeight=1.0,
                yWeight=1.0,
                flat_netpin=torch.from_numpy(flat_net2pin_map), 
                netpin_start=torch.from_numpy(flat_net2pin_start_map),
                pin2net_map=torch.from_numpy(pin2net_map), 
                net_weights=torch.from_numpy(net_weights), 
                net_mask=torch.from_numpy(net_mask), 
                num_threads=1,
                algorithm='net-by-net'
                )
        hpwl_value = custom.forward(pin_pos_var)
        print("hpwl_value = ", hpwl_value.data.numpy())
        np.testing.assert_allclose(hpwl_value.data.numpy(), golden_value)

        # test gpu 
        if torch.cuda.device_count(): 
            custom_cuda = hpwl.HPWL(
                    xWeight=1.0,
                    yWeight=1.0,
                    flat_netpin=torch.from_numpy(flat_net2pin_map).cuda(), 
                    netpin_start=torch.from_numpy(flat_net2pin_start_map).cuda(),
                    pin2net_map=torch.from_numpy(pin2net_map).cuda(), 
                    net_weights=torch.from_numpy(net_weights).cuda(), 
                    net_mask=torch.from_numpy(net_mask).cuda(), 
                    num_threads=1,
                    algorithm='net-by-net'
                    )
            hpwl_value = custom_cuda.forward(pin_pos_var.cuda())
            print("hpwl_value cuda = ", hpwl_value.data.cpu().numpy())
            np.testing.assert_allclose(hpwl_value.data.cpu().numpy(), golden_value)

        # test atomic cpu 
        custom_atomic = hpwl.HPWL(
                xWeight=1.0,
                yWeight=1.0,
                flat_netpin=torch.from_numpy(flat_net2pin_map), 
                netpin_start=torch.from_numpy(flat_net2pin_start_map),
                pin2net_map=torch.from_numpy(pin2net_map), 
                net_weights=torch.from_numpy(net_weights), 
                net_mask=torch.from_numpy(net_mask), 
                num_threads=1,
                algorithm='atomic'
                )
        hpwl_value = custom_atomic.forward(pin_pos_var)
        print("hpwl_value atomic = ", hpwl_value.data.numpy())
        np.testing.assert_allclose(hpwl_value.data.numpy(), golden_value)

        # test atomic gpu 
        if torch.cuda.device_count(): 
            custom_cuda_atomic = hpwl.HPWL(
                    xWeight=1.0,
                    yWeight=1.0,
                    flat_netpin=torch.from_numpy(flat_net2pin_map).cuda(), 
                    netpin_start=torch.from_numpy(flat_net2pin_start_map).cuda(),
                    pin2net_map=torch.from_numpy(pin2net_map).cuda(), 
                    net_weights=torch.from_numpy(net_weights).cuda(), 
                    net_mask=torch.from_numpy(net_mask).cuda(), 
                    num_threads=1,
                    algorithm='atomic'
                    )
            hpwl_value = custom_cuda_atomic.forward(pin_pos_var.cuda())
            print("hpwl_value cuda atomic = ", hpwl_value.data.cpu().numpy())
            np.testing.assert_allclose(hpwl_value.data.cpu().numpy(), golden_value)

if __name__ == '__main__':
    unittest.main()

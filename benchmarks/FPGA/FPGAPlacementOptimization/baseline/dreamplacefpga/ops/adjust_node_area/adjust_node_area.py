##
# @file   adjust_node_area.py
# @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Nov 2020
# @brief  Nonlinear placement engine to be called with parameters and placement database 
#
import math
import torch
from torch import nn
import torch.nn.functional as F
import logging
import pdb

import dreamplacefpga.ops.adjust_node_area.adjust_node_area_cpp as adjust_node_area_cpp
import dreamplacefpga.ops.adjust_node_area.update_pin_offset_cpp as update_pin_offset_cpp

import dreamplacefpga.configure as configure
if configure.compile_configurations["CUDA_FOUND"] == "TRUE":
    import dreamplacefpga.ops.adjust_node_area.adjust_node_area_cuda as adjust_node_area_cuda
    import dreamplacefpga.ops.adjust_node_area.update_pin_offset_cuda as update_pin_offset_cuda

logger = logging.getLogger(__name__)

class ComputeNodeAreaFromRouteMap(nn.Module):
    def __init__(self, xl, yl, xh, yh, flop_lut_indices, num_movable_nodes, num_bins_x,
                 num_bins_y):
        super(ComputeNodeAreaFromRouteMap, self).__init__()
        self.xl = xl
        self.yl = yl
        self.xh = xh
        self.yh = yh
        self.flop_lut_indices = flop_lut_indices
        self.num_movable_nodes = num_movable_nodes
        self.num_bins_x = num_bins_x
        self.num_bins_y = num_bins_y
        self.bin_size_x = (xh - xl) / num_bins_x
        self.bin_size_y = (yh - yl) / num_bins_y

    def forward(self, pos, node_size_x, node_size_y, utilization_map):
        if pos.is_cuda:
            func = adjust_node_area_cuda.forward
        else:
            func = adjust_node_area_cpp.forward
        output = func(pos, node_size_x, node_size_y, utilization_map,
                      self.bin_size_x, self.bin_size_y, self.xl, self.yl,
                      self.xh, self.yh, self.flop_lut_indices, self.num_movable_nodes,
                      self.num_bins_x, self.num_bins_y)
        return output


class ComputeNodeAreaFromPinMap(ComputeNodeAreaFromRouteMap):
    def __init__(self, pin_weights, flat_node2pin_start_map, xl, yl, xh, yh,
                 flop_lut_indices, num_movable_nodes, num_bins_x, num_bins_y, unit_pin_capacity):
        super(ComputeNodeAreaFromPinMap,
              self).__init__(xl, yl, xh, yh, flop_lut_indices, num_movable_nodes, num_bins_x,
                             num_bins_y)
        bin_area = (xh - xl) / num_bins_x * (yh - yl) / num_bins_y
        self.unit_pin_capacity = unit_pin_capacity
        # for each physical node, we use the pin counts as the weights
        if pin_weights is not None:
            self.pin_weights = pin_weights
        elif flat_node2pin_start_map is not None:
            self.pin_weights = flat_node2pin_start_map[
                1:self.num_movable_nodes +
                1] - flat_node2pin_start_map[:self.num_movable_nodes]
        else:
            assert "either pin_weights or flat_node2pin_start_map is required"

    def forward(self, pos, node_size_x, node_size_y, utilization_map):
        output = super(ComputeNodeAreaFromPinMap,
                       self).forward(pos, node_size_x, node_size_y,
                                     utilization_map)
        output.mul_(self.pin_weights[:self.num_movable_nodes].to(node_size_x.dtype) / (node_size_x[:self.num_movable_nodes] * node_size_y[:self.num_movable_nodes] * self.unit_pin_capacity))
        return output


class AdjustNodeArea(nn.Module):
    def __init__(
        self,
        placedb,
        flat_node2pin_map,
        flat_node2pin_start_map,
        pin_weights,  # only one of them needed
        flop_lut_indices,
        flop_lut_mask,
        flop_mask,
        lut_mask,
        total_place_area,  # total placement area excluding fixed cells
        total_whitespace_area,  # total white space area excluding movable and fixed cells
        max_route_opt_adjust_rate,
        route_opt_adjust_exponent=2.5,
        max_pin_opt_adjust_rate=2.5,
        area_adjust_stop_ratio=0.01,
        route_area_adjust_stop_ratio=0.01,
        pin_area_adjust_stop_ratio=0.05,
        unit_pin_capacity=0.0):

        super(AdjustNodeArea, self).__init__()
        self.flat_node2pin_start_map = flat_node2pin_start_map
        self.flat_node2pin_map = flat_node2pin_map
        self.pin_weights = pin_weights

        self.flop_lut_indices = flop_lut_indices
        self.flop_lut_mask = flop_lut_mask
        self.flop_mask = flop_mask
        self.lut_mask = lut_mask

        self.filler_start_map = placedb.filler_start_map
        self.xl = placedb.xl
        self.xh = placedb.xh
        self.yl = placedb.yl
        self.yh = placedb.yh
        self.num_movable_nodes = placedb.num_movable_nodes
        self.num_filler_nodes = placedb.num_filler_nodes

        #mlab
        self.num_mlab_nodes = placedb.num_mlab_nodes
        if self.num_mlab_nodes > 0:
            self.is_mlab_node = placedb.is_mlab_node
            self.is_mlab_filler_node = placedb.is_mlab_filler_node

        #large carry chain nodes
        self.num_ccNodes = placedb.num_ccNodes
        if self.num_ccNodes > 0:
            self.is_cc_node = torch.from_numpy(placedb.is_cc_node).to(self.lut_mask.device)
        # maximum and minimum instance area adjustment rate for routability optimization
        self.max_route_opt_adjust_rate = max_route_opt_adjust_rate
        self.min_route_opt_adjust_rate = 1.0 / max_route_opt_adjust_rate
        # exponent for adjusting the utilization map
        self.route_opt_adjust_exponent = route_opt_adjust_exponent
        # maximum and minimum instance area adjustment rate for routability optimization
        self.max_pin_opt_adjust_rate = max_pin_opt_adjust_rate
        self.min_pin_opt_adjust_rate = 1.0 / max_pin_opt_adjust_rate

        # stop ratio
        self.area_adjust_stop_ratio = area_adjust_stop_ratio
        self.route_area_adjust_stop_ratio = route_area_adjust_stop_ratio
        self.pin_area_adjust_stop_ratio = pin_area_adjust_stop_ratio

        self.compute_node_area_route = ComputeNodeAreaFromRouteMap(
            xl=self.xl,
            yl=self.yl,
            xh=self.xh,
            yh=self.yh,
            flop_lut_indices=self.flop_lut_indices,
            num_movable_nodes=self.num_movable_nodes,
            num_bins_x=placedb.num_routing_grids_x,
            num_bins_y=placedb.num_routing_grids_y)
        self.compute_node_area_pin = ComputeNodeAreaFromPinMap(
            pin_weights=self.pin_weights,
            flat_node2pin_start_map=self.flat_node2pin_start_map,
            xl=self.xl,
            yl=self.yl,
            xh=self.xh,
            yh=self.yh,
            flop_lut_indices=self.flop_lut_indices,
            num_movable_nodes=self.num_movable_nodes,
            num_bins_x=placedb.num_routing_grids_x,
            num_bins_y=placedb.num_routing_grids_y,
            unit_pin_capacity=unit_pin_capacity)

        # placement area excluding fixed cells
        self.total_place_area = total_place_area
        # placement area excluding movable and fixed cells
        self.total_whitespace_area = total_whitespace_area

    def forward(self, pos, node_size_x, node_size_y, pin_offset_x,
                pin_offset_y, target_density, resource_areas,
                route_utilization_map, pin_utilization_map):

        with torch.no_grad():
            adjust_area_flag = True
            adjust_resource_area_flag = resource_areas is not None
            adjust_route_area_flag = route_utilization_map is not None
            adjust_pin_area_flag = pin_utilization_map is not None

            if not (adjust_resource_area_flag or adjust_pin_area_flag or adjust_route_area_flag):
                return False, False, False, False

            num_physical_nodes = node_size_x.numel() - self.num_filler_nodes
            num_flop_lut_fillers = self.filler_start_map[2]
            # compute old areas of movable nodes - Ignore DSP/RAM instances
            node_size_x_movable = node_size_x[:self.num_movable_nodes]
            node_size_y_movable = node_size_y[:self.num_movable_nodes]

            node_size_x_filler = node_size_x[num_physical_nodes:num_physical_nodes+num_flop_lut_fillers]
            node_size_y_filler = node_size_y[num_physical_nodes:num_physical_nodes+num_flop_lut_fillers]
            old_movable_area = node_size_x_movable * node_size_y_movable
            old_filler_area = node_size_x_filler * node_size_y_filler

            #Update for LUT
            old_movable_area_lut_sum = (node_size_x_movable * node_size_y_movable * self.lut_mask[:self.num_movable_nodes]).sum()
            num_lut_fillers = self.filler_start_map[1]
            old_filler_area_lut_sum = (node_size_x_filler[:num_lut_fillers] * node_size_y_filler[:num_lut_fillers]).sum()

            #Update for FF
            old_movable_area_flop_sum = (node_size_x_movable * node_size_y_movable * self.flop_mask[:self.num_movable_nodes]).sum()
            num_flop_fillers = self.filler_start_map[2] - self.filler_start_map[1]
            old_filler_area_flop_sum = (node_size_x_filler[num_lut_fillers:] * node_size_y_filler[num_lut_fillers:]).sum()
            old_filler_area_sum = old_filler_area_lut_sum + old_filler_area_flop_sum

            #No filler space available for nodes to inflate
            if old_filler_area_sum == 0:
                return False, False, False, False

            # compute routability optimized area
            if adjust_route_area_flag:
                # clamp the routing square of routing utilization map
                route_utilization_map_clamp = route_utilization_map.pow(self.route_opt_adjust_exponent).clamp_(
                        min=self.min_route_opt_adjust_rate,
                        max=self.max_route_opt_adjust_rate)
                route_opt_area = self.compute_node_area_route(pos, node_size_x, node_size_y, route_utilization_map_clamp)
            # compute pin density optimized area
            if adjust_pin_area_flag:
                pin_opt_area = self.compute_node_area_pin(pos, node_size_x, node_size_y,
                    # clamp the pin utilization map
                    pin_utilization_map.clamp(min=self.min_pin_opt_adjust_rate, max=self.max_pin_opt_adjust_rate))

            # compute the extra area max(route_opt_area, pin_opt_area) over the base area for each movable node
            # Include all possible conditions
            if adjust_resource_area_flag and adjust_route_area_flag and adjust_pin_area_flag:
                area_increment = F.relu(torch.max(resource_areas[:self.num_movable_nodes], torch.max(route_opt_area, pin_opt_area)) - old_movable_area)
            elif adjust_resource_area_flag and adjust_route_area_flag:
                area_increment = F.relu(torch.max(resource_areas[:self.num_movable_nodes], route_opt_area) - old_movable_area)
            elif adjust_resource_area_flag and adjust_pin_area_flag:
                area_increment = F.relu(torch.max(resource_areas[:self.num_movable_nodes], pin_opt_area) - old_movable_area)
            elif adjust_route_area_flag and adjust_pin_area_flag:
                area_increment = F.relu(torch.max(route_opt_area, pin_opt_area) - old_movable_area)
            elif adjust_resource_area_flag:
                area_increment = F.relu(resource_areas[:self.num_movable_nodes] - old_movable_area)
            elif adjust_route_area_flag:
                area_increment = F.relu(route_opt_area - old_movable_area)
            elif adjust_pin_area_flag:
                area_increment = F.relu(pin_opt_area - old_movable_area)
            else:
                area_increment = torch.zeros(old_movable_area.numel(), dtype=old_movable_area.dtype, device=old_movable_area.device)

            #Restrict inflation of large carry chain nodes
            if self.num_ccNodes > 0:
                cc_mask = self.is_cc_node[:self.num_movable_nodes] == 1
                area_increment[cc_mask] = area_increment[cc_mask].clamp_(max=3.0)

            area_increment_lut_sum = (area_increment * self.lut_mask[:self.num_movable_nodes]).sum()
            area_increment_flop_sum = (area_increment * self.flop_mask[:self.num_movable_nodes]).sum()
            ## check whether the total area is larger than the max area requirement
            scale_factor_lut = max(((self.total_place_area/2.0 - old_movable_area_lut_sum) / area_increment_lut_sum).clamp_(max=1.0), 0.0)
            scale_factor_flop = max(((self.total_place_area/2.0 - old_movable_area_flop_sum) / area_increment_flop_sum).clamp_(max=1.0), 0.0)
            #Incorporate area of placeholder MLAB fillers for FF
            if self.num_mlab_nodes > 0:
                mlab_size_x = node_size_x_movable[self.is_mlab_node[:self.num_movable_nodes] == 1]
                mlab_size_y = node_size_y_movable[self.is_mlab_node[:self.num_movable_nodes] == 1]
                mlab_area = mlab_size_x * mlab_size_y
                scale_factor_flop = max(((self.total_place_area/2.0 - old_movable_area_flop_sum - mlab_area.sum()) / area_increment_flop_sum).clamp_(max=1.0), 0.0)

            # set the new_movable_area as base_area + scaled area increment
            new_movable_area = old_movable_area + (area_increment * scale_factor_lut * self.lut_mask[:self.num_movable_nodes]) + (area_increment * scale_factor_flop * self.flop_mask[:self.num_movable_nodes])

            area_increment_sum = area_increment_lut_sum * scale_factor_lut + area_increment_flop_sum * scale_factor_flop
            old_movable_area_sum = old_movable_area_lut_sum + old_movable_area_flop_sum
            new_movable_area_sum = old_movable_area_sum + area_increment_sum
            area_increment_ratio = area_increment_sum / old_movable_area_sum
            if area_increment_sum > 0:
                logger.info(
                    "area_increment = %E, area_increment / movable = %g, area_adjust_stop_ratio = %g"
                    % (area_increment_sum, area_increment_ratio,
                       self.area_adjust_stop_ratio))
                logger.info(
                    "area_increment / total_place_area = %g, area_increment / filler = %g, area_increment / total_whitespace_area = %g"
                    % (area_increment_sum / self.total_place_area,
                       area_increment_sum / old_filler_area_sum,
                       area_increment_sum / self.total_whitespace_area))

            # compute the adjusted area increase ratio
            # disable some of the area adjustment if the condition holds
            if adjust_resource_area_flag:
                resource_area_increment_ratio = F.relu((resource_areas[:self.num_movable_nodes] - old_movable_area) * self.flop_lut_mask[:self.num_movable_nodes]).sum() / old_movable_area_sum
                adjust_resource_area_flag = resource_area_increment_ratio.item() > self.route_area_adjust_stop_ratio
                logger.info(
                    "resource_area_increment_ratio = %g, resource_area_adjust_stop_ratio = %g"
                    % (resource_area_increment_ratio, self.route_area_adjust_stop_ratio))
            if adjust_route_area_flag:
                route_area_increment_ratio = F.relu((route_opt_area - old_movable_area) * self.flop_lut_mask[:self.num_movable_nodes]).sum() / old_movable_area_sum
                adjust_route_area_flag = route_area_increment_ratio.data.item() > self.route_area_adjust_stop_ratio
                logger.info(
                    "route_area_increment_ratio = %g, route_area_adjust_stop_ratio = %g"
                    % (route_area_increment_ratio, self.route_area_adjust_stop_ratio))
            if adjust_pin_area_flag:
                pin_area_increment_ratio = F.relu((pin_opt_area - old_movable_area) * self.flop_lut_mask[:self.num_movable_nodes]).sum() / old_movable_area_sum
                adjust_pin_area_flag = pin_area_increment_ratio.data.item() > self.pin_area_adjust_stop_ratio
                logger.info(
                    "pin_area_increment_ratio = %g, pin_area_adjust_stop_ratio = %g"
                    % (pin_area_increment_ratio, self.pin_area_adjust_stop_ratio))
            adjust_area_flag = (
                area_increment_ratio.data.item() > self.area_adjust_stop_ratio
            ) and (adjust_resource_area_flag or adjust_route_area_flag or adjust_pin_area_flag)

            if not adjust_area_flag:
                return adjust_area_flag, adjust_resource_area_flag, adjust_route_area_flag, adjust_pin_area_flag

            num_nodes = pos.numel() // 2
            # adjust the size and positions of movable nodes
            # each movable node have its own inflation ratio, the shape of movable_nodes_ratio is (num_movable_nodes)
            # we keep the centers the same
            movable_nodes_ratio = new_movable_area / old_movable_area
            logger.info(
                "inflation ratio for movable nodes: avg/max %g/%g" %
                (movable_nodes_ratio.mean(), movable_nodes_ratio.max()))
            movable_nodes_ratio.sqrt_()
            ## convert positions to centers
            # scale size
            node_size_x_movable *= movable_nodes_ratio
            node_size_y_movable *= movable_nodes_ratio
            ## convert back to lower left corners

            # finally scale the filler instance areas to let the total area be self.total_place_area
            # all the filler nodes share the same deflation ratio, filler_nodes_ratio is a scalar
            if new_movable_area_sum + old_filler_area_sum > self.total_place_area:
                ##Use common filler size for both LUT/FF

                #Update for LUT fillers
                new_movable_area_lut_sum = old_movable_area_lut_sum + area_increment_lut_sum * scale_factor_lut
                new_lut_filler_area = F.relu(self.total_place_area/2 - new_movable_area_lut_sum)/num_lut_fillers
                new_lut_filler_length = new_lut_filler_area.sqrt()

                node_size_x_filler[:num_lut_fillers] = new_lut_filler_length
                node_size_y_filler[:num_lut_fillers] = new_lut_filler_length

                #Update for Flop fillers
                new_movable_area_flop_sum = old_movable_area_flop_sum + area_increment_flop_sum * scale_factor_flop
                new_flop_filler_area = F.relu(self.total_place_area/2 - new_movable_area_flop_sum)/num_flop_fillers
                new_flop_filler_length = new_flop_filler_area.sqrt()

                node_size_x_filler[num_lut_fillers:] = new_flop_filler_length
                node_size_y_filler[num_lut_fillers:] = new_flop_filler_length

                #Old movable area for flops includes mlab placeholder filler area
                if self.num_mlab_nodes > 0:
                    mlab_ff_mask = self.is_mlab_filler_node[num_lut_fillers:num_lut_fillers+num_flop_fillers] == 1
                    mlab_size_x = node_size_x_movable[self.is_mlab_node[:self.num_movable_nodes] == 1]
                    mlab_size_y = node_size_y_movable[self.is_mlab_node[:self.num_movable_nodes] == 1]
                    mlab_area = mlab_size_x * mlab_size_y
                    #assign mlab area to placeholder fillers in FF
                    node_size_x_filler[num_lut_fillers:][mlab_ff_mask] = mlab_size_x
                    node_size_y_filler[num_lut_fillers:][mlab_ff_mask] = mlab_size_y
                    new_movable_area_flop_sum = (node_size_x_movable * node_size_y_movable * self.flop_mask[:self.num_movable_nodes]).sum()
                    if new_movable_area_flop_sum + mlab_area.sum() > self.total_place_area/2:
                        logger.info(
                            "FLOP: new movable area %.3E + mlab placeholder filler area %.3E > total_place_area  %.3E - CHECK!"
                            % (new_movable_area_flop_sum, mlab_area.sum(),self.total_place_area/2))
                    new_flop_filler_area = F.relu(self.total_place_area/2 - new_movable_area_flop_sum - mlab_area.sum())
                    new_flop_filler_area /= (num_flop_fillers - self.num_mlab_nodes)
                    new_flop_filler_length = new_flop_filler_area.sqrt()
                    node_size_x_filler[num_lut_fillers:] = new_flop_filler_length
                    node_size_y_filler[num_lut_fillers:] = new_flop_filler_length
                    #Update new_flop_filler_area to correct value
                    new_flop_filler_area = F.relu(self.total_place_area/2 - new_movable_area_flop_sum)
                    new_flop_filler_area /= num_flop_fillers

                new_filler_area_sum = F.relu(self.total_place_area - new_movable_area_sum)
            else:
                new_filler_area_sum = old_filler_area_sum
                new_movable_area_lut_sum = old_movable_area_lut_sum
                new_lut_filler_area = old_filler_area_lut_sum/num_lut_fillers
                new_movable_area_flop_sum = old_movable_area_flop_sum
                new_flop_filler_area = old_filler_area_flop_sum/num_flop_fillers

            logger.info(
                "old total movable nodes area %.3E, filler area %.3E, total movable + filler area %.3E, total_place_area %.3E"
                % (old_movable_area_sum, old_filler_area_sum,
                   old_movable_area_sum + old_filler_area_sum,
                   self.total_place_area))
            logger.info(
                "LUT old movable nodes area %.3E, filler area %.3E, total movable + filler area %.3E, total_place_area %.3E"
                % (old_movable_area_lut_sum, old_filler_area_lut_sum,
                   old_movable_area_lut_sum+old_filler_area_lut_sum,
                   self.total_place_area/2))
            logger.info(
                "FLOP old movable nodes area %.3E, filler area %.3E, total movable + filler area %.3E, total_place_area %.3E"
                % (old_movable_area_flop_sum, old_filler_area_flop_sum,
                   old_movable_area_flop_sum+old_filler_area_flop_sum,
                   self.total_place_area/2))


            logger.info(
                "new total movable nodes area %.3E, filler area %.3E, total movable + filler area %.3E, total_place_area %.3E"
                % (new_movable_area_sum, new_filler_area_sum,
                   new_movable_area_sum + new_filler_area_sum,
                   self.total_place_area))
            logger.info(
                "LUT new movable nodes area %.3E, filler area %.3E, total movable + filler area %.3E, total_place_area %.3E"
                % (new_movable_area_lut_sum, new_lut_filler_area * num_lut_fillers,
                   new_movable_area_lut_sum + new_lut_filler_area * num_lut_fillers,
                   self.total_place_area/2))
            logger.info(
                "FLOP new movable nodes area %.3E, filler area %.3E, total movable + filler area %.3E, total_place_area %.3E"
                % (new_movable_area_flop_sum, new_flop_filler_area * num_flop_fillers,
                   new_movable_area_flop_sum + new_flop_filler_area * num_flop_fillers,
                   self.total_place_area/2))

            if pos.is_cuda:
                func = update_pin_offset_cuda.forward
            else:
                func = update_pin_offset_cpp.forward
            func(node_size_x, node_size_y, self.flat_node2pin_start_map,
                 self.flat_node2pin_map, movable_nodes_ratio,
                 self.num_movable_nodes, pin_offset_x, pin_offset_y)
            return adjust_area_flag, adjust_resource_area_flag, adjust_route_area_flag, adjust_pin_area_flag

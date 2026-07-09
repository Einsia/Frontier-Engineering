##
# @file   NonLinearPlace.py
# @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Sep 2020
# @brief  Nonlinear placement engine to be called with parameters and placement database 
#

import os 
import sys
import time 
import pickle
import numpy as np 
import logging
import torch 
import gzip 
import copy
import matplotlib.pyplot as plt
if sys.version_info[0] < 3: 
    import cPickle as pickle
else:
    import _pickle as pickle
from BasicPlace import *
from PlaceObj import *
from EvalMetrics import *
import NesterovAcceleratedGradientOptimizer
import pdb 
import dreamplacefpga.ops.dsp_ram_legalization.dsp_ram_legalization as dsp_ram_legalization

class NonLinearPlaceFPGA (BasicPlaceFPGA):
    """
    @brief Nonlinear placement engine. 
    It takes parameters and placement database and runs placement flow. 
    """
    def __init__(self, params, placedb):
        """
        @brief initialization. 
        @param params parameters 
        @param placedb placement database 
        """
        super(NonLinearPlaceFPGA, self).__init__(params, placedb)

    def __call__(self, params, placedb):
        """
        @brief Top API to solve placement. 
        @param params parameters 
        @param placedb placement database 
        """
        iteration = 0
        blockLegalIter = 0
        all_metrics = []

        # global placement 
        if params.global_place_flag: 
            # global placement may run in multiple stages according to user specification 
            for global_place_params in params.global_place_stages:

                # we formulate each stage as a 3-nested optimization problem 
                # f_gamma(g_density(h(x) ; density weight) ; gamma)
                # Lgamma      Llambda        Lsub
                # When optimizing an inner problem, the outer parameters are fixed.
                # This is a generalization to the eplace/RePlAce approach 

                # As global placement may easily diverge, we record the position of best overflow
                best_metric = [None]
                best_pos = [None]

                if params.gpu: 
                    torch.cuda.synchronize()
                tt = time.time()
                # construct model and optimizer 
                density_weight = 0.0
                # construct placement model 
                model = PlaceObjFPGA(density_weight, params, placedb, self.data_collections, self.op_collections, global_place_params).to(self.data_collections.pos[0].device)
                #print("Model constructed in %g ms"%((time.time()-tt)*1000))

                optimizer_name = global_place_params["optimizer"]

                # determine optimizer
                if optimizer_name.lower() == "adam": 
                    optimizer = torch.optim.Adam(self.parameters(), lr=0)
                elif optimizer_name.lower() == "sgd": 
                    optimizer = torch.optim.SGD(self.parameters(), lr=0)
                elif optimizer_name.lower() == "sgd_momentum": 
                    optimizer = torch.optim.SGD(self.parameters(), lr=0, momentum=0.9, nesterov=False)
                elif optimizer_name.lower() == "sgd_nesterov": 
                    optimizer = torch.optim.SGD(self.parameters(), lr=0, momentum=0.9, nesterov=True)
                elif optimizer_name.lower() == "nesterov": 
                    optimizer = NesterovAcceleratedGradientOptimizer.NesterovAcceleratedGradientOptimizer(self.parameters(), 
                            lr=0, 
                            obj_and_grad_fn=model.obj_and_grad_fn,
                            constraint_fn=self.op_collections.move_boundary_op,
                            )
                else:
                    assert 0, "unknown optimizer %s" % (optimizer_name)

                logging.info("use %s optimizer" % (optimizer_name))

                model.train()
                # defining evaluation ops 
                eval_ops = {
                        "hpwl" : self.op_collections.hpwl_op, 
                        "overflow" : self.op_collections.density_overflow_op
                        }
                if params.routability_opt_flag:
                    eval_ops.update({
                        'clustering_compatibility_lut':
                        self.op_collections.clustering_compatibility_lut_area_op, 
                        'clustering_compatibility_ff':
                        self.op_collections.clustering_compatibility_ff_area_op, 
                        'route_utilization':
                        self.op_collections.route_utilization_map_op,
                        'pin_utilization':
                        self.op_collections.pin_utilization_map_op
                    })
                #For fence regions
                eval_ops.update({
                    'density':
                    self.op_collections.fence_region_density_merged_op,
                    "overflow":
                    self.op_collections.fence_region_density_overflow_merged_op,
                })

                #Initialization moved before printing metrics
                if torch.eq(torch.mean(model.density_weight), 0.0):
                    model.initialize_density_weight(params, placedb)
                    #logging.info("density_weight = [%s]" % ", ".join(["%.3E" % i for i in model.density_weight.cpu().numpy().tolist()]))

                # a function to initialize learning rate 
                def initialize_learning_rate(pos):
                    learning_rate = model.estimate_initial_learning_rate(pos)
                    # update learning rate 
                    for param_group in optimizer.param_groups:
                        param_group['lr'] = learning_rate.data

                if iteration == 0: 
                    if params.gp_noise_ratio > 0.0: 
                        #logging.info("add %g%% noise" % (params.gp_noise_ratio*100))
                        model.op_collections.noise_op(model.data_collections.pos[0], params.gp_noise_ratio)
                        initialize_learning_rate(model.data_collections.pos[0])
                # the state must be saved after setting learning rate 
                initial_state = copy.deepcopy(optimizer.state_dict())

                if params.gpu: 
                    torch.cuda.synchronize()
                #logging.info("%s initialization takes %g seconds" % (optimizer_name, (time.time()-tt)))

                # as nesterov requires line search, we cannot follow the convention of other solvers
                if optimizer_name.lower() in {"sgd", "adam", "sgd_momentum", "sgd_nesterov"}: 
                    model.obj_and_grad_fn(model.data_collections.pos[0])
                elif optimizer_name.lower() != "nesterov":
                    assert 0, "unsupported optimizer %s" % (optimizer_name)

                # stopping criteria 
                def Lgamma_stop_criterion(placedb, Lgamma_step, metrics, stop_mask=None): 
                    with torch.no_grad():
                        if len(metrics) > 1: 
                            cur_metric = metrics[-1][-1][-1]
                            prev_metric = metrics[-2][-1][-1]

                            if Lgamma_step > 100 and (((cur_metric.overflow.cpu().numpy() < placedb.targetOverflow).sum() == len(placedb.targetOverflow) and cur_metric.hpwl > prev_metric.hpwl) or 
                                cur_metric.max_density.max() < 1.0) and (placedb.num_movable_nodes_fence_region[placedb.dsp_ram_compIds].sum() == 0 or blockLegalIter >= 5):
                                logInfo = "Lgamma stopping criteria: " + str(Lgamma_step) + " > 100 and (( OVFL: "
                                for el in range(placedb.targetOverflow.size):
                                    logInfo += str(round(cur_metric.overflow[el].item(),4)) + " < " + str(placedb.targetOverflow[el]) + "; "
                                logInfo += " and HPWL " + '{:.4e}'.format(cur_metric.hpwl.item()) + " > " + '{:.4e}'.format(prev_metric.hpwl.item()) + " ) or "
                                logInfo += str(round(cur_metric.max_density.max().item(),4)) + " < 1.0) and DSP/RAM block legal iter " + str(blockLegalIter) + " >= 5"
                                logging.info(logInfo)
                                return True
                        return False 

                def Llambda_stop_criterion(placedb, Lgamma_step, Llambda_density_weight_step, metrics): 
                    with torch.no_grad(): 
                        if len(metrics) > 1: 
                            cur_metric = metrics[-1][-1]
                            prev_metric = metrics[-2][-1]
                            if ((cur_metric.overflow.cpu().numpy() < placedb.targetOverflow).sum() == len(placedb.targetOverflow) and
                                cur_metric.hpwl > prev_metric.hpwl and (placedb.num_movable_nodes_fence_region[placedb.dsp_ram_compIds].sum() == 0 or blockLegalIter >= 5)) or cur_metric.max_density[-1] < 1.0:
                                logInfo = "Llambda stopping criteria: " + str(Llambda_density_weight_step) + " and (( OVFL: "
                                for el in range(placedb.targetOverflow.size):
                                    logInfo += str(round(cur_metric.overflow[el].item(),4)) + " < " + str(placedb.targetOverflow[el]) + "; "
                                logInfo += " and HPWL " + '{:.4e}'.format(cur_metric.hpwl.item()) + " > " + '{:.4e}'.format(prev_metric.hpwl.item()) + " ) or "
                                logInfo += str(round(cur_metric.max_density.max().item(),4)) + " < 1.0)"
                                return True
                    return False 

                # use a moving average window for stopping criteria, for an example window of 3
                # 0, 1, 2, 3, 4, 5, 6
                #    window2
                #             window1
                moving_avg_window = max(min(model.Lsub_iteration // 2, 3), 1)
                def Lsub_stop_criterion(Lgamma_step, Llambda_density_weight_step, Lsub_step, metrics):
                    with torch.no_grad(): 
                        if len(metrics) >= moving_avg_window * 2: 
                            cur_avg_obj = 0
                            prev_avg_obj = 0
                            for i in range(moving_avg_window):
                                cur_avg_obj += metrics[-1 - i].objective
                                prev_avg_obj += metrics[-1 - moving_avg_window - i].objective
                            cur_avg_obj /= moving_avg_window 
                            prev_avg_obj /= moving_avg_window
                            threshold = 0.999
                            if cur_avg_obj >= prev_avg_obj * threshold:
                                logging.info("Lsub stopping criteria: %d and %g > %g * %g" % (Lsub_step, cur_avg_obj, prev_avg_obj, threshold))
                                return True 
                    return False 

                def one_descent_step(Lgamma_step, Llambda_density_weight_step, Lsub_step, iteration, metrics, stop_mask=None):

                    # metric for this iteration 
                    cur_metric = EvalMetricsFPGA(iteration, (Lgamma_step, Llambda_density_weight_step, Lsub_step))
                    cur_metric.gamma = model.gamma.data
                    cur_metric.density_weight = model.density_weight.data
                    metrics.append(cur_metric)
                    pos = model.data_collections.pos[0]

                    # move any out-of-bound cell back to placement region 
                    self.op_collections.move_boundary_op(pos)
                    optimizer.zero_grad()
                    cur_metric.evaluate(placedb, eval_ops, pos, model.data_collections)
                    model.overflow = cur_metric.overflow.data.clone()
                    #logging.debug("evaluation %.3f ms" % ((time.time()-t1)*1000))
                    #t2 = time.time()

                    # as nesterov requires line search, we cannot follow the convention of other solvers
                    if optimizer_name.lower() in ["sgd", "adam", "sgd_momentum", "sgd_nesterov"]: 
                        obj, grad = model.obj_and_grad_fn(pos)
                        cur_metric.objective = obj.data.clone()
                    elif optimizer_name.lower() != "nesterov":
                        assert 0, "unsupported optimizer %s" % (optimizer_name)

                    # plot placement 
                    if params.plot_flag and (iteration % 100 == 0): 
                        cur_pos = self.pos[0].data.clone().cpu().numpy()
                        self.plot(params, placedb, iteration, cur_pos)

                    logging.info(cur_metric)

                    t3 = time.time()
                    if(model.update_mask is not None):
                        pos_bk = pos.data.clone()
                        optimizer.step()
                        # print(model.update_mask)
                        for region_id, fence_region_update_flag in enumerate(model.update_mask):
                            #If there are no elements of resource type, skip
                            if(fence_region_update_flag == 0 and placedb.num_movable_nodes_fence_region[region_id] > 0):
                                ### don't update cell location in that region
                                mask = self.op_collections.fence_region_density_ops[region_id].pos_mask
                                pos.data.masked_scatter_(mask, pos_bk[mask])
                    else:
                        optimizer.step()

                    #TODO - For Stratix-IV: mlab is treated as lut type as sites for MLAB/LAB are not distinguished
                    #Update locations of pseudo filler nodes
                    if placedb.num_mlab_nodes > 0:
                        mlab_locations_x = pos[:placedb.num_physical_nodes][placedb.is_mlab_node].data
                        mlab_locations_y = pos[placedb.num_nodes:placedb.num_nodes+placedb.num_physical_nodes][placedb.is_mlab_node].data
                        pos[:placedb.num_nodes][placedb.is_mlab_filler_node == 1].data.copy_(mlab_locations_x)
                        pos[placedb.num_nodes:][placedb.is_mlab_filler_node == 1].data.copy_(mlab_locations_y)

                    # nesterov has already computed the objective of the next step 
                    if optimizer_name.lower() == "nesterov":
                        cur_metric.objective = optimizer.param_groups[0]['obj_k_1'][0].data.clone()
                        #print("Nesterov objective %f \n"%(tobj.data.clone()))
                        #print("HPWL is %g; Obj is %g \n" %(cur_metric.hpwl, cur_metric.objective))

                    # actually reports the metric before step 
                    #logging.info(cur_metric)
                    # record the best outer cell overflow
                    if best_metric[0] is None or (best_metric[0].overflow > cur_metric.overflow).sum().item() == cur_metric.overflow.size()[0]:
                        best_metric[0] = cur_metric
                        if best_pos[0] is None:
                            best_pos[0] = self.pos[0].data.clone()
                        else:
                            best_pos[0].data.copy_(self.pos[0].data)

                    #logging.info("full step %.3f ms" % ((time.time()-t0)*1000))

                def check_plateau(x, window=10, threshold=0.001):
                    if(len(x) < window):
                        return False
                    x = x[-window:]
                    return (np.max(x) - np.min(x)) / np.mean(x) < threshold

                def check_divergence(x, window=50, threshold=0.05):
                    if(len(x) < window):
                        return False
                    x = np.array(x[-window:])
                    smooth = max(1,int(0.1*window))
                    wl_beg, wl_end = np.mean(x[0:smooth,0]), np.mean(x[-smooth:,0])
                    overflow_beg, overflow_end = np.mean(x[0:smooth,1]), np.mean(x[-smooth:,1])
                    # wl_ratio, overflow_ratio = (wl_end - wl_beg)/wl_beg, (overflow_end - max(placedb.targetOverflow.max(), best_metric[0].overflow))/best_metric[0].overflow
                    overflow_mean = np.mean(x[:,1])
                    overflow_diff = np.maximum(0,np.sign(x[1:,1] - x[:-1,1])).astype(np.float32)
                    overflow_diff = np.sum(overflow_diff) / overflow_diff.shape[0]
                    overflow_range = np.max(x[:,1]) - np.min(x[:,1])
                    wl_mean = np.mean(x[:,0])
                    wl_ratio, overflow_ratio = (wl_mean - best_metric[0].hpwl.item())/best_metric[0].hpwl.item(), (overflow_mean - max(placedb.targetOverflow.max(), best_metric[0].overflow.max().item()))/best_metric[0].overflow.max().item()
                    if(wl_ratio > threshold*1.2):
                        if(overflow_ratio > threshold):
                            print(f"[Warning] Divergence detected: overflow increases too much than best overflow ({overflow_ratio:.4f} > {threshold:.4f})")
                            return True
                        elif(overflow_range/overflow_mean < threshold):
                            print(f"[Warning] Divergence detected: overflow plateau ({overflow_range/overflow_mean:.4f} < {threshold:.4f})")
                            return True
                        elif(overflow_diff > 0.6):
                            print(f"[Warning] Divergence detected: overflow fluctuate too frequently ({overflow_diff:.2f} > 0.6)")
                            return True
                        else:
                            return False
                    else:
                        return False

                Lgamma_metrics = all_metrics

                if params.routability_opt_flag: 
                    adjust_area_flag = True
                    adjust_resource_area_flag = params.adjust_resource_area_flag
                    adjust_route_area_flag = params.adjust_route_area_flag
                    adjust_pin_area_flag = params.adjust_pin_area_flag
                    num_area_adjust = 0

                Llambda_flat_iteration = 0

                ### self-adaptive divergence check
                overflow_list = np.ones((len(placedb.region_boxes)), dtype=placedb.dtype)
                divergence_list = []
                min_perturb_interval = 50
                stop_placement = 0
                last_perturb_iter = -min_perturb_interval
                noise_injected_flag = 0
                perturb_counter = 0
                allow_update = 1

                # Start to compute time for optimization without parsing and initialization
                optimization_timer = time.time()
                for Lgamma_step in range(model.Lgamma_iteration):
                    Lgamma_metrics.append([])
                    Llambda_metrics = Lgamma_metrics[-1]
                    for Llambda_density_weight_step in range(model.Llambda_density_weight_iteration):
                        Llambda_metrics.append([])
                        Lsub_metrics = Llambda_metrics[-1]
                        for Lsub_step in range(model.Lsub_iteration):
                            ## Divergence threshold should decrease as overflow decreases
                            ## Only detect divergence when overflow is relatively low but not too low
                            if(((placedb.targetOverflow * 1.1 < overflow_list).sum() == len(placedb.targetOverflow) and (overflow_list < placedb.targetOverflow).sum() == len(placedb.targetOverflow)) and check_divergence(divergence_list, window=3, threshold=0.01 * overflow_list)):
                                self.pos[0].data.copy_(best_pos[0].data)
                                stop_placement = 1
                                allow_update = 0
                                logging.error(
                                    "possible DIVERGENCE detected, roll back to the best position recorded and switch to ZerothOrderSearch of overflow and hpwl"
                                )

                            ct0 = time.time()
                            one_descent_step(Lgamma_step, Llambda_density_weight_step, Lsub_step, iteration, Lsub_metrics)
                            #print("Time for one step: %g ms" %((time.time()-ct0)*1000))
                            iteration += 1
                            if model.lock_mask is not None and model.lock_mask[placedb.dsp_ram_compIds].sum() == len(placedb.dsp_ram_compIds):
                                blockLegalIter += 1
                            # stopping criteria 
                            if Lsub_stop_criterion(Lgamma_step, Llambda_density_weight_step, Lsub_step, Lsub_metrics):
                                break 
                        Llambda_flat_iteration += 1
                        # update density weight 
                        if Llambda_flat_iteration > 1: 
                            model.op_collections.update_density_weight_op(Llambda_metrics[-1][-1], Llambda_metrics[-2][-1] if len(Llambda_metrics) > 1 else Lgamma_metrics[-2][-1][-1], Llambda_flat_iteration)
                        #logging.debug("update density weight %.3f ms" % ((time.time()-t2)*1000))
                        if Llambda_stop_criterion(placedb, Lgamma_step, Llambda_density_weight_step, Llambda_metrics):
                            break 

                        if (params.routability_opt_flag and num_area_adjust < params.max_num_area_adjust and
                            (Llambda_metrics[-1][-1].overflow[placedb.slice_compIds] < self.data_collections.node_area_adjust_overflow[placedb.slice_compIds]).sum().item() == len(placedb.slice_compIds)):
                            pos = model.data_collections.pos[0]

                            route_utilization_map = None 
                            pin_utilization_map = None
                            resource_areas = None
                            if adjust_route_area_flag: 
                                #Use RUDY for FPGA
                                route_utilization_map = model.op_collections.route_utilization_map_op(pos)
                                if params.plot_flag:
                                    path = "%s/%s" % (params.result_dir, params.design_name())
                                    figname = "%s/plot/rudy%d.png" % (path, num_area_adjust)
                                    os.system("mkdir -p %s" % (os.path.dirname(figname)))
                                    plt.imsave(figname, route_utilization_map.data.cpu().numpy().T, origin='lower')
                            if adjust_pin_area_flag:
                                pin_utilization_map = model.op_collections.pin_utilization_map_op(pos)
                                if params.plot_flag: 
                                    path = "%s/%s" % (params.result_dir, params.design_name())
                                    figname = "%s/plot/pin%d.png" % (path, num_area_adjust)
                                    os.system("mkdir -p %s" % (os.path.dirname(figname)))
                                    plt.imsave(figname, pin_utilization_map.data.cpu().numpy().T, origin='lower')
                            # Compute LUT/FF clustering compatibility optimized resource areas
                            if adjust_resource_area_flag:
                                lut_resource_areas = model.op_collections.clustering_compatibility_lut_area_op(pos)
                                ff_resource_areas = model.op_collections.clustering_compatibility_ff_area_op(pos)
                                resource_areas = lut_resource_areas + ff_resource_areas

                            adjust_area_flag, adjust_resource_area_flag, adjust_route_area_flag, adjust_pin_area_flag = model.op_collections.adjust_node_area_op(
                                    pos,
                                    resource_areas,
                                    route_utilization_map,
                                    pin_utilization_map
                                    )
                            content = "routability optimization round %d: adjust area flags = (%d, %d, %d, %d)" % (num_area_adjust, adjust_area_flag, adjust_resource_area_flag, adjust_route_area_flag, adjust_pin_area_flag)
                            logging.info(content)
                            if adjust_area_flag: 
                                num_area_adjust += 1

                                #Record position before instance area update
                                best_metric[0] = Llambda_metrics[-1][-1]
                                if best_pos[0] is None:
                                    best_pos[0] = model.data_collections.pos[0].data.clone()
                                else:
                                    best_pos[0].data.copy_(model.data_collections.pos[0].data)

                                #Compute new node areas
                                for el in range(len(placedb.slice_compIds)):
                                    rsrcId = placedb.comp2rsrcId_map[el]
                                    mask = model.data_collections.node2fence_region_map == rsrcId
                                    model.data_collections.total_movable_node_area_fence_region[el] = (model.data_collections.node_size_x[:model.data_collections.num_physical_nodes] * model.data_collections.node_size_y[:model.data_collections.num_physical_nodes] * mask).sum()
                                
                                #Update node areas
                                model.data_collections.node_areas = model.data_collections.node_size_x * model.data_collections.node_size_y

                                # restart Llambda 
                                model.op_collections.density_op.reset(model.data_collections) 
                                model.op_collections.density_overflow_op.reset()
                                model.op_collections.pin_utilization_map_op.reset()
                                for fence_reg in model.op_collections.fence_region_density_ops:
                                    fence_reg.reset(model.data_collections)

                                cur_metric = EvalMetricsFPGA(iteration, (Lgamma_step, Llambda_density_weight_step, Lsub_step))
                                cur_metric.gamma = model.gamma.data
                                cur_metric.density_weight = model.density_weight.data
                                cur_metric.evaluate(placedb, eval_ops, pos, model.data_collections)
                                model.overflow = cur_metric.overflow.data.clone()

                                model.op_collections.update_gamma_op(Lgamma_step, model.overflow)
                                model.reset_density_weight(params, placedb, 0.1)
                                #logging.info("density_weight = [%s]" % ", ".join(["%.3E" % i for i in model.density_weight.cpu().numpy().tolist()]))

                                # load state to restart the optimizer 
                                optimizer.load_state_dict(initial_state)
                                # must after loading the state 
                                initialize_learning_rate(pos)
                                # increase iterations of the sub problem to slow down the search 
                                model.Lsub_iteration = model.routability_Lsub_iteration

                                break 

                        ##DSP/RAM legalization condition check
                        if len(placedb.dsp_ram_compIds) > 0 and placedb.num_movable_nodes_fence_region[placedb.dsp_ram_compIds].max() > 0 and (Llambda_metrics[-1][-1].overflow < model.data_collections.targetOverflow).sum().item() == model.data_collections.targetOverflow.size()[0]:
                            pos = model.data_collections.pos[0]
                            if model.lock_mask is not None and model.lock_mask[placedb.dsp_ram_compIds].sum() == len(placedb.dsp_ram_compIds):
                                break

                            ## plot placement 
                            #if params.plot_flag:
                            #    cur_pos = pos.data.clone().cpu().numpy()
                            #    self.plot(params, placedb, iteration, cur_pos)
                            #    iteration += 1

                            #Legalize DSP/RAM at the end of Global placement
                            for lgId in placedb.dsp_ram_rsrcIds:
                                if placedb.node_count[lgId] > 0:
                                    movVal = dsp_ram_legalization.LegalizeDSPRAMFunction.legalize(pos, placedb, lgId, model)
                                    logging.info("Legalized %d %s instances with maxMov = %g and avgMov = %g" %
                                                  (placedb.node_count[lgId], placedb.rsrcTypes[lgId], movVal[0], movVal[1]))

                            ## plot placement 
                            #if params.plot_flag:
                            #    cur_pos = pos.data.clone().cpu().numpy()
                            #    self.plot(params, placedb, iteration, cur_pos)
                            #    iteration += 1

                            #Lock DSP/RAM locations
                            model.lock_mask[placedb.dsp_ram_compIds] = True
                            model.update_mask = ~model.lock_mask
                            pos.grad[0:placedb.num_physical_nodes].data.masked_fill_(model.data_collections.dsp_ram_mask, 0.0)
                            pos.grad[placedb.num_nodes:placedb.num_nodes+placedb.num_physical_nodes].data.masked_fill_(model.data_collections.dsp_ram_mask, 0.0)

                            # restart Llambda 
                            for fence_reg in model.op_collections.fence_region_density_ops:
                                fence_reg.setLockDSPRAM()

                            #Restart place params
                            cur_metric = EvalMetricsFPGA(iteration, (Lgamma_step, Llambda_density_weight_step, Lsub_step))
                            cur_metric.gamma = model.gamma.data
                            cur_metric.density_weight = model.density_weight.data
                            cur_metric.evaluate(placedb, eval_ops, pos, model.data_collections)
                            model.overflow = cur_metric.overflow.data.clone()

                            model.op_collections.update_gamma_op(Lgamma_step, model.overflow)

                            model.reset_density_weight(params, placedb, 1.0)
                            #logging.info("density_weight = [%s]" % ", ".join(["%.3E" % i for i in model.density_weight.cpu().numpy().tolist()]))

                            # load state to restart the optimizer 
                            optimizer.load_state_dict(initial_state)
                            # must after loading the state 
                            initialize_learning_rate(pos)
                            # increase iterations of the sub problem to slow down the search 
                            model.Lsub_iteration = model.routability_Lsub_iteration

                            break 

                    # gradually reduce gamma to tradeoff smoothness and accuracy 
                    model.op_collections.update_gamma_op(Lgamma_step, Llambda_metrics[-1][-1].overflow)

                    if Lgamma_stop_criterion(placedb, Lgamma_step, Lgamma_metrics) or stop_placement == 1:
                        break

                    # update learning rate 
                    if optimizer_name.lower() in ["sgd", "adam", "sgd_momentum", "sgd_nesterov", "cg"]: 
                        if 'learning_rate_decay' in global_place_params: 
                            for param_group in optimizer.param_groups:
                                param_group['lr'] *= global_place_params['learning_rate_decay']

########################################
########################################

                    def solve_problem_2(pos_w, admm_multiplier, non_fence_regions_ex, non_fence_regions, iteration):
                        def check_valid(regions, pos_x, pos_y, pos_xh, pos_yh, valid_margin_x=0, valid_margin_y=0):
                            if(type(regions) == list):
                                regions = np.concatenate(regions,0)
                            valid_mask = torch.ones_like(pos_x, dtype=torch.bool)
                            for sub_region in regions:
                                xll, yll, xhh, yhh = sub_region
                                valid_margin_x = min((xhh-xll)/2, valid_margin_x)
                                valid_margin_y = min((yhh-yll)/2, valid_margin_y)
                                valid_mask.masked_fill_((pos_x < xhh-valid_margin_x) & (pos_xh > xll+valid_margin_x) & (pos_y < yhh-valid_margin_y) & (pos_yh > yll+valid_margin_y), 0)
                            return valid_mask

                        num_nodes = placedb.num_nodes
                        num_movable_nodes = placedb.num_movable_nodes

                        pos_g = pos_w + admm_multiplier # minimize the L2 norm
                        # node2fence_region_map = torch.from_numpy(placedb.node2fence_region_map[:num_movable_nodes]).to(pos_g.device)
                        node2fence_region_map = self.data_collections.node2fence_region_map

                        pos_x, pos_y = pos_g[:num_movable_nodes], pos_g[num_nodes:num_nodes + num_movable_nodes]
                        node_size_x, node_size_y = model.data_collections.node_size_x[:num_movable_nodes], model.data_collections.node_size_y[:num_movable_nodes]
                        num_regions = len(placedb.region_boxes)

                        regions = placedb.region_boxes
                        # margin = 20 * 0.997**iteration
                        margin_x = placedb.bin_size_x * min(1,4*0.997**iteration)
                        margin_y = placedb.bin_size_y * min(1,4*0.997**iteration)

                        # valid_margin = 1000 * 0.995**iteration
                        valid_margin_x = placedb.bin_size_x * 200*0.996**iteration
                        valid_margin_y = placedb.bin_size_y * 200*0.996**iteration
                        # valid_margin = 0 if valid_margin < 5 else valid_margin
                        ### move cells into fence regions
                        for i in range(num_regions):
                            if i in placedb.fixed_rsrcIds:
                                continue
                            mask = (node2fence_region_map == i)
                            pos_x_i, pos_y_i = pos_x[mask], pos_y[mask]
                            num_movable_nodes_i = pos_x_i.numel()
                            node_size_x_i, node_size_y_i = node_size_x[mask], node_size_y[mask]
                            pos_xh_i = pos_x_i + node_size_x_i
                            pos_yh_i = pos_y_i + node_size_y_i
                            regions_i = regions[i] # [n_regions, 4]
                            delta_min = torch.empty(num_movable_nodes_i, device=pos_x.device).fill_(((placedb.xh-placedb.xl)**2+(placedb.yh-placedb.yl)**2))
                            delta_x_min = torch.zeros_like(delta_min)
                            delta_y_min = torch.zeros_like(delta_min)

                            valid_mask = check_valid(non_fence_regions[i], pos_x_i, pos_y_i, pos_xh_i, pos_yh_i, valid_margin_x, valid_margin_y)

                            for sub_region in regions_i:
                                delta_x = torch.zeros_like(delta_min)
                                delta_y = torch.zeros_like(delta_min)
                                xl, yl, xh, yh = sub_region

                                # on the left
                                mask_l = (pos_x_i < xl + margin_x).masked_fill_(valid_mask, 0)
                                # on the right
                                mask_r = (pos_xh_i > xh - margin_x).masked_fill_(valid_mask, 0)
                                # on the top
                                mask_t = (pos_yh_i > yh - margin_y).masked_fill_(valid_mask, 0)
                                # on the bottom
                                mask_b = (pos_y_i < yl + margin_y).masked_fill_(valid_mask, 0)

                                # x replacement for left cell
                                delta_x.masked_scatter_(mask_l, xl + margin_x - pos_x_i[mask_l])
                                # x replacement for right cell
                                delta_x.masked_scatter_(mask_r, xh - margin_x - pos_xh_i[mask_r])
                                # delta_x.masked_fill_(~(mask_l | mask_r), 0)
                                # y replacement for top cell
                                delta_y.masked_scatter_(mask_t, yh - margin_y - pos_yh_i[mask_t])
                                # y replacement for bottom cell
                                delta_y.masked_scatter_(mask_b, yl + margin_y - pos_y_i[mask_b])
                                # delta_y.masked_fill_(~(mask_t | mask_b), 0)
                                # update minimum replacement
                                delta_i = (delta_x ** 2 + delta_y ** 2)
                                update_mask = delta_i < delta_min

                                delta_x_min.masked_scatter_(update_mask, delta_x[update_mask])
                                delta_y_min.masked_scatter_(update_mask, delta_y[update_mask])
                                delta_min.masked_scatter_(update_mask, delta_i[update_mask])

                            # update the minimum replacement for subregions
                            pos_x.masked_scatter_(mask, pos_x_i + delta_x_min)
                            pos_y.masked_scatter_(mask, pos_y_i + delta_y_min)

                        ### move cells out of fence regions
                        # margin = 0
                        # valid_margin = 100 * 0.99**iteration
                        exclude_mask = (node2fence_region_map == placedb.rIOIdx) | (node2fence_region_map == placedb.rPLLIdx)
                        pos_x_ex, pos_y_ex = pos_x[exclude_mask], pos_y[exclude_mask]
                        node_size_x_ex, node_size_y_ex = node_size_x[exclude_mask], node_size_y[exclude_mask]
                        pos_xh_ex = pos_x_ex + node_size_x_ex
                        pos_yh_ex = pos_y_ex + node_size_y_ex

                        delta_min = torch.empty(pos_x_ex.numel(), device=pos_x.device).fill_(((placedb.xh-placedb.xl)**2+(placedb.yh-placedb.yl)**2))
                        delta_x_min = torch.zeros_like(delta_min)
                        delta_y_min = torch.zeros_like(delta_min)
                        ### don't move valid cells
                        valid_mask = check_valid(regions, pos_x_ex, pos_y_ex, pos_xh_ex, pos_yh_ex, valid_margin_x, valid_margin_y)

                        for sub_region in non_fence_regions_ex:
                            delta_x = torch.zeros_like(delta_min)
                            delta_y = torch.zeros_like(delta_min)
                            xl, yl, xh, yh = sub_region

                            # on the left
                            mask_l = (pos_x_ex < xl).masked_fill_(valid_mask, 0)
                            # on the right
                            mask_r = (pos_xh_ex > xh).masked_fill_(valid_mask, 0)
                            # on the top
                            mask_t = (pos_yh_ex > yh).masked_fill_(valid_mask, 0)
                            # on the bottom
                            mask_b = (pos_y_ex < yl).masked_fill_(valid_mask, 0)

                            # x replacement for left cell
                            delta_x.masked_scatter_(mask_l, xl + margin_x - pos_x_ex[mask_l])
                            # x replacement for right cell
                            delta_x.masked_scatter_(mask_r, xh - margin_x - pos_xh_ex[mask_r])
                            # delta_x.masked_fill_(~(mask_l | mask_r), 0)
                            # y replacement for top cell
                            delta_y.masked_scatter_(mask_t, yh - margin_y - pos_yh_ex[mask_t])
                            # y replacement for bottom cell
                            delta_y.masked_scatter_(mask_b, yl + margin_y - pos_y_ex[mask_b])
                            # delta_y.masked_fill_(~(mask_t | mask_b), 0)
                            # update minimum replacement
                            delta_i = (delta_x ** 2 + delta_y ** 2)
                            update_mask = delta_i < delta_min

                            delta_x_min.masked_scatter_(update_mask, delta_x[update_mask])
                            delta_y_min.masked_scatter_(update_mask, delta_y[update_mask])
                            delta_min.masked_scatter_(update_mask, delta_i[update_mask])

                        # update the minimum replacement for subregions
                        pos_x.masked_scatter_(exclude_mask, pos_x_ex + delta_x_min)
                        pos_y.masked_scatter_(exclude_mask, pos_y_ex + delta_y_min)

                        ### write back solution
                        fillers = np.zeros(self.num_filler_nodes, dtype=placedb.dtype)
                        fmask = placedb.io_mask
                        fillMask = np.concatenate((fmask,fillers.astype(bool),fmask,fillers.astype(bool)),axis=0)
                        allLoc = np.concatenate((placedb.node_x, fillers, placedb.node_y, fillers),axis=0)
                        omask = ~fmask
                        allMask = ~fillMask
                        res = pos_g.data.clone()
                        res.data[:num_movable_nodes].copy_(pos_x)
                        res.data[num_nodes:num_nodes + num_movable_nodes].copy_(pos_y)
                        return res

                # in case of divergence, use the best metric
                ### always rollback to best outer cell overflow
                last_metric = all_metrics[-1][-1][-1]
                self.targetOverflow = torch.tensor(placedb.targetOverflow, dtype=torch.float, device=self.device)
                if last_metric.overflow.max() > max(self.targetOverflow.max(), best_metric[0].overflow.max()) and last_metric.hpwl > best_metric[0].hpwl:
                    self.pos[0].data.copy_(best_pos[0].data)
                    logging.error("possible DIVERGENCE detected, roll back to the best position recorded")
                    all_metrics.append([best_metric])
                    logging.info(best_metric[0])

                    #Legalize DSP/RAMs if any
                    if ((len(placedb.dsp_ram_compIds) > 0 and
                        placedb.num_movable_nodes_fence_region[placedb.dsp_ram_compIds].max() > 0) and
                        (model.lock_mask is not None and
                        model.lock_mask[placedb.dsp_ram_compIds].sum() != len(placedb.dsp_ram_compIds))):

                        for lgId in placedb.dsp_ram_rsrcIds:
                            if placedb.node_count[lgId] > 0:
                                movVal = dsp_ram_legalization.LegalizeDSPRAMFunction.legalize(pos, placedb, lgId, model)
                                logging.info("Legalized %s with maxMov = %g and avgMov = %g" % (placedb.rsrcTypes[lgId], movVal[0], movVal[1]))
                        model.lock_mask[placedb.dsp_ram_compIds] = True
                        model.update_mask = ~model.lock_mask

                #logging.info("optimizer %s takes %.3f seconds" % (optimizer_name, time.time()-tt))
            # recover node size and pin offset for legalization, since node size is adjusted in global placement
            if params.routability_opt_flag: 
                with torch.no_grad(): 
                    # convert lower left to centers 
                    # convert lower left to centers
                    #self.pos[0][:placedb.num_movable_nodes].add_(
                    #    self.data_collections.
                    #    node_size_x[:placedb.num_movable_nodes] / 2)
                    #self.pos[0][placedb.num_nodes:placedb.num_nodes +
                    #            placedb.num_movable_nodes].add_(
                    #                self.data_collections.
                    #                node_size_y[:placedb.num_movable_nodes] /
                    #                2)
                    self.data_collections.node_size_x.copy_(
                        self.data_collections.original_node_size_x)
                    self.data_collections.node_size_y.copy_(
                        self.data_collections.original_node_size_y)
                    ## use fixed centers as the anchor
                    #self.pos[0][:placedb.num_movable_nodes].sub_(
                    #    self.data_collections.
                    #    node_size_x[:placedb.num_movable_nodes] / 2)
                    #self.pos[0][placedb.num_nodes:placedb.num_nodes +
                    #            placedb.num_movable_nodes].sub_(
                    #                self.data_collections.
                    #                node_size_y[:placedb.num_movable_nodes] /
                    #                2)
                    self.data_collections.pin_offset_x.copy_(
                        self.data_collections.original_pin_offset_x)
                    self.data_collections.pin_offset_y.copy_(
                        self.data_collections.original_pin_offset_y)
        #else: 
        #    cur_metric = EvalMetricsFPGA(iteration)
        #    all_metrics.append(cur_metric)
        #    cur_metric.evaluate(placedb, {"hpwl" : self.op_collections.hpwl_op}, self.pos[0])
        #    logging.info(cur_metric)

        # dump global placement solution for legalization 
        if params.dump_global_place_solution_flag: 
            self.dump(params, placedb, self.pos[0].cpu(), "%s.lg.pklz" %(params.design_name()))

        half_pos = self.pos[0].shape[0]//2

        ## plot placement 
        #if params.plot_flag: 
        #    cur_pos = self.pos[0].data.clone().cpu().numpy()
        #    self.plot(params, placedb, 12345, cur_pos)

        if params.global_place_flag == 1 and placedb.num_ccNodes > 0:
            #Update sizes & GP location of cc nodes
            model.data_collections.org_node_size_x[placedb.new2org_node_map[:placedb.num_movable_nodes]] = model.data_collections.node_size_x[:placedb.num_movable_nodes]
            model.data_collections.org_node_size_y[placedb.new2org_node_map[:placedb.num_movable_nodes]] = model.data_collections.node_size_y[:placedb.num_movable_nodes]
            model.data_collections.org_node_size_x[placedb.org_num_movable_nodes:placedb.org_num_physical_nodes] = model.data_collections.node_size_x[placedb.num_movable_nodes:placedb.num_physical_nodes]
            model.data_collections.org_node_size_y[placedb.org_num_movable_nodes:placedb.org_num_physical_nodes] = model.data_collections.node_size_y[placedb.num_movable_nodes:placedb.num_physical_nodes]

            model.data_collections.org_node_x[placedb.new2org_node_map[:placedb.num_movable_nodes]] = self.pos[0][:placedb.num_movable_nodes].data
            model.data_collections.org_node_y[placedb.new2org_node_map[:placedb.num_movable_nodes]] = self.pos[0][half_pos:half_pos+placedb.num_movable_nodes].data
            model.data_collections.org_node_x[placedb.org_num_movable_nodes:placedb.org_num_physical_nodes] = self.pos[0][placedb.num_movable_nodes:placedb.num_physical_nodes].data
            model.data_collections.org_node_size_y[placedb.org_num_movable_nodes:placedb.org_num_physical_nodes] = self.pos[0][half_pos+placedb.num_movable_nodes:half_pos+placedb.num_physical_nodes]

            ccYLocIncr = 1/placedb.SLICE_CAPACITY
            for ccId in range(placedb.num_carry_chains):
                org_cc_indices = np.where(placedb.org_node2ccId_map == ccId)[0]
                curr_cc_index = placedb.cc2nodeId_map[ccId]
                elCount = placedb.cc_element_count[ccId]
                model.data_collections.org_node_size_x[org_cc_indices] = model.data_collections.node_size_x[curr_cc_index]
                model.data_collections.org_node_size_y[org_cc_indices] = model.data_collections.node_size_y[curr_cc_index]/elCount
                model.data_collections.org_node_x[org_cc_indices] = self.pos[0][curr_cc_index].data
                yoffset = torch.arange(elCount-1, -1, -1, dtype=self.data_collections.dtype, device=self.device)*ccYLocIncr
                model.data_collections.org_node_y[org_cc_indices] = self.pos[0][half_pos:][curr_cc_index].data + yoffset
                #print("Updated Carry chain %d at (%.2f, %.2f) => org (%.2f, %.2f)"%
                #    (ccId, self.pos[0][curr_cc_index].data, self.pos[0][half_pos:][curr_cc_index].data,
                #    model.data_collections.org_node_x[org_cc_indices[0]],
                #    model.data_collections.org_node_y[org_cc_indices[0]]))

            model.data_collections.org_node_areas = model.data_collections.org_node_size_x * model.data_collections.org_node_size_y
            placedb.num_movable_nodes = placedb.org_num_movable_nodes
            placedb.num_physical_nodes = placedb.org_num_physical_nodes
            self.pos[0][:placedb.num_physical_nodes].data.copy_(self.data_collections.org_node_x)
            self.pos[0][half_pos:half_pos+placedb.num_physical_nodes].data.copy_(self.data_collections.org_node_y)

        ## plot placement 
        #if params.plot_flag: 
        #    cur_pos = self.pos[0].data.clone().cpu().numpy()
        #    self.plot(params, placedb, 5678, cur_pos)

        # legalization 
        if params.legalize_flag:
            if params.global_place_flag == 0:
                #Load from GP results
                for global_place_params in params.global_place_stages:

                    if params.gpu: 
                        torch.cuda.synchronize()
                    tt = time.time()
                    # construct model and optimizer 
                    density_weight = 0.0
                    # construct placement model 
                    model = PlaceObjFPGA(density_weight, params, placedb, self.data_collections, self.op_collections, global_place_params).to(self.data_collections.pos[0].device)
                    print("Model constructed in %g ms"%((time.time()-tt)*1000))

                place_file=params.global_place_sol
                #logging.info("Reading %s" % (place_file))
                with open (place_file,  "r") as f:
                    for line in f:
                        tokens = line.split()
                        if len(tokens) > 0:
                            if tokens[0] in placedb.node_name2id_map:
                                nodeId = placedb.node_name2id_map[tokens[0]]
                                self.data_collections.node_x[nodeId].data.fill_(placedb.dtype(tokens[1]))
                                self.data_collections.node_y[nodeId].data.fill_(placedb.dtype(tokens[2]))
                                self.data_collections.node_z[nodeId].data.fill_(int(tokens[3]))
                                if placedb.num_ccNodes:
                                    nodeId = placedb.org_node_name2id_map[tokens[0]]
                                    self.data_collections.org_node_x[nodeId].data.fill_(placedb.dtype(tokens[1]))
                                    self.data_collections.org_node_y[nodeId].data.fill_(placedb.dtype(tokens[2]))
                                    self.data_collections.org_node_z[nodeId].data.fill_(int(tokens[3]))
                self.pos[0][:placedb.num_physical_nodes].data.copy_(self.data_collections.node_x)
                self.pos[0][half_pos:half_pos+placedb.num_physical_nodes].data.copy_(self.data_collections.node_y)
                logging.info("Read Global Placement solution from %s" % (place_file))
                cur_metric = EvalMetricsFPGA(iteration)
                all_metrics.append(cur_metric)
                cur_metric.evaluate(placedb, {"hpwl" : self.op_collections.hpwl_op}, self.pos[0])
                logging.info(cur_metric)
                iteration += 1

            #Break carry chain nodes as single entity
            if placedb.num_ccNodes > 0:
                placedb.num_movable_nodes = placedb.org_num_movable_nodes
                placedb.num_physical_nodes = placedb.org_num_physical_nodes
                self.pos[0][:placedb.num_physical_nodes].data.copy_(self.data_collections.org_node_x)
                self.pos[0][half_pos:half_pos+placedb.num_physical_nodes].data.copy_(self.data_collections.org_node_y)
                node_areas = self.data_collections.org_node_areas
                lut_mask = placedb.org_lut_mask
                flop_mask = placedb.org_flop_mask
                lut_flop_mask = placedb.org_lut_flop_mask
                node_z = self.data_collections.org_node_z
            else: 
                node_areas = self.data_collections.node_areas
                lut_mask = placedb.lut_mask
                flop_mask = placedb.flop_mask
                lut_flop_mask = placedb.lut_flop_mask
                node_z = self.data_collections.node_z

            #Perform sorting of pin, net, node
            _, sortedNetIdx = torch.sort(self.data_collections.net2pincount_map)
            sortedNetIdx = sortedNetIdx.to(torch.int32)
            _, sortedNetMap = torch.sort(sortedNetIdx)
            sortedNetMap = sortedNetMap.to(torch.int32)

            _, sortedPinIdx = torch.sort(sortedNetMap[self.data_collections.pin2net_map.to(torch.long)])
            sortedPinIdx = sortedPinIdx.to(torch.int32)
            _, sortedPinMap = torch.sort(sortedPinIdx)
            sortedPinMap = sortedPinMap.to(torch.int32)

            node2pinId0 = self.op_collections.sort_node2pin_op(sortedPinMap)
            #node2pinId0 = torch.zeros(placedb.num_physical_nodes, dtype=torch.int32)
            #for el in range(placedb.num_physical_nodes):
            #    startId = data_collections.flat_node2pin_start_map[el]
            #    endId = data_collections.flat_node2pin_start_map[el+1]
            #    _, sorted_node2pin_idx = torch.sort(sorted_pin_map[data_collections.flat_node2pin_map.to(torch.long)[startId:endId]]) 
            #    data_collections.flat_node2pin_map[startId:endId].data.copy_(data_collections.flat_node2pin_map[startId:endId][sorted_node2pin_idx].data)
            #    node2pinId0[el] = sorted_pin_map[data_collections.flat_node2pin_map[startId]]

            _, sortedNodeIdx = torch.sort(node2pinId0)
            sortedNodeIdx = sortedNodeIdx.to(torch.int32)

            _, sortedNodeMap = torch.sort(sortedNodeIdx)
            sortedNodeMap = sortedNodeMap.to(torch.int32)

            tt = time.time()

            if placedb.num_ccNodes == 0:
                preconditioner = model.precondWL[:placedb.num_physical_nodes]
            else:
                preconditioner = model.lg_precondWL[:placedb.num_physical_nodes]
            
            self.op_collections.lut_ff_legalization_op.initialize(self.pos[0], preconditioner, sortedNodeMap, sortedNodeIdx, sortedNetMap, sortedNetIdx, sortedPinMap)

            DLStatus = 1
            dlIter = 0

            #For runDLIter stopping criteria
            MAX_DL_ITERS=100
            MIN_DL_ITERS=50
            ITERS_INCREASE=50
            STOP_ITERS=150
            STABLE_ITER_COUNT=5
            REM_INSTANCE_RATIO=0.09
            activeStatus = torch.zeros(placedb.num_sites_x*placedb.num_sites_y, dtype=torch.int, device=self.device)
            illegalStatus = torch.zeros(placedb.num_physical_nodes, dtype=torch.int, device=self.device)

            iter_stable = 0
            prevAct = 0

            while (DLStatus == 1):
                self.op_collections.lut_ff_legalization_op.runDLIter(self.pos[0], preconditioner, sortedNodeMap, sortedNodeIdx, sortedNetMap, sortedNetIdx, sortedPinMap, activeStatus, illegalStatus, dlIter)

                if prevAct == illegalStatus.sum().item() + activeStatus.sum().item():
                    iter_stable = iter_stable + 1
                else:
                    iter_stable = 0

                dlIter = dlIter+1
                if activeStatus.sum().item() > 0:
                    DLStatus = 1
                elif illegalStatus.sum().item() > 0:
                    DLStatus = -1
                else:
                    DLStatus = 0

                prevAct=illegalStatus.sum().item() + activeStatus.sum().item()

                if dlIter > STOP_ITERS or (dlIter > MIN_DL_ITERS and iter_stable > STABLE_ITER_COUNT):
                    DLStatus = 0

                if dlIter > MAX_DL_ITERS and iter_stable < STABLE_ITER_COUNT:
                    if illegalStatus.sum().item() < REM_INSTANCE_RATIO*placedb.num_physical_nodes:
                        DLStatus = 0
                    else:
                        MAX_DL_ITERS += ITERS_INCREASE

            #Use inflated instance areas for ripUP & greedy LG
            avgLUTArea = node_areas[:placedb.num_physical_nodes][lut_mask].sum()
            avgLUTArea /= placedb.node_count[placedb.rLUTIdx]
            avgFFArea = node_areas[:placedb.num_physical_nodes][flop_mask].sum()
            avgFFArea /= placedb.node_count[placedb.rFFIdx]
            #Inst Areas
            inst_areas = node_areas[:placedb.num_physical_nodes].detach().clone()
            inst_areas[~lut_flop_mask] = 0.0 #Area of non SLICE nodes set to 0.0
            inst_areas[lut_mask] /= avgLUTArea
            inst_areas[flop_mask] /= avgFFArea

            self.pos[0].data.copy_(self.op_collections.lut_ff_legalization_op.ripUP_Greedy_slotAssign(self.pos[0], preconditioner, node_z[:placedb.num_movable_nodes], sortedNodeMap, sortedNodeIdx, sortedNetMap, sortedNetIdx, sortedPinMap, inst_areas))

            #Terminate if legalization has errors
            if (self.pos[0] == -1).sum().item() > 0:
                sys.exit("[ERROR] " + str((self.pos[0] == -1).sum().item()) + " instances were not legalized - Please ensure there is sufficient space in sitemap and/or revisit LG algorithm")

            logging.info("legalization takes %.3f seconds" % (time.time()-tt))
            cur_metric = EvalMetricsFPGA(iteration)
            all_metrics.append(cur_metric)
            cur_metric.evaluate(placedb, {"hpwl" : self.op_collections.hpwl_op}, self.pos[0])
            logging.info(cur_metric)
            iteration += 1

        # recover node size and pin offset for plot, since node size is adjusted in global placement
        if params.routability_opt_flag: 
            with torch.no_grad(): 
                # convert lower left to centers 
                # convert lower left to centers
                #self.pos[0][:placedb.num_movable_nodes].add_(
                #    self.data_collections.
                #    node_size_x[:placedb.num_movable_nodes] / 2)
                #self.pos[0][placedb.num_nodes:placedb.num_nodes +
                #            placedb.num_movable_nodes].add_(
                #                self.data_collections.
                #                node_size_y[:placedb.num_movable_nodes] /
                #                2)
                self.data_collections.node_size_x.copy_(
                    self.data_collections.original_node_size_x)
                self.data_collections.node_size_y.copy_(
                    self.data_collections.original_node_size_y)
                ## use fixed centers as the anchor
                #self.pos[0][:placedb.num_movable_nodes].sub_(
                #    self.data_collections.
                #    node_size_x[:placedb.num_movable_nodes] / 2)
                #self.pos[0][placedb.num_nodes:placedb.num_nodes +
                #            placedb.num_movable_nodes].sub_(
                #                self.data_collections.
                #                node_size_y[:placedb.num_movable_nodes] /
                #                2)
                self.data_collections.pin_offset_x.copy_(
                    self.data_collections.original_pin_offset_x)
                self.data_collections.pin_offset_y.copy_(
                    self.data_collections.original_pin_offset_y)

        # plot placement 
        #if params.plot_flag: 
        #    self.plot(params, placedb, iteration, self.pos[0].data.clone().cpu().numpy())

        # dump legalization solution for detailed placement 
        if params.dump_legalize_solution_flag: 
            self.dump(params, placedb, self.pos[0].cpu(), "%s.dp.pklz" %(params.design_name()))

        # detailed placement
        if params.detailed_place_flag: 
            place_file=params.lg_place_sol
            if params.global_place_flag == 0 and params.legalize_flag == 0 and place_file != "":
                #Load legal placement results from file
                for global_place_params in params.global_place_stages:

                    if params.gpu: 
                        torch.cuda.synchronize()
                    tt = time.time()
                    # construct model and optimizer 
                    density_weight = 0.0
                    # construct placement model 
                    model = PlaceObjFPGA(density_weight, params, placedb, self.data_collections, self.op_collections, global_place_params).to(self.data_collections.pos[0].device)
                    print("Model constructed in %g ms"%((time.time()-tt)*1000))

                with open (place_file,  "r") as f:
                    for line in f:
                        tokens = line.split()
                        if len(tokens) > 0:
                            nodeId = placedb.node_name2id_map[tokens[0]]
                            self.data_collections.node_x[nodeId].data.fill_(float(tokens[1]))
                            self.data_collections.node_y[nodeId].data.fill_(float(tokens[2]))
                            self.data_collections.node_z[nodeId].data.fill_(int(tokens[3]))
                self.pos[0][:placedb.num_physical_nodes].data.copy_(self.data_collections.node_x)
                self.pos[0][half_pos:half_pos+placedb.num_physical_nodes].data.copy_(self.data_collections.node_y)

                ##Update locations for all instances from placement solution
                logging.info("Read Legalized Placement solution from %s" % (place_file))
                cur_metric = EvalMetricsFPGA(iteration)
                all_metrics.append(cur_metric)
                cur_metric.evaluate(placedb, {"hpwl" : self.op_collections.hpwl_op}, self.pos[0])
                logging.info(cur_metric)
                iteration += 1

        ## detailed placement 
        #if params.detailed_place_flag: 
        #    tt = time.time()
        #    self.pos[0].data.copy_(self.op_collections.detailed_place_op(self.pos[0]))
        #    logging.info("detailed placement takes %.3f seconds" % (time.time()-tt))
        #    cur_metric = EvalMetricsFPGA(iteration)
        #    all_metrics.append(cur_metric)
        #    cur_metric.evaluate(placedb, {"hpwl" : self.op_collections.hpwl_op}, self.pos[0])
        #    logging.info(cur_metric)
        #    iteration += 1

        if placedb.num_ccNodes:
            node_z = self.data_collections.org_node_z
        else: 
            node_z = self.data_collections.node_z
        half_pos = self.pos[0].shape[0]//2

        # save results 
        cur_pos = self.pos[0].data.clone().cpu().numpy()
        node_z = node_z[:placedb.num_movable_nodes].data.clone().cpu().numpy() 
        # apply solution 
        placedb.apply(
            cur_pos[0:placedb.num_movable_nodes],
            cur_pos[half_pos:half_pos + placedb.num_movable_nodes],
            node_z)

        # plot placement 
        if params.plot_flag: 
            self.plot(params, placedb, iteration, cur_pos)

        return all_metrics 


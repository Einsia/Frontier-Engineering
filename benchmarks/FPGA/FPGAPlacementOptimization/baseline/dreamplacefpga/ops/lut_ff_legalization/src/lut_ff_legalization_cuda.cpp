/**
 * @file   lut_ff_legalization_cuda.cpp
 * @author Rachel Selina
 * @date   Mar 2021 (DREAMPlaceFPGA-PL)
 * @brief  Legalize LUT/FF
 */

#include "utility/src/torch.h"
#include "utility/src/utils.h"

DREAMPLACE_BEGIN_NAMESPACE
// Initialize
template <typename T>
int initLGCudaLauncher(
        const T *pos_x,
        const T *pos_y,
        const T *pin_offset_x,
        const T *pin_offset_y,
        const int *sorted_node_map,
        const int *sorted_node_idx,
        const int *sorted_net_idx,
        const int *flat_net2pin_map,
        const int *flat_net2pin_start_map,
        const int *flop2ctrlSetId_map,
        const int *flop_ctrlSets,
        const int *node2fence_region_map,
        const int *node2outpinIdx_map,
        const int *pin2net_map,
        const int *pin2node_map,
        const int *pin_typeIds,
        const int *net2pincount,
        const int *is_mlab_node,
        const T preClusteringMaxDist,
        const int ffId,
        const int lutId,
        const int num_nets,
        const int num_nodes,
        const int wlscoreMaxNetDegree,
        T *net_bbox,
        int *net_pinIdArrayX,
        int *net_pinIdArrayY,
        int *flat_node2precluster_map,
        int *flat_node2prclstrCount);

//runDLIter
template <typename T>
int runDLCudaLauncher(
        const T* pos_x,
        const T* pos_y,
        const T* pin_offset_x,
        const T* pin_offset_y,
        const T* net_bbox,
        const T* site_xy,
        const T* net_weights,
        const int* net_pinIdArrayX,
        const int* net_pinIdArrayY,
        const int* site_types,
        const int* spiral_accessor,
        const int* node2fence_region_map,
        const int* lut_flop_indices,
        const int* flop2ctrlSetId_map,
        const int* flop_ctrlSets,
        const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map,
        const int* lut_type,
        const int* flat_node2pin_start_map,
        const int* flat_node2pin_map,
        const int* node2outpinIdx_map,
        const int* node2pincount,
        const int* net2pincount,
        const int* pin2net_map,
        const int* pin_typeIds,
        const int* flat_net2pin_start_map,
        const int* pin2node_map,
        const int* sorted_net_map,
        const int* sorted_node_map,
        const int* flat_node2prclstrCount,
        const int* flat_node2precluster_map,
        const int* is_mlab_node,
        const int* site_nbrList,
        const int* site_nbrRanges,
        const int* site_nbrRanges_idx,
        const int* addr2site_map,
        const int* site2addr_map,
        const int* special_nodes,
        const T maxDist,
        const T xWirelenWt,
        const T yWirelenWt,
        const T wirelenImprovWt,
        const T extNetCountWt,
        const int num_sites_x,
        const int num_sites_y,
        const int num_clb_sites,
        const int num_lutflops,
        const int minStableIter,
        const int maxList,
        const int half_ctrl_mode,
        const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY,
        const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE,
        const int minNeighbors,
        const int spiralBegin,
        const int spiralEnd,
        const int intMinVal,
        const int numGroups,
        const int netShareScoreMaxNetDegree,
        const int wlscoreMaxNetDegree,
        const int lutTypeInSliceUnit,
        const int lut_maxShared,
        const int CKSR_IN_CLB,
        const int CE_IN_CLB,
        const int SCL_IDX,
        const int PQ_IDX,
        const int SIG_IDX,
        const int lutId,
        const int ffId,
        const int sliceId,
        int* site_nbr_idx,
        int* site_nbr,
        int* site_nbrGroup_idx,
        int* site_curr_pq_top_idx,
        int* site_curr_pq_sig_idx,
        int* site_curr_pq_sig,
        int* site_curr_pq_idx,
        int* site_curr_stable,
        int* site_curr_pq_siteId,
        int* site_curr_pq_validIdx,
        T* site_curr_pq_score,
        int* site_curr_pq_impl_lut,
        int* site_curr_pq_impl_ff,
        int* site_curr_pq_impl_cksr,
        int* site_curr_pq_impl_ce,
        T* site_curr_scl_score,
        int* site_curr_scl_siteId,
        int* site_curr_scl_idx,
        int* cumsum_curr_scl,
        int* site_curr_scl_validIdx,
        int* validIndices_curr_scl,
        int* site_curr_scl_sig_idx,
        int* site_curr_scl_sig,
        int* site_curr_scl_impl_lut,
        int* site_curr_scl_impl_ff,
        int* site_curr_scl_impl_cksr,
        int* site_curr_scl_impl_ce,
        int* site_next_pq_idx,
        int* site_next_pq_validIdx,
        int* site_next_pq_top_idx,
        T* site_next_pq_score,
        int* site_next_pq_siteId,
        int* site_next_pq_sig_idx,
        int* site_next_pq_sig,
        int* site_next_pq_impl_lut,
        int* site_next_pq_impl_ff,
        int* site_next_pq_impl_cksr,
        int* site_next_pq_impl_ce,
        T* site_next_scl_score,
        int* site_next_scl_siteId,
        int* site_next_scl_idx,
        int* site_next_scl_validIdx,
        int* site_next_scl_sig_idx,
        int* site_next_scl_sig,
        int* site_next_scl_impl_lut,
        int* site_next_scl_impl_ff,
        int* site_next_scl_impl_cksr,
        int* site_next_scl_impl_ce,
        int* site_next_stable,
        T* site_det_score,
        int* site_det_siteId,
        int* site_det_sig_idx,
        int* site_det_sig,
        int* site_det_impl_lut,
        int* site_det_impl_ff,
        int* site_det_impl_cksr,
        int* site_det_impl_ce,
        int* inst_curr_detSite,
        T* inst_curr_bestScoreImprov,
        int* inst_curr_bestSite,
        int* inst_next_detSite,
        T* inst_next_bestScoreImprov,
        int* inst_next_bestSite,
        int* activeStatus,
        int* illegalStatus,
        int* inst_score_improv,
        int* site_score_improv,
        int* sorted_clb_siteIds);

//legalize Mlab
template <typename T>
int legalizeMlabCudaLauncher(
        const T* pos_x,
        const T* pos_y,
        const T* site_xy,
        const T* mlab_locX,
        const T* mlab_locY,
        const int* mlab_indices,
        const int* site2addr_map,
        const int num_mlab_nodes,
        const int num_sites_y,
        const int SIG_IDX,
        const int SLICE_CAPACITY,
        T* dist_moved,
        T* site_det_score,
        T* inst_curr_bestScoreImprov,
        T* inst_next_bestScoreImprov,
        int* site_det_siteId,
        int* site_det_sig_idx,
        int* site_det_sig,
        int* site_det_impl_lut,
        int* inst_curr_detSite,
        int* inst_curr_bestSite,
        int* inst_next_detSite,
        int* inst_next_bestSite,
        int* sites_with_special_nodes);

#define CHECK_FLAT(x) AT_ASSERTM(x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on GPU")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel() & 1) == 0, #x "must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

void initLegalization(
              at::Tensor pos,
              at::Tensor pin_offset_x,
              at::Tensor pin_offset_y,
              at::Tensor sorted_net_idx,
              at::Tensor sorted_node_map,
              at::Tensor sorted_node_idx,
              at::Tensor flat_net2pin_map,
              at::Tensor flat_net2pin_start_map,
              at::Tensor flop2ctrlSetId_map,
              at::Tensor flop_ctrlSets,
              at::Tensor node2fence_region_map,
              at::Tensor node2outpinIdx_map,
              at::Tensor pin2net_map,
              at::Tensor pin2node_map,
              at::Tensor pin_typeIds,
              at::Tensor net2pincount,
              at::Tensor is_mlab_node,
              double preClusteringMaxDist,
              int num_nets,
              int num_nodes,
              int lutId,
              int ffId,
              int wlscoreMaxNetDegree,
              at::Tensor net_bbox,
              at::Tensor net_pinIdArrayX,
              at::Tensor net_pinIdArrayY,
              at::Tensor flat_node2precluster_map,
              at::Tensor flat_node2prclstrCount)
{
    CHECK_FLAT(pos);
    CHECK_EVEN(pos);
    CHECK_CONTIGUOUS(pos);

    CHECK_FLAT(pin_offset_x);
    CHECK_CONTIGUOUS(pin_offset_x);
    CHECK_FLAT(pin_offset_y);
    CHECK_CONTIGUOUS(pin_offset_y);

    CHECK_FLAT(sorted_net_idx);
    CHECK_CONTIGUOUS(sorted_net_idx);

    CHECK_FLAT(sorted_node_map);
    CHECK_CONTIGUOUS(sorted_node_map);
    CHECK_FLAT(sorted_node_idx);
    CHECK_CONTIGUOUS(sorted_node_idx);

    CHECK_FLAT(flat_net2pin_map);
    CHECK_CONTIGUOUS(flat_net2pin_map);
    CHECK_FLAT(flat_net2pin_start_map);
    CHECK_CONTIGUOUS(flat_net2pin_start_map);

    CHECK_FLAT(flop2ctrlSetId_map);
    CHECK_CONTIGUOUS(flop2ctrlSetId_map);
    CHECK_FLAT(flop_ctrlSets);
    CHECK_CONTIGUOUS(flop_ctrlSets);

    CHECK_FLAT(node2fence_region_map);
    CHECK_CONTIGUOUS(node2fence_region_map);
    CHECK_FLAT(node2outpinIdx_map);
    CHECK_CONTIGUOUS(node2outpinIdx_map);

    CHECK_FLAT(pin2net_map);
    CHECK_CONTIGUOUS(pin2net_map);
    CHECK_FLAT(pin2node_map);
    CHECK_CONTIGUOUS(pin2node_map);
    CHECK_FLAT(pin_typeIds);
    CHECK_CONTIGUOUS(pin_typeIds);

    CHECK_FLAT(net2pincount);
    CHECK_CONTIGUOUS(net2pincount);

    int numNodes = pos.numel() / 2;

    // Call the cuda kernel launcher
    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "initLGCudaLauncher", [&] {
        initLGCudaLauncher<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
            DREAMPLACE_TENSOR_DATA_PTR(pin_offset_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(pin_offset_y, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(sorted_node_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(sorted_node_idx, int),
            DREAMPLACE_TENSOR_DATA_PTR(sorted_net_idx, int),
            DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_start_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(flop2ctrlSetId_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(flop_ctrlSets, int),
            DREAMPLACE_TENSOR_DATA_PTR(node2fence_region_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(node2outpinIdx_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(pin2net_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(pin2node_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(pin_typeIds, int),
            DREAMPLACE_TENSOR_DATA_PTR(net2pincount, int),
            DREAMPLACE_TENSOR_DATA_PTR(is_mlab_node, int),
            preClusteringMaxDist, ffId, lutId,
            num_nets, num_nodes, wlscoreMaxNetDegree,
            DREAMPLACE_TENSOR_DATA_PTR(net_bbox, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayX, int),
            DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayY, int),
            DREAMPLACE_TENSOR_DATA_PTR(flat_node2precluster_map, int),
            DREAMPLACE_TENSOR_DATA_PTR(flat_node2prclstrCount, int));
    });


}

//RunDLIteration
void runDLIter(
        at::Tensor pos,
        at::Tensor pin_offset_x,
        at::Tensor pin_offset_y,
        at::Tensor net_bbox,
        at::Tensor site_xy,
        at::Tensor net_weights,
        at::Tensor net_pinIdArrayX,
        at::Tensor net_pinIdArrayY,
        at::Tensor site_types,
        at::Tensor spiral_accessor,
        at::Tensor node2fence_region_map,
        at::Tensor lut_flop_indices,
        at::Tensor flop2ctrlSetId_map,
        at::Tensor flop_ctrlSets,
        at::Tensor extended_ctrlSets,
        at::Tensor ext_ctrlSet_start_map,
        at::Tensor lut_type,
        at::Tensor flat_node2pin_start_map,
        at::Tensor flat_node2pin_map,
        at::Tensor node2outpinIdx_map,
        at::Tensor node2pincount,
        at::Tensor net2pincount,
        at::Tensor pin2net_map,
        at::Tensor pin_typeIds,
        at::Tensor flat_net2pin_start_map,
        at::Tensor pin2node_map,
        at::Tensor sorted_net_map,
        at::Tensor sorted_node_map,
        at::Tensor flat_node2prclstrCount,
        at::Tensor flat_node2precluster_map,
        at::Tensor is_mlab_node,
        at::Tensor site_nbrList,
        at::Tensor site_nbrRanges,
        at::Tensor site_nbrRanges_idx,
        at::Tensor addr2site_map,
        at::Tensor site2addr_map,
        at::Tensor special_nodes,
        double maxDist,
        double xWirelenWt,
        double yWirelenWt,
        double wirelenImprovWt,
        double extNetCountWt,
        int num_sites_x,
        int num_sites_y,
        int num_clb_sites,
        int num_lutflops,
        int minStableIter,
        int maxList,
        int half_ctrl_mode,
        int SLICE_CAPACITY,
        int HALF_SLICE_CAPACITY,
        int BLE_CAPACITY,
        int NUM_BLE_PER_SLICE,
        int minNeighbors,
        int spiralBegin,
        int spiralEnd,
        int intMinVal,
        int numGroups,
        int netShareScoreMaxNetDegree,
        int wlscoreMaxNetDegree,
        int lutTypeInSliceUnit,
        int lut_maxShared,
        int CKSR_IN_CLB,
        int CE_IN_CLB,
        int SCL_IDX,
        int PQ_IDX,
        int SIG_IDX,
        int lutId,
        int ffId,
        int sliceId,
        at::Tensor site_nbr_idx,
        at::Tensor site_nbr,
        at::Tensor site_nbrGroup_idx,
        at::Tensor site_curr_pq_top_idx,
        at::Tensor site_curr_pq_sig_idx,
        at::Tensor site_curr_pq_sig,
        at::Tensor site_curr_pq_idx,
        at::Tensor site_curr_stable,
        at::Tensor site_curr_pq_siteId,
        at::Tensor site_curr_pq_validIdx,
        at::Tensor site_curr_pq_score,
        at::Tensor site_curr_pq_impl_lut,
        at::Tensor site_curr_pq_impl_ff,
        at::Tensor site_curr_pq_impl_cksr,
        at::Tensor site_curr_pq_impl_ce,
        at::Tensor site_curr_scl_score,
        at::Tensor site_curr_scl_siteId,
        at::Tensor site_curr_scl_idx,
        at::Tensor cumsum_curr_scl,
        at::Tensor site_curr_scl_validIdx,
        at::Tensor validIndices_curr_scl,
        at::Tensor site_curr_scl_sig_idx,
        at::Tensor site_curr_scl_sig,
        at::Tensor site_curr_scl_impl_lut,
        at::Tensor site_curr_scl_impl_ff,
        at::Tensor site_curr_scl_impl_cksr,
        at::Tensor site_curr_scl_impl_ce,
        at::Tensor site_next_pq_idx,
        at::Tensor site_next_pq_validIdx,
        at::Tensor site_next_pq_top_idx,
        at::Tensor site_next_pq_score,
        at::Tensor site_next_pq_siteId,
        at::Tensor site_next_pq_sig_idx,
        at::Tensor site_next_pq_sig,
        at::Tensor site_next_pq_impl_lut,
        at::Tensor site_next_pq_impl_ff,
        at::Tensor site_next_pq_impl_cksr,
        at::Tensor site_next_pq_impl_ce,
        at::Tensor site_next_scl_score,
        at::Tensor site_next_scl_siteId,
        at::Tensor site_next_scl_idx,
        at::Tensor site_next_scl_validIdx,
        at::Tensor site_next_scl_sig_idx,
        at::Tensor site_next_scl_sig,
        at::Tensor site_next_scl_impl_lut,
        at::Tensor site_next_scl_impl_ff,
        at::Tensor site_next_scl_impl_cksr,
        at::Tensor site_next_scl_impl_ce,
        at::Tensor site_next_stable,
        at::Tensor site_det_score,
        at::Tensor site_det_siteId,
        at::Tensor site_det_sig_idx,
        at::Tensor site_det_sig,
        at::Tensor site_det_impl_lut,
        at::Tensor site_det_impl_ff,
        at::Tensor site_det_impl_cksr,
        at::Tensor site_det_impl_ce,
        at::Tensor inst_curr_detSite,
        at::Tensor inst_curr_bestScoreImprov,
        at::Tensor inst_curr_bestSite,
        at::Tensor inst_next_detSite,
        at::Tensor inst_next_bestScoreImprov,
        at::Tensor inst_next_bestSite,
        at::Tensor activeStatus,
        at::Tensor illegalStatus,
        at::Tensor inst_score_improv,
        at::Tensor site_score_improv,
        at::Tensor sorted_clb_siteIds)
{
    CHECK_FLAT(pos);
    CHECK_EVEN(pos);
    CHECK_CONTIGUOUS(pos);

    CHECK_FLAT(pin_offset_x);
    CHECK_CONTIGUOUS(pin_offset_x);
    CHECK_FLAT(pin_offset_y);
    CHECK_CONTIGUOUS(pin_offset_y);

    CHECK_FLAT(net_bbox);
    CHECK_CONTIGUOUS(net_bbox);

    CHECK_FLAT(net_pinIdArrayX);
    CHECK_CONTIGUOUS(net_pinIdArrayX);
    CHECK_FLAT(net_pinIdArrayY);
    CHECK_CONTIGUOUS(net_pinIdArrayY);

    CHECK_FLAT(site_xy);
    CHECK_CONTIGUOUS(site_xy);
    CHECK_FLAT(spiral_accessor);
    CHECK_CONTIGUOUS(spiral_accessor);
    CHECK_FLAT(site_types);
    CHECK_CONTIGUOUS(site_types);

    CHECK_FLAT(node2fence_region_map);
    CHECK_CONTIGUOUS(node2fence_region_map);

    CHECK_FLAT(lut_flop_indices);
    CHECK_CONTIGUOUS(lut_flop_indices);

    CHECK_FLAT(flop_ctrlSets);
    CHECK_CONTIGUOUS(flop_ctrlSets);
    CHECK_FLAT(flop2ctrlSetId_map);
    CHECK_CONTIGUOUS(flop2ctrlSetId_map);

    CHECK_FLAT(lut_type);
    CHECK_CONTIGUOUS(lut_type);

    CHECK_FLAT(flat_node2pin_start_map);
    CHECK_CONTIGUOUS(flat_node2pin_start_map);
    CHECK_FLAT(flat_node2pin_map);
    CHECK_CONTIGUOUS(flat_node2pin_map);

    CHECK_FLAT(node2pincount);
    CHECK_CONTIGUOUS(node2pincount);

    CHECK_FLAT(net2pincount);
    CHECK_CONTIGUOUS(net2pincount);

    CHECK_FLAT(pin2net_map);
    CHECK_CONTIGUOUS(pin2net_map);
    CHECK_FLAT(pin_typeIds);
    CHECK_CONTIGUOUS(pin_typeIds);

    CHECK_FLAT(flat_net2pin_start_map);
    CHECK_CONTIGUOUS(flat_net2pin_start_map);

    CHECK_FLAT(pin2node_map);
    CHECK_CONTIGUOUS(pin2node_map);

    CHECK_FLAT(sorted_net_map);
    CHECK_CONTIGUOUS(sorted_net_map);
    CHECK_FLAT(sorted_node_map);
    CHECK_CONTIGUOUS(sorted_node_map);

    CHECK_FLAT(flat_node2prclstrCount);
    CHECK_CONTIGUOUS(flat_node2prclstrCount);
    CHECK_FLAT(flat_node2precluster_map);
    CHECK_CONTIGUOUS(flat_node2precluster_map);

    CHECK_FLAT(site_nbrList);
    CHECK_CONTIGUOUS(site_nbrList);
    CHECK_FLAT(site_nbrRanges);
    CHECK_CONTIGUOUS(site_nbrRanges);
    CHECK_FLAT(site_nbrRanges_idx);
    CHECK_CONTIGUOUS(site_nbrRanges_idx);

    CHECK_FLAT(net_weights);
    CHECK_CONTIGUOUS(net_weights);

    CHECK_FLAT(addr2site_map);
    CHECK_CONTIGUOUS(addr2site_map);
    CHECK_FLAT(site2addr_map);
    CHECK_CONTIGUOUS(site2addr_map);

    int numNodes = pos.numel() / 2;

    // Call the cuda kernel launcher
    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "runDLCudaLauncher", [&] {
        runDLCudaLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_x, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_y, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_bbox, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_weights, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayX, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayY, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_types, int),
                    DREAMPLACE_TENSOR_DATA_PTR(spiral_accessor, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2fence_region_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(lut_flop_indices, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop2ctrlSetId_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop_ctrlSets, int),
                    DREAMPLACE_TENSOR_DATA_PTR(extended_ctrlSets, int),
                    DREAMPLACE_TENSOR_DATA_PTR(ext_ctrlSet_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(lut_type, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2outpinIdx_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2pincount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net2pincount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2net_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_typeIds, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_net_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2prclstrCount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2precluster_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(is_mlab_node, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrList, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrRanges, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrRanges_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(addr2site_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site2addr_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(special_nodes, int),
                    maxDist, xWirelenWt, yWirelenWt, wirelenImprovWt, extNetCountWt, 
                    num_sites_x, num_sites_y, num_clb_sites, num_lutflops,
                    minStableIter, maxList, half_ctrl_mode, SLICE_CAPACITY, 
                    HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE, minNeighbors, 
                    spiralBegin, spiralEnd, intMinVal,
                    numGroups, netShareScoreMaxNetDegree, wlscoreMaxNetDegree,
                    lutTypeInSliceUnit, lut_maxShared, CKSR_IN_CLB,
                    CE_IN_CLB, SCL_IDX, PQ_IDX, SIG_IDX, lutId, ffId, sliceId,
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbr_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrGroup_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_top_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_stable, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_validIdx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_cksr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_ce, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(cumsum_curr_scl, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_validIdx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(validIndices_curr_scl, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_impl_cksr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_impl_ce, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_validIdx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_top_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_impl_cksr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_pq_impl_ce, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_validIdx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_impl_cksr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_scl_impl_ce, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_next_stable, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_cksr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_ce, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_detSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_bestScoreImprov, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_bestSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_detSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_bestScoreImprov, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_bestSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(activeStatus, int),
                    DREAMPLACE_TENSOR_DATA_PTR(illegalStatus, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_score_improv, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_score_improv, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_clb_siteIds, int)
                    );
                });
    //std::cout << "Run DL Iter "<< std::endl;
}

//Legalize Mlabs
void legalizeMlab(
        at::Tensor pos,
        at::Tensor site_xy,
        at::Tensor mlab_locX,
        at::Tensor mlab_locY,
        at::Tensor mlab_indices,
        at::Tensor site2addr_map,
        int num_mlab_nodes,
        int num_sites_y,
        int SIG_IDX,
        int SLICE_CAPACITY,
        at::Tensor dist_moved,
        at::Tensor site_det_score,
        at::Tensor inst_curr_bestScoreImprov,
        at::Tensor inst_next_bestScoreImprov,
        at::Tensor site_det_siteId,
        at::Tensor site_det_sig_idx,
        at::Tensor site_det_sig,
        at::Tensor site_det_impl_lut,
        at::Tensor inst_curr_detSite,
        at::Tensor inst_curr_bestSite,
        at::Tensor inst_next_detSite,
        at::Tensor inst_next_bestSite,
        at::Tensor sites_with_special_nodes)
{
    CHECK_FLAT(pos);
    CHECK_EVEN(pos);
    CHECK_CONTIGUOUS(pos);

    CHECK_FLAT(site_xy);
    CHECK_CONTIGUOUS(site_xy);

    CHECK_FLAT(mlab_locX);
    CHECK_CONTIGUOUS(mlab_locX);
    CHECK_FLAT(mlab_locY);
    CHECK_CONTIGUOUS(mlab_locY);

    CHECK_FLAT(mlab_indices);
    CHECK_CONTIGUOUS(mlab_indices);

    CHECK_FLAT(site2addr_map);
    CHECK_CONTIGUOUS(site2addr_map);

    int numNodes = pos.numel() / 2;

    // Call the cuda kernel launcher
    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "legalizeMlabCudaLauncher", [&] {
        legalizeMlabCudaLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(mlab_locX, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(mlab_locY, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(mlab_indices, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site2addr_map, int),
                    num_mlab_nodes, num_sites_y, SIG_IDX, SLICE_CAPACITY, 
                    DREAMPLACE_TENSOR_DATA_PTR(dist_moved, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_bestScoreImprov, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_bestScoreImprov, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_detSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_bestSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_detSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_bestSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sites_with_special_nodes, int)
                    );
                });
    //std::cout << "Legalize MLabs"<< std::endl;
}

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("initLegalization", &DREAMPLACE_NAMESPACE::initLegalization, 
        "initialize LUT/FF legalization (CUDA)");
  m.def("runDLIter", &DREAMPLACE_NAMESPACE::runDLIter, "Run DL Iteration (CUDA)");
  m.def("legalizeMlab", &DREAMPLACE_NAMESPACE::legalizeMlab, "Legalize Mlab (CUDA)");
}


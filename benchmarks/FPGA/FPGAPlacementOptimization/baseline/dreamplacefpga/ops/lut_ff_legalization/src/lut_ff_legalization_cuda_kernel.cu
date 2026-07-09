/**
 * @file   lut_ff_legalization_cuda_kernel.cu
 * @author Rachel Selina (DREAMPlaceFPGA-PL)
 * @date   Aug 2023
 * @brief  Legalize LUT/FF
 */
#include <float.h>
#include <math.h>
#include <stdio.h>
#include "assert.h"
#include "cuda_runtime.h"
#include <thrust/copy.h>
#include <thrust/sort.h>
#include <thrust/sequence.h>
#include <thrust/transform.h>
#include <thrust/functional.h>
#include <thrust/host_vector.h>
#include <thrust/device_vector.h>
#include <thrust/iterator/counting_iterator.h>
#include <thrust/iterator/constant_iterator.h>
#include "utility/src/print.cuh"
#include "utility/src/utils.cuh"
#include "utility/src/limits.h"

//local dependency
#include "lut_ff_legalization/src/graph_matching.cuh"

DREAMPLACE_BEGIN_NAMESPACE

#define THREAD_COUNT 64
#define INVALID -1
#define INPUT_PIN 1
//Reset below values if required: Below values are for a maximum SLICE_CAPACITY of 20
#define SLICE_MAX_CAP 20
#define SIG_MAX_CAP 40
#define CE_MAX_CAP 7
#define CKSR_MAX_CAP 2

//Clear entries in candidate
inline __device__ void clear_cand_contents(const int tsPQ, const int SIG_IDX,
        const int CKSR_IN_CLB, const int CE_IN_CLB, const int SLICE_CAPACITY,
        int* site_sig_idx, int* site_sig, int* site_impl_lut, int* site_impl_ff,
        int* site_impl_cksr, int* site_impl_ce)
{
    int topIdx(tsPQ*SIG_IDX);
    int lutIdx = tsPQ*SLICE_CAPACITY;
    int ckIdx = tsPQ*CKSR_IN_CLB;
    int ceIdx = tsPQ*CE_IN_CLB;

    for(int sg = 0; sg < SIG_IDX; ++sg)
    {
        site_sig[topIdx + sg] = INVALID;
    }
    for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
    {
        site_impl_lut[lutIdx + sg] = INVALID;
    }
    for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
    {
        site_impl_ff[lutIdx + sg] = INVALID;
    }
    for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
    {
        site_impl_cksr[ckIdx + sg] = INVALID;
    }
    for(int sg = 0; sg < CE_IN_CLB; ++sg)
    {
        site_impl_ce[ceIdx + sg] = INVALID;
    }
}

//Check if entry exists in array
inline __device__ bool val_in_array(
        const int* array, const int arraySize, const int arrayIdx, const int val)
{
    for (int idx = 0; idx < arraySize; ++idx)
    {
        if (array[arrayIdx+idx] == val)
        {
            return true;
        }
    }
    return false;
}

/// define candidate_validity_check
// Candidate is valid if the instance is not commited to a site
inline __device__ bool candidate_validity_check(
        const int* is_mlab_node, const int SLICE_CAPACITY,
        const int topIdx, const int pqSigIdx,
        const int siteId, const int* site_curr_pq_sig,
        const int* inst_curr_detSite)
{
    //Check first instance if it is mlab
    if (pqSigIdx == 2*SLICE_CAPACITY &&
            is_mlab_node[site_curr_pq_sig[topIdx]] == 1)
    {
        int pqInst = site_curr_pq_sig[topIdx];
        if (inst_curr_detSite[pqInst] != INVALID && 
                inst_curr_detSite[pqInst] != siteId)
        {
            return false;
        }
    } else
    {
        for (int i = 0; i < pqSigIdx; ++i)
        {
            int pqInst = site_curr_pq_sig[topIdx + i];

            if (inst_curr_detSite[pqInst] != INVALID && 
                    inst_curr_detSite[pqInst] != siteId)
            {
                return false;
            }
        }
    }
    return true;
}

////SUBFUCTIONS////

//define add flop to candidate
inline __device__ bool add_flop_to_candidate_impl(
        const int* node2outpinIdx_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int* extended_ctrlSets, const int* ext_ctrlSet_start_map,
        const int* flop2ctrlSetId_map, const int* node2fence_region_map,
        const int* res_lut, const int lutId, const int ffCKSR, const int ffCE,
        const int ffId, const int half_ctrl_mode, const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY, const int CKSR_IN_CLB, const int CE_IN_CLB,
        const int BLE_CAPACITY, const int lut_maxShared, int* res_ff, int* res_cksr,
        int* res_ce)
{
    if (half_ctrl_mode == 1)
    {
        for (int i = 0; i < CKSR_IN_CLB; ++i)
        {
            if (res_cksr[i] != INVALID && 
                    res_cksr[i] != ffCKSR)
            {
                continue;
            }

            for (int j = 0; j < CKSR_IN_CLB; ++j)
            {
                int ceIdx = CKSR_IN_CLB*i + j;
                if (res_ce[ceIdx] != INVALID && 
                        res_ce[ceIdx] != ffCE)
                {
                    continue;
                }

                int beg = i*HALF_SLICE_CAPACITY+j;
                int end = beg + HALF_SLICE_CAPACITY;
                for (int k = beg; k < end; k += BLE_CAPACITY)
                {
                    if (res_ff[k] == INVALID)
                    {
                        res_ff[k] = ffId;
                        res_cksr[i] = ffCKSR;
                        res_ce[ceIdx] = ffCE;
                        return true;
                    }
                }
            }
        }
    } else
    {
        //FF Ctrls are SHARED across the SLICE
        int ckID = INVALID;
        for (int i = 0; i < CKSR_IN_CLB; ++i)
        {
            if (res_cksr[i] == ffCKSR || res_cksr[i] == INVALID)
            {
                ckID = i;
                break;
            }
        }

        if (ckID != INVALID)
        {
            int fCtrlId = flop2ctrlSetId_map[ffId];
            int fCStartId = ext_ctrlSet_start_map[fCtrlId];
            int fCEndId = ext_ctrlSet_start_map[fCtrlId+1];

            int upd_ctrls[SLICE_MAX_CAP];
            int num_upd_ctrls(0);

            for (int sg = 0; sg < CE_IN_CLB; ++sg)
            {
                if (res_ce[sg] != INVALID)
                {
                    upd_ctrls[num_upd_ctrls] = res_ce[sg];
                    ++num_upd_ctrls;
                }
            }

            int num_init_ctrls = num_upd_ctrls;

            //Ensure all FF ctrls can be accommodated in Slice
            for (int j = fCStartId; j < fCEndId; ++j)
            {
                upd_ctrls[num_upd_ctrls] = extended_ctrlSets[j];
                ++num_upd_ctrls;
            }

            if (num_upd_ctrls > num_init_ctrls)
            {
                sort_array(upd_ctrls, num_upd_ctrls);
                remove_duplicates(upd_ctrls, num_upd_ctrls);
            }

            if (num_upd_ctrls > CE_IN_CLB)
            {
                return false;
            }

            int fIndex = INVALID;
            for (int i = 0; i < SLICE_CAPACITY; i += BLE_CAPACITY)
            {
                if (res_ff[i] == INVALID)
                {
                    if(subSlice_compatibility(node2outpinIdx_map,
                                flat_node2pin_start_map, flat_node2pin_map,
                                pin2net_map, pin_typeIds, node2fence_region_map,
                                res_ff, res_lut, lutId, SLICE_CAPACITY,
                                BLE_CAPACITY, lut_maxShared, BLE_CAPACITY,
                                i, ffId))
                    {
                        fIndex = i;
                        break;
                    }
                } else if (res_ff[i+1] == INVALID)
                {
                    if(subSlice_compatibility(node2outpinIdx_map,
                                flat_node2pin_start_map, flat_node2pin_map,
                                pin2net_map, pin_typeIds, node2fence_region_map,
                                res_ff, res_lut, lutId, SLICE_CAPACITY,
                                BLE_CAPACITY, lut_maxShared, BLE_CAPACITY,
                                i+1, ffId))
                    {
                        fIndex = i+1;
                        break;
                    }
                }
            }

            if (fIndex != INVALID)
            {
                res_ff[fIndex] = ffId;
                res_cksr[ckID] = ffCKSR;

                for (int j = 0; j < num_upd_ctrls; ++j)
                {
                    res_ce[j] = upd_ctrls[j];
                }
                for (int j = num_upd_ctrls; j < CE_IN_CLB; ++j)
                {
                    res_ce[j] = INVALID;
                }
                return true;
            }
        }
    }
    return false;
}

// define remove_invalid_neighbor
inline __device__ void remove_invalid_neighbor(
        const int sIdx, const int sNbrIdx, int* site_nbr_idx, int* site_nbr)
{
    int temp[1024];
    int tempSize(0);
    for (int i = 0; i < site_nbr_idx[sIdx]; ++i)
    {
        int instId = site_nbr[sNbrIdx + i];

        if (instId != INVALID)
        {
            temp[tempSize] = instId;
            ++tempSize;
        }
    }

    for (int j = 0; j < tempSize; ++j)
    {
        site_nbr[sNbrIdx+j] = temp[j];
    }
    for (int j = tempSize; j < site_nbr_idx[sIdx]; ++j)
    {
        site_nbr[sNbrIdx+j] = INVALID;
    }
    site_nbr_idx[sIdx] = tempSize;

    //DBG
    if (tempSize > 1000)
    {
        printf("WARN: remove_invalid_neighbor() has tempSize > 1000 for site: %d\n", sIdx);
    }
    //DBG
}
//addLUTToCandidateImpl
inline __device__ bool add_lut_to_cand_impl(
        const int* node2outpinIdx_map, const int* lut_type,
        const int* flat_node2pin_start_map, const int* flat_node2pin_map,
        const int* pin2net_map, const int* pin_typeIds, const int* node2fence_region_map,
        const int* res_ff, const int lutTypeInSliceUnit, const int lutId,
        const int lut_maxShared, const int lutInstId, const int SLICE_CAPACITY,
        const int BLE_CAPACITY, const int half_ctrl_mode, int* res_lut)
{
    if (half_ctrl_mode == 1)
    {
        for (int i=0; i < SLICE_CAPACITY; i += BLE_CAPACITY)
        {
            if (res_lut[i] == INVALID)
            {
                res_lut[i] = lutInstId;
                return true;
            }
        }
        for (int i=1; i < SLICE_CAPACITY; i += BLE_CAPACITY)
        {    
            if (res_lut[i] == INVALID)
            {
                if (two_lut_compatibility_check(lut_type, flat_node2pin_start_map,
                            flat_node2pin_map, pin2net_map, pin_typeIds, lutTypeInSliceUnit,
                            lut_maxShared, res_lut[i-1], lutInstId))
                {
                    res_lut[i] = lutInstId;
                    return true;
                }
            }
        }
    } else
    {
        for (int i=0; i < SLICE_CAPACITY; i += BLE_CAPACITY)
        {
            if (res_lut[i] == INVALID)
            {
                if(subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map, flat_node2pin_map,
                            pin2net_map, pin_typeIds, node2fence_region_map, res_ff, res_lut, lutId,
                            SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared, BLE_CAPACITY, i, lutInstId))
                {
                    res_lut[i] = lutInstId;
                    return true;
                }
            } else if(res_lut[i+1] == INVALID)
            {
                if (subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map, flat_node2pin_map,
                            pin2net_map, pin_typeIds, node2fence_region_map, res_ff, res_lut, lutId,
                            SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared, BLE_CAPACITY, i+1, lutInstId))
                {
                    res_lut[i+1] = lutInstId;
                    return true;
                }
            }
        }
    }
    return false;
}

//template <typename T>
__device__ bool is_inst_in_cand_feasible(
        const int* node2outpinIdx_map, const int* node2fence_region_map,
        const int* lut_type, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int* flat_node2prclstrCount, const int* flat_node2precluster_map,
        const int* flop2ctrlSetId_map, const int* flop_ctrlSets,
        const int* extended_ctrlSets, const int* ext_ctrlSet_start_map,
        const int* site_det_impl_lut, const int* site_det_impl_ff,
        const int* site_det_impl_cksr, const int* site_det_impl_ce,
        const int* special_nodes, const int lutTypeInSliceUnit, const int lut_maxShared,
        const int siteId, const int instId, const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY, const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE, const int CKSR_IN_CLB, const int CE_IN_CLB,
        const int lutId, const int ffId, const int half_ctrl_mode)
{
    ////DBG
    //int dbgInstId = 326924;
    //int dbgSId = 3595;
    ////DBG

    int instPcl = instId*3;

    int sdlutId = siteId*SLICE_CAPACITY;
    int sdckId = siteId*CKSR_IN_CLB;
    int sdceId = siteId*CE_IN_CLB;

    int res_lut[SLICE_MAX_CAP];
    int res_ff[SLICE_MAX_CAP];
    int res_cksr[CKSR_MAX_CAP];
    int res_ce[CE_MAX_CAP];

    for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
    {
        res_lut[sg] = site_det_impl_lut[sdlutId + sg];
        res_ff[sg] = site_det_impl_ff[sdlutId + sg];
    }
    for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
    {
        res_cksr[sg] = site_det_impl_cksr[sdckId + sg];
    }
    for(int sg = 0; sg < CE_IN_CLB; ++sg)
    {
        res_ce[sg] = site_det_impl_ce[sdceId + sg];
    }
    /////

        ////DBG
        //if (siteId == dbgSId && instId == dbgInstId)
        //{
        //    printf("%d is inst in cand feasible: Here for instId %d \n", siteId, instId);
        //}
        ////DBG

    bool lutFail(false);
    for (int idx = 0; idx < flat_node2prclstrCount[instId]; ++idx)
    {
        int clInstId = flat_node2precluster_map[instPcl + idx];
        int clInstCKSR = flop2ctrlSetId_map[clInstId]*3 + 1;
        int clInstCE = flop2ctrlSetId_map[clInstId]*3 + 2;

        if (node2fence_region_map[clInstId] == lutId) //LUT
        {
            if (!lutFail && 
                !add_lut_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map,
                    flat_node2pin_map, pin2net_map, pin_typeIds, node2fence_region_map, res_ff,
                    lutTypeInSliceUnit, lutId, lut_maxShared, clInstId, SLICE_CAPACITY,
                    BLE_CAPACITY, half_ctrl_mode, res_lut))
            {
                lutFail = true;
            }
            ////DBG
            //if (siteId == dbgSId && instId == dbgInstId)
            //{
            //    printf("%d is inst in cand feasible: Check add lut to cand impl for instId %d, lutFail %d \n", siteId, clInstId, lutFail);
            //}
            ////DBG

        } else if (node2fence_region_map[clInstId] == ffId) //FF
        {
            ////DBG
            //if (siteId == dbgSId && instId == dbgInstId)
            //{
            //    printf("%d is inst in cand feasible: Check add flop to candidate impl for instId %d \n", siteId, clInstId);
            //}
            ////DBG

            if(!add_flop_to_candidate_impl(node2outpinIdx_map, flat_node2pin_start_map,
                    flat_node2pin_map, pin2net_map, pin_typeIds, extended_ctrlSets,
                    ext_ctrlSet_start_map, flop2ctrlSetId_map, node2fence_region_map,
                    res_lut, lutId, flop_ctrlSets[clInstCKSR], flop_ctrlSets[clInstCE],
                    clInstId, half_ctrl_mode, SLICE_CAPACITY, HALF_SLICE_CAPACITY,
                    CKSR_IN_CLB, CE_IN_CLB, BLE_CAPACITY, lut_maxShared, res_ff,
                    res_cksr, res_ce))
            {
                ////DBG
                //if (siteId == dbgSId && instId == dbgInstId)
                //{
                //    printf("%d is inst in cand feasible: add flop to candidate impl for instId %d returned False\n", siteId, clInstId);
                //}
                ////DBG

                return false;
            }
        }
                ////DBG
                //if (siteId == dbgSId && instId == dbgInstId)
                //{
                //    printf("%d is inst in cand feasible: Done for instId %d \n", siteId, clInstId);
                //}
                ////DBG
    }
    if (!lutFail)
    {
        return true;
    }

    ////DBG
    //if (siteId == dbgSId && instId == dbgInstId)
    //{
    //    printf("%d is inst in cand feasible: lutFail %d use graph matching\n", siteId, lutFail);
    //    printf("Contents of res_lut: ");
    //    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
    //    {
    //        printf("%d ", res_lut[sg]);
    //    }
    //    printf("\n");

    //    printf("Contents of res_lut with lut_type and special_nodes: ");
    //    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
    //    {
    //        printf("%d", res_lut[sg]);
    //        if (res_lut[sg] != INVALID)
    //        {
    //            printf(" (%d, %d)", lut_type[res_lut[sg]], special_nodes[res_lut[sg]]);
    //        }
    //        printf(", ");
    //    }
    //    printf("\n");
    //}
    ////DBG

    return fit_luts_to_candidate_impl(node2outpinIdx_map, lut_type, pin2net_map, pin_typeIds,
            flat_node2pin_start_map, flat_node2pin_map, flat_node2precluster_map,
            node2fence_region_map, special_nodes, half_ctrl_mode, lutTypeInSliceUnit,
            lut_maxShared, instPcl, flat_node2prclstrCount[instId], NUM_BLE_PER_SLICE,
            SLICE_CAPACITY, BLE_CAPACITY, lutId, res_lut, res_ff);
}

inline __device__ bool add_inst_to_cand_impl(
        const int* node2outpinIdx_map, const int* lut_type,
        const int* flat_node2pin_start_map, const int* flat_node2pin_map,
        const int* pin2net_map, const int* pin_typeIds,
        const int* flat_node2prclstrCount, const int* flat_node2precluster_map,
        const int* flop2ctrlSetId_map, const int* node2fence_region_map,
        const int* flop_ctrlSets, const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map, const int* special_nodes,
        const int lutTypeInSliceUnit, const int lut_maxShared, const int instId,
        const int lutId, const int ffId, const int half_ctrl_mode, const int CKSR_IN_CLB,
        const int CE_IN_CLB, const int SLICE_CAPACITY, const int HALF_SLICE_CAPACITY,
        const int BLE_CAPACITY, const int NUM_BLE_PER_SLICE, int* nwCand_lut,
        int* nwCand_ff, int* nwCand_cksr, int* nwCand_ce)
{
    int instPcl = instId*3;

    //array instantiation
    int res_lut[SLICE_MAX_CAP];
    int res_ff[SLICE_MAX_CAP];
    int res_cksr[CKSR_MAX_CAP];
    int res_ce[CE_MAX_CAP];

    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
    {
        res_lut[sg] = nwCand_lut[sg];
        res_ff[sg] = nwCand_ff[sg];
    }
    for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
    {
        res_cksr[sg] = nwCand_cksr[sg];
    }
    for (int sg = 0; sg < CE_IN_CLB; ++sg)
    {
        res_ce[sg] = nwCand_ce[sg];
    }
    /////
    //DBG

    bool lutFail(false);
    for (int idx = 0; idx < flat_node2prclstrCount[instId]; ++idx)
    {
        int clInstId = flat_node2precluster_map[instPcl + idx];
        int clInstCKSR = flop2ctrlSetId_map[clInstId]*3 + 1;
        int clInstCE = flop2ctrlSetId_map[clInstId]*3 + 2;

        if (node2fence_region_map[clInstId] == lutId) //LUT
        {
            if (!lutFail &&
                !add_lut_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map,
                    flat_node2pin_map, pin2net_map, pin_typeIds, node2fence_region_map, res_ff,
                    lutTypeInSliceUnit, lutId, lut_maxShared, clInstId, SLICE_CAPACITY,
                    BLE_CAPACITY, half_ctrl_mode, res_lut))
            {
                lutFail = true;
            }
        } else if (node2fence_region_map[clInstId] == ffId) //FF
        {
            if(!add_flop_to_candidate_impl(node2outpinIdx_map, flat_node2pin_start_map,
                    flat_node2pin_map, pin2net_map, pin_typeIds, extended_ctrlSets,
                    ext_ctrlSet_start_map, flop2ctrlSetId_map, node2fence_region_map,
                    res_lut, lutId, flop_ctrlSets[clInstCKSR], flop_ctrlSets[clInstCE],
                    clInstId, half_ctrl_mode, SLICE_CAPACITY, HALF_SLICE_CAPACITY,
                    CKSR_IN_CLB, CE_IN_CLB, BLE_CAPACITY, lut_maxShared, res_ff,
                    res_cksr, res_ce))
            {
                return false;
            }
        }
    }

    if (!lutFail)
    {
        for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
        {
            nwCand_lut[sg] = res_lut[sg];
            nwCand_ff[sg] = res_ff[sg];
        }
        for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
        {
            nwCand_cksr[sg] = res_cksr[sg];
        }
        for (int sg = 0; sg < CE_IN_CLB; ++sg)
        {
            nwCand_ce[sg] = res_ce[sg];
        }

        return true;
    }

    if(fit_luts_to_candidate_impl(node2outpinIdx_map, lut_type, pin2net_map,
        pin_typeIds, flat_node2pin_start_map, flat_node2pin_map,
        flat_node2precluster_map, node2fence_region_map, special_nodes,
        half_ctrl_mode, lutTypeInSliceUnit, lut_maxShared, instPcl,
        flat_node2prclstrCount[instId], NUM_BLE_PER_SLICE, SLICE_CAPACITY,
        BLE_CAPACITY, lutId, res_lut, res_ff))
    {
        for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
        {
            nwCand_lut[sg] = res_lut[sg];
            nwCand_ff[sg] = res_ff[sg];
        }
        for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
        {
            nwCand_cksr[sg] = res_cksr[sg];
        }
        for (int sg = 0; sg < CE_IN_CLB; ++sg)
        {
            nwCand_ce[sg] = res_ce[sg];
        }

        return true;
    }
    return false;
}

//template <typename T>
inline __device__ void remove_incompatible_neighbors(
        const int* node2outpinIdx_map, const int* node2fence_region_map,
        const int* lut_type, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int* flat_node2prclstrCount, const int* flat_node2precluster_map,
        const int* flop2ctrlSetId_map, const int* flop_ctrlSets,
        const int* extended_ctrlSets, const int* ext_ctrlSet_start_map,
        const int* site_det_impl_lut, const int* site_det_impl_ff,
        const int* site_det_impl_cksr, const int* site_det_impl_ce,
        const int* site_det_sig, const int* site_det_sig_idx, const int* special_nodes,
        const int lutTypeInSliceUnit, const int lut_maxShared, const int siteId,
        const int sNbrIdx, const int half_ctrl_mode, const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY, const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE, const int SIG_IDX, const int CKSR_IN_CLB,
        const int CE_IN_CLB, const int lutId, const int ffId, int* site_nbr_idx,
        int* site_nbr)
{
    ////DBG
    //int dbgSId = 3595;
    ////DBG

    int sdtopId = siteId*SIG_IDX;

        ////DBG
        //if (siteId == dbgSId)
        //{
        //    int sdtopId = siteId*SIG_IDX;
        //    int sdlutId = siteId*SLICE_CAPACITY;
        //    int sdckId = siteId*CKSR_IN_CLB;
        //    int sdceId = siteId*CE_IN_CLB;
        //    printf("%d remove incompatible neighbors for total neighbor instances of %d :", siteId, site_nbr_idx[siteId]);

        //    for (int nbrId = 0; nbrId < site_nbr_idx[siteId]; ++nbrId)
        //    {
        //        printf("%d ", site_nbr[sNbrIdx + nbrId]);
        //    }
        //    printf("\n");

        //    //////
        //    printf("There are %d elements in site_det_sig: ", site_det_sig_idx[siteId]);
        //    for(int sg = 0; sg < site_det_sig_idx[siteId]; ++sg)
        //    {
        //        printf("%d ",site_det_sig[sdtopId + sg]);
        //    }
        //    printf("\n");
        //    printf("LUTs in site_det_impl_lut: ");
        //    for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
        //    {
        //        printf("%d ", site_det_impl_lut[sdlutId + sg]);
        //    }
        //    printf("\n");
        //    printf("FFs in site_det_impl_ff: ");
        //    for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
        //    {
        //        printf("%d ", site_det_impl_ff[sdlutId + sg]);
        //    }
        //    printf("\n");
        //    printf("FFs CKSR: ");
        //    for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
        //    {
        //        printf("%d ", site_det_impl_cksr[sdckId + sg]);
        //    }
        //    printf("\n");
        //    printf("FFs CE: ");
        //    for(int sg = 0; sg < CE_IN_CLB; ++sg)
        //    {
        //        printf("%d ", site_det_impl_ce[sdceId + sg]);
        //    }
        //    printf("\n");
        //    //////
        //}
        ////DBG

    for (int nbrId = 0; nbrId < site_nbr_idx[siteId]; ++nbrId)
    {
        int instId = site_nbr[sNbrIdx + nbrId];

        ////DBG
        //if (siteId == dbgSId)
        //{
        //    printf("%d remove incompatible neighbors %d of %d: Consider instId %d of type %d",
        //            siteId, nbrId, site_nbr_idx[siteId], instId, node2fence_region_map[instId]);
        //    if (node2fence_region_map[instId] == 1)
        //    {
        //        int clInstCKSR = flop2ctrlSetId_map[instId]*3 + 1;
        //        printf(" has clk %d and ctrls: ", flop_ctrlSets[clInstCKSR]);
        //        int cStartId =  ext_ctrlSet_start_map[flop2ctrlSetId_map[instId]];
        //        int cEndId =  ext_ctrlSet_start_map[flop2ctrlSetId_map[instId]+1];
        //        for (int ctrlId = cStartId; ctrlId < cEndId; ++ctrlId)
        //        {
        //            printf("%d ", extended_ctrlSets[ctrlId]);
        //        }
        //    }
        //    printf("\n");
        //}
        ////DBG

        if (val_in_array(site_det_sig, site_det_sig_idx[siteId], sdtopId, instId) || 
            !is_inst_in_cand_feasible(node2outpinIdx_map, node2fence_region_map, lut_type,
                flat_node2pin_start_map, flat_node2pin_map, pin2net_map, pin_typeIds,
                flat_node2prclstrCount, flat_node2precluster_map, flop2ctrlSetId_map,
                flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map, site_det_impl_lut,
                site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce, special_nodes,
                lutTypeInSliceUnit, lut_maxShared, siteId, instId, SLICE_CAPACITY,
                HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE, CKSR_IN_CLB,
                CE_IN_CLB, lutId, ffId, half_ctrl_mode))
        {
            site_nbr[sNbrIdx + nbrId] = INVALID;
        }

        ////DBG
        //if (siteId == dbgSId)
        //{
        //    printf("%d remove incompatible neighbors %d of %d: Done with instId %d of type %d\n",
        //            siteId, nbrId, site_nbr_idx[siteId], instId, node2fence_region_map[instId]);
        //}
        ////DBG

    }
        ////DBG
        //if (siteId == dbgSId)
        //{
        //    printf("%d remove incompatible neighbors: Marked invalid instance neighbors in site_nbr \n", siteId);
        //}
        ////DBG

    //Remove invalid neighbor instances
    remove_invalid_neighbor(siteId, sNbrIdx, site_nbr_idx, site_nbr);
        ////DBG
        //if (siteId == dbgSId)
        //{
        //    printf("%d remove incompatible neighbors: Updated site_nbr has %d instances\n", siteId, site_nbr_idx[siteId]);
        //}
        ////DBG

}

//WL Improv
template <typename T>
__device__ void compute_wirelength_improv(
        const T* pos_x, const T* pos_y, const T* net_bbox, const T* pin_offset_x,
        const T* pin_offset_y, const T* net_weights, const T* site_xy,
        const int* net2pincount, const int* flat_net2pin_start_map,
        const int* net_pinIdArrayX, const int* net_pinIdArrayY,
        const int* pin2node_map, const T xWirelenWt, const T yWirelenWt,
        const int currNetId, const int res_siteId, const int cNIPIdx,
        const int* currNetIntPins, T& wirelenImprov)
{
    //Compute wirelenImprov
    int cNbId = currNetId*4;
    T netXlen = net_bbox[cNbId+2] - net_bbox[cNbId];
    T netYlen = net_bbox[cNbId+3] - net_bbox[cNbId+1];
    if (cNIPIdx == net2pincount[currNetId])
    {
        T bXLo(pin_offset_x[currNetIntPins[0]]);
        T bXHi(pin_offset_x[currNetIntPins[0]]);
        T bYLo(pin_offset_y[currNetIntPins[0]]);
        T bYHi(pin_offset_y[currNetIntPins[0]]);
        for (int poI = 1; poI < cNIPIdx; ++poI)
        {
            T poX = pin_offset_x[currNetIntPins[poI]];
            T poY = pin_offset_y[currNetIntPins[poI]];
            if (poX < bXLo)
            {
                bXLo = poX;
            } else if (poX > bXHi)
            {
                bXHi = poX;
            }
            if (poY < bYLo)
            {
                bYLo = poY;
            } else if (poY > bYHi)
            {
                bYHi = poY;
            }
        }
        wirelenImprov += net_weights[currNetId] *
                            (xWirelenWt * (netXlen - (bXHi-bXLo)) + 
                            yWirelenWt * (netYlen - (bYHi - bYLo)));
        return;
    }

    T bXLo(net_bbox[cNbId]);
    T bYLo(net_bbox[cNbId+1]);
    T bXHi(net_bbox[cNbId+2]);
    T bYHi(net_bbox[cNbId+3]);

    int sId = res_siteId*2;
    T locX = site_xy[sId];
    T locY = site_xy[sId+1];

    if (locX <= bXLo)
    {
        bXLo = locX;
    } else
    {
        int n2pId = flat_net2pin_start_map[currNetId];
        while (n2pId < flat_net2pin_start_map[currNetId+1] && 
                val_in_array(currNetIntPins, cNIPIdx, 0, net_pinIdArrayX[n2pId]))
        {
            ++n2pId;
        }
        int reqPId = net_pinIdArrayX[n2pId];
        T pinX = pos_x[pin2node_map[reqPId]] + pin_offset_x[reqPId];
        bXLo = DREAMPLACE_STD_NAMESPACE::min(pinX, locX);
    }

    if (locX >= bXHi)
    {
        bXHi = locX;
    } else
    {
        int n2pId = flat_net2pin_start_map[currNetId+1]-1;
        while (n2pId >= flat_net2pin_start_map[currNetId] &&
                val_in_array(currNetIntPins, cNIPIdx, 0, net_pinIdArrayX[n2pId]))
        {
            --n2pId;
        }
        int reqPId = net_pinIdArrayX[n2pId];
        T pinX = pos_x[pin2node_map[reqPId]] + pin_offset_x[reqPId];
        bXHi = DREAMPLACE_STD_NAMESPACE::max(pinX, locX);
    }

    if (locY <= bYLo)
    {
        bYLo = locY;
    } else
    {
        int n2pId = flat_net2pin_start_map[currNetId];
        while (n2pId < flat_net2pin_start_map[currNetId+1] &&
                val_in_array(currNetIntPins, cNIPIdx, 0, net_pinIdArrayY[n2pId]))
        {
            ++n2pId;
        }
        int reqPId = net_pinIdArrayY[n2pId];
        T pinY = pos_y[pin2node_map[reqPId]] + pin_offset_y[reqPId];
        bYLo = DREAMPLACE_STD_NAMESPACE::min(pinY, locY);
    }

    if (locY >= bYHi)
    {
        bYHi = locY;
    } else
    {
        int n2pId = flat_net2pin_start_map[currNetId+1]-1;
        while (n2pId >= flat_net2pin_start_map[currNetId] &&
                val_in_array(currNetIntPins, cNIPIdx, 0, net_pinIdArrayY[n2pId]))
        {
            --n2pId;
        }
        int reqPId = net_pinIdArrayY[n2pId];
        T pinY = pos_y[pin2node_map[reqPId]] + pin_offset_y[reqPId];
        bYHi = DREAMPLACE_STD_NAMESPACE::max(pinY, locY);
    }
    wirelenImprov += net_weights[currNetId] * 
                    (xWirelenWt * (netXlen - (bXHi-bXLo)) + 
                    yWirelenWt * (netYlen - (bYHi - bYLo)));
    return;
}

//computeCandidateScore
template <typename T>
__device__ void compute_candidate_score(
        const T* pos_x, const T* pos_y, const T* pin_offset_x, const T* pin_offset_y,
        const T* net_bbox, const T* net_weights, const T* site_xy,
        const int* net_pinIdArrayX, const int* net_pinIdArrayY,
        const int* flat_net2pin_start_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* sorted_net_map, const int* pin2net_map,
        const int* pin2node_map, const int* net2pincount, const int* lut_type,
        const T xWirelenWt, const T yWirelenWt, const T extNetCountWt,
        const T wirelenImprovWt, const int netShareScoreMaxNetDegree,
        const int wlscoreMaxNetDegree, const int half_ctrl_mode, const int* res_sig,
        const int res_siteId, const int res_sigIdx, T &result)
{
    T netShareScore = T(0.0);
    T wirelenImprov = T(0.0);
    T typeScore = T(0.0);
    int pins[512];
    int pinIdx = 0;

    for (int i = 0; i < res_sigIdx; ++i)
    {
        int instId = res_sig[i];
        //For macro nodes, same instId is repeated in sig
        if (i != 0 && instId == res_sig[i-1]) continue;
        for (int pId = flat_node2pin_start_map[instId]; 
                pId < flat_node2pin_start_map[instId+1]; ++pId)
        {
            pins[pinIdx] = flat_node2pin_map[pId];
            ++pinIdx;
        }
        if (half_ctrl_mode == 0)
        {
            typeScore += lut_type[instId];
        }
    }
    sort_array(pins, pinIdx);
    //remove_duplicates(pins, pinIdx);

    if (pinIdx == 0)
    {
        result = T(0.0);
        return;
    } 

    int maxNetDegree = DREAMPLACE_STD_NAMESPACE::max(netShareScoreMaxNetDegree,
                                                     wlscoreMaxNetDegree);
    int currNetId = pin2net_map[pins[0]];

    if (net2pincount[currNetId] > maxNetDegree)
    {
        result = T(0.0);
        return;
    } 

    int numIntNets(0), numNets(0);
    int currNetIntPins[512];
    int cNIPIdx = 0;

    currNetIntPins[cNIPIdx] = pins[0];
    ++cNIPIdx;

    for (int pId = 1; pId < pinIdx; ++pId)
    {
        int netId = pin2net_map[pins[pId]];
        if (netId == currNetId)
        {
            currNetIntPins[cNIPIdx] = pins[pId];
            ++cNIPIdx;
        } else
        {
            if (net2pincount[currNetId] <= netShareScoreMaxNetDegree)
            {
                ++numNets;
                numIntNets += (cNIPIdx == net2pincount[currNetId] ? 1 : 0);
                netShareScore += net_weights[currNetId] * (cNIPIdx - 1.0) / DREAMPLACE_STD_NAMESPACE::max(T(1.0), net2pincount[currNetId] - T(1.0));
            }
            if (net2pincount[currNetId] <= wlscoreMaxNetDegree)
            {
                compute_wirelength_improv(pos_x, pos_y, net_bbox, pin_offset_x, pin_offset_y,
                    net_weights, site_xy, net2pincount, flat_net2pin_start_map, net_pinIdArrayX,
                    net_pinIdArrayY, pin2node_map, xWirelenWt, yWirelenWt, currNetId, res_siteId,
                    cNIPIdx, currNetIntPins, wirelenImprov);
            }
            currNetId = netId;
            if (net2pincount[currNetId] > maxNetDegree)
            {
                break;
            }
            cNIPIdx = 0;
            currNetIntPins[cNIPIdx] = pins[pId];
            ++cNIPIdx;
        }
    }

    //Handle last net
    if (net2pincount[currNetId] <= netShareScoreMaxNetDegree)
    {
        ++numNets;
        numIntNets += (cNIPIdx == net2pincount[currNetId] ? 1 : 0);
        netShareScore += net_weights[currNetId] * (cNIPIdx - 1.0) / DREAMPLACE_STD_NAMESPACE::max(T(1.0), net2pincount[currNetId] - T(1.0));
    }

    if (net2pincount[currNetId] <= wlscoreMaxNetDegree)
    {
        compute_wirelength_improv(pos_x, pos_y, net_bbox, pin_offset_x, pin_offset_y,
            net_weights, site_xy, net2pincount, flat_net2pin_start_map, net_pinIdArrayX,
            net_pinIdArrayY, pin2node_map, xWirelenWt, yWirelenWt, currNetId, res_siteId,
            cNIPIdx, currNetIntPins, wirelenImprov);
    }
    netShareScore /= (T(1.0) + extNetCountWt * (numNets - numIntNets));
    result = netShareScore + wirelenImprovWt * wirelenImprov;

    if (half_ctrl_mode == 0)
    {
        result += T(0.1)*typeScore;
    }
}

template <typename T>
inline __device__ bool compare_pq_tops(
        const T* site_curr_pq_score, const int* site_curr_pq_top_idx, const int* site_curr_pq_validIdx,
        const int* site_curr_pq_siteId, const int* site_curr_pq_sig_idx, const int* site_curr_pq_sig,
        const int* site_curr_pq_impl_lut, const int* site_curr_pq_impl_ff, const int* site_curr_pq_impl_cksr,
        const int* site_curr_pq_impl_ce, const T* site_next_pq_score, const int* site_next_pq_top_idx,
        const int* site_next_pq_validIdx, const int* site_next_pq_siteId, const int* site_next_pq_sig_idx,
        const int* site_next_pq_sig, const int* site_next_pq_impl_lut, const int* site_next_pq_impl_ff,
        const int* site_next_pq_impl_cksr, const int* site_next_pq_impl_ce, const int siteId,
        const int sPQ, const int SIG_IDX, const int CKSR_IN_CLB, const int CE_IN_CLB,
        const int SLICE_CAPACITY)
{
    //Check site_curr_pq TOP == site_next_pq TOP
    int curr_pq_topId = sPQ+site_curr_pq_top_idx[siteId];
    int next_pq_topId = sPQ+site_next_pq_top_idx[siteId];

    if (site_curr_pq_validIdx[curr_pq_topId] != site_next_pq_validIdx[next_pq_topId] || 
            site_curr_pq_validIdx[curr_pq_topId] != 1)
    {
        return false;
    }
    if (site_curr_pq_score[curr_pq_topId] == site_next_pq_score[next_pq_topId] && 
            site_curr_pq_siteId[curr_pq_topId] == site_next_pq_siteId[next_pq_topId] &&
            site_curr_pq_sig_idx[curr_pq_topId] == site_next_pq_sig_idx[next_pq_topId])
    {
        //Check both sig
        int currPQSigIdx = curr_pq_topId*SIG_IDX;
        int nextPQSigIdx = next_pq_topId*SIG_IDX;

        for (int sg = 0; sg < site_curr_pq_sig_idx[curr_pq_topId]; ++sg)
        {
            if (site_curr_pq_sig[currPQSigIdx + sg] != site_next_pq_sig[nextPQSigIdx + sg])
            {
                return false;
            }
        }

        //Check impl
        int cCKRId = curr_pq_topId*CKSR_IN_CLB;
        int cCEId = curr_pq_topId*CE_IN_CLB;
        int cFFId = curr_pq_topId*SLICE_CAPACITY;
        int nCKRId = next_pq_topId*CKSR_IN_CLB;
        int nCEId = next_pq_topId*CE_IN_CLB;
        int nFFId = next_pq_topId*SLICE_CAPACITY;

        for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
        {
            if (site_curr_pq_impl_lut[cFFId + sg] != site_next_pq_impl_lut[nFFId + sg] || 
                    site_curr_pq_impl_ff[cFFId + sg] != site_next_pq_impl_ff[nFFId + sg])
            {
                return false;
            }
        }
        for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
        {
            if (site_curr_pq_impl_cksr[cCKRId + sg] != site_next_pq_impl_cksr[nCKRId + sg])
            {
                return false;
            }
        }
        for (int sg = 0; sg < CE_IN_CLB; ++sg)
        {
            if(site_curr_pq_impl_ce[cCEId + sg] != site_next_pq_impl_ce[nCEId + sg])
            {
                return false;
            }
        }
        return true;
    }
    return false;
}

////////////////////////////////
////////////////////////////////
////////////////////////////////

template <typename T>
__global__ void initNets(
        const T* pos_x,
        const T* pos_y,
        const T* pin_offset_x,
        const T* pin_offset_y,
        const int* flat_net2pin_start_map,
        const int* flat_net2pin_map,
        const int* sorted_net_idx,
        const int* pin2node_map,
        const int* net2pincount,
        const int num_nets,
        const int wlscoreMaxNetDegree,
        T* net_bbox,
        int* net_pinIdArrayX,
        int* net_pinIdArrayY)
{
    int i = threadIdx.x + blockDim.x * blockIdx.x;
    while (i < num_nets)
    {
        const int idx = sorted_net_idx[i];

        if (net2pincount[idx] > 0 && net2pincount[idx] <= wlscoreMaxNetDegree)
        {
            int pinIdxBeg = flat_net2pin_start_map[idx];
            int pinIdxEnd = flat_net2pin_start_map[idx+1];

            int xLo = idx*4;
            int yLo = xLo+1;
            int xHi = xLo+2;
            int yHi = xLo+3;

            int pnIdx = flat_net2pin_map[pinIdxBeg];
            int nodeIdx = pin2node_map[pnIdx];

            net_bbox[xLo] = pos_x[nodeIdx] + pin_offset_x[pnIdx];
            net_bbox[yLo] = pos_y[nodeIdx] + pin_offset_y[pnIdx];
            net_bbox[xHi] = net_bbox[xLo];
            net_bbox[yHi] = net_bbox[yLo];

            int tempX[512];
            int tempY[512];
            T temp_flat_net2pinX[512];
            T temp_flat_net2pinY[512];
            int tempId = 0;

            temp_flat_net2pinX[tempId] = net_bbox[xLo];
            temp_flat_net2pinY[tempId] = net_bbox[yLo];
            tempX[tempId] = pnIdx;
            tempY[tempId] = pnIdx;

            ++tempId;

            //Update Net Bbox based on node location and pin offset
            for (int pId = pinIdxBeg+1; pId < pinIdxEnd; ++pId)
            {
                int pinIdx = flat_net2pin_map[pId];
                int ndIdx = pin2node_map[pinIdx];

                T valX = pos_x[ndIdx] + pin_offset_x[pinIdx];
                T valY = pos_y[ndIdx] + pin_offset_y[pinIdx];

                if (valX < net_bbox[xLo])
                {
                    net_bbox[xLo] = valX;
                } else if (valX > net_bbox[xHi])
                {
                    net_bbox[xHi] = valX;
                }

                if (valY < net_bbox[yLo])
                {
                    net_bbox[yLo] = valY;
                } else if (valY > net_bbox[yHi])
                {
                    net_bbox[yHi] = valY;
                }

                temp_flat_net2pinX[tempId] = valX;
                temp_flat_net2pinY[tempId] = valY;

                tempX[tempId] = pinIdx;
                tempY[tempId] = pinIdx;

                ++tempId;
            }

            //Sort pinIdArray based on node loc and pin offset - Bubble sort
            for (int ix = 1; ix < tempId; ++ix)
            {
                for (int jx = 0; jx < tempId-1; ++jx)
                {
                    //Sort X
                    if (temp_flat_net2pinX[jx] > temp_flat_net2pinX[jx+1])
                    {
                        int tempVal = tempX[jx];
                        tempX[jx] = tempX[jx+1];
                        tempX[jx+1] = tempVal;

                        T net2pinVal = temp_flat_net2pinX[jx];
                        temp_flat_net2pinX[jx] = temp_flat_net2pinX[jx+1];
                        temp_flat_net2pinX[jx+1] = net2pinVal;
                    }

                    //Sort Y
                    if (temp_flat_net2pinY[jx] > temp_flat_net2pinY[jx+1])
                    {
                        int tempVal = tempY[jx];
                        tempY[jx] = tempY[jx+1];
                        tempY[jx+1] = tempVal;

                        T net2pinVal = temp_flat_net2pinY[jx];
                        temp_flat_net2pinY[jx] = temp_flat_net2pinY[jx+1];
                        temp_flat_net2pinY[jx+1] = net2pinVal;
                    }
                }
            }

            //Assign sorted values back
            tempId = 0;
            for (int pId = pinIdxBeg; pId < pinIdxEnd; ++pId)
            {
                net_pinIdArrayX[pId] = tempX[tempId];
                net_pinIdArrayY[pId] = tempY[tempId];
                ++tempId;
            }
        }
        i += blockDim.x * gridDim.x;
    }
}

//TODO-Remove is_mlab_node when MLABs are treated separately
//Preclustering to handle carry chains and mlabs
template <typename T>
__global__ void preClustering(
        const T* pos_x,
        const T* pos_y,
        const T* pin_offset_x,
        const T* pin_offset_y,
        const int* sorted_node_map,
        const int* sorted_node_idx,
        const int* flat_net2pin_start_map,
        const int* flat_net2pin_map,
        const int* flop2ctrlSetId_map,
        const int* flop_ctrlSets,
        const int* node2fence_region_map,
        const int* node2outpinIdx_map,
        const int* pin2net_map,
        const int* pin2node_map,
        const int* pin_typeIds,
        const int* is_mlab_node,
        const T preClusteringMaxDist,
        const int lutId,
        const int ffId,
        const int num_nodes,
        int* flat_node2precluster_map,
        int* flat_node2prclstrCount)
{
    int i = threadIdx.x + blockDim.x * blockIdx.x;
    //const int blk = blockDim.x * gridDim.x;
    while (i < num_nodes)
    {
        const int idx = sorted_node_idx[i];
        //Only consider LUTs and skip MLABs
        if (node2fence_region_map[idx] == lutId && is_mlab_node[idx] == 0)
        {
            int ff_insts[SLICE_MAX_CAP];
            T ff_dists[SLICE_MAX_CAP];
            int ffIdx = 0;
            int nPIdx = idx*4;

            for (int nodeOutId = nPIdx; nodeOutId < nPIdx+4; ++nodeOutId)
            {
                int outPinId = node2outpinIdx_map[nodeOutId];
                if (outPinId == INVALID) continue;

                int outNetId = pin2net_map[outPinId];

                int pinIdxBeg = flat_net2pin_start_map[outNetId];
                int pinIdxEnd = flat_net2pin_start_map[outNetId+1];

                T instLocX = pos_x[idx] + pin_offset_x[outPinId];
                T instLocY = pos_y[idx] + pin_offset_y[outPinId];

                for (int pinId = pinIdxBeg; pinId < pinIdxEnd; ++pinId)
                {
                    int pinIdx = flat_net2pin_map[pinId];
                    int nodeIdx = pin2node_map[pinIdx];

                    T distX = instLocX - pos_x[nodeIdx] - pin_offset_x[pinIdx];
                    T distY = instLocY - pos_y[nodeIdx] - pin_offset_y[pinIdx];

                    T dist = DREAMPLACE_STD_NAMESPACE::abs(distX) + 
                        DREAMPLACE_STD_NAMESPACE::abs(distY);

                    if (pin_typeIds[pinIdx] == INPUT_PIN &&
                            node2fence_region_map[nodeIdx] == ffId &&
                            dist < preClusteringMaxDist)
                    {
                        ff_insts[ffIdx] = nodeIdx;
                        ff_dists[ffIdx] = dist;
                        ++ffIdx;
                    }
                }
            }

            //Check if ff is empty
            if (ffIdx > 0)
            {
                //Sort ff_insts/ff_dists based on dist and sorted_node_map
                for (int ix = 1; ix < ffIdx; ++ix)
                {
                    for (int jx = 0; jx < ffIdx-1; ++jx)
                    {
                        if (ff_dists[jx] == ff_dists[jx+1])
                        {
                            if (sorted_node_map[ff_insts[jx]] > sorted_node_map[ff_insts[jx+1]])
                            {
                                int tempVal = ff_insts[jx];
                                ff_insts[jx] = ff_insts[jx+1];
                                ff_insts[jx+1] = tempVal;

                                T distVal = ff_dists[jx];
                                ff_dists[jx] = ff_dists[jx+1];
                                ff_dists[jx+1] = distVal;
                            }
                        } else
                        {
                            if (ff_dists[jx] > ff_dists[jx+1])
                            {
                                int tempVal = ff_insts[jx];
                                ff_insts[jx] = ff_insts[jx+1];
                                ff_insts[jx+1] = tempVal;

                                T distVal = ff_dists[jx];
                                ff_dists[jx] = ff_dists[jx+1];
                                ff_dists[jx+1] = distVal;
                            }
                        }
                    }
                }

                int nPIdx = idx*3;

                flat_node2precluster_map[nPIdx + flat_node2prclstrCount[idx]] = ff_insts[0];
                ++flat_node2prclstrCount[idx];

                int fcIdx = flop2ctrlSetId_map[ff_insts[0]]*3 + 1;
                int cksr = flop_ctrlSets[fcIdx];

                for (int fIdx = 1; fIdx < ffIdx; ++fIdx)
                {
                    int ctrlIdx = flop2ctrlSetId_map[ff_insts[fIdx]]*3 + 1;
                    int fCksr = flop_ctrlSets[ctrlIdx];

                    if (fCksr == cksr)
                    {
                        flat_node2precluster_map[nPIdx + flat_node2prclstrCount[idx]] = ff_insts[fIdx];
                        ++flat_node2prclstrCount[idx];
                        break;
                    }
                }

                //Sort precluster based on idx 
                for (int ix = nPIdx+1; ix < nPIdx + flat_node2prclstrCount[idx]; ++ix)
                {
                    for (int jx = nPIdx; jx < nPIdx + flat_node2prclstrCount[idx]-1; ++jx)
                    {
                        if (sorted_node_map[flat_node2precluster_map[jx]] > sorted_node_map[flat_node2precluster_map[jx+1]])
                        {
                            int val = flat_node2precluster_map[jx];
                            flat_node2precluster_map[jx] = flat_node2precluster_map[jx+1];
                            flat_node2precluster_map[jx+1] = val;
                        }
                    }
                }

                for (int prcl = 0; prcl < flat_node2prclstrCount[idx]; ++prcl)
                {
                    int fIdx = flat_node2precluster_map[nPIdx + prcl];
                    int fID = fIdx*3;
                    if (fIdx != idx)
                    {
                        for (int cl = 0; cl < flat_node2prclstrCount[idx]; ++cl)
                        {
                            flat_node2precluster_map[fID + cl] = flat_node2precluster_map[nPIdx + cl];
                        }
                        flat_node2prclstrCount[fIdx] = flat_node2prclstrCount[idx];
                    }
                }
            }
        }
        i += blockDim.x * gridDim.x;
    }
}

//runDLIteration
template <typename T>
__global__ void runDLIteration(
        const T* pos_x,
        const T* pos_y,
        const T* pin_offset_x,
        const T* pin_offset_y,
        const T* net_bbox,
        const T* site_xy,
        const int* net_pinIdArrayX,
        const int* net_pinIdArrayY,
        const int* node2fence_region_map,
        const int* flop2ctrlSetId_map,
        const int* flop_ctrlSets,
        const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map,
        const int* lut_type,
        const int* flat_node2pin_start_map,
        const int* flat_node2pin_map,
        const int* node2outpinIdx_map,
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
        const T* net_weights,
        const int* addr2site_map,
        const int* special_nodes,
        const int num_clb_sites,
        const int minStableIter,
        const int maxList,
        const int half_ctrl_mode,
        const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY,
        const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE,
        const int minNeighbors,
        const int intMinVal,
        const int numGroups,
        const int netShareScoreMaxNetDegree,
        const int wlscoreMaxNetDegree,
        const int lutTypeInSliceUnit,
        const int lut_maxShared,
        const T xWirelenWt,
        const T yWirelenWt,
        const T wirelenImprovWt,
        const T extNetCountWt,
        const int CKSR_IN_CLB,
        const int CE_IN_CLB,
        const int SCL_IDX,
        const int PQ_IDX,
        const int SIG_IDX,
        const int lutId,
        const int ffId,
        int* validIndices_curr_scl,
        int* site_nbr_idx,
        int* site_nbr,
        int* site_nbrGroup_idx,
        int* site_curr_pq_top_idx,
        int* site_curr_pq_validIdx,
        int* site_curr_pq_sig_idx,
        int* site_curr_pq_sig,
        int* site_curr_pq_idx,
        int* site_curr_stable,
        int* site_curr_pq_siteId,
        T* site_curr_pq_score,
        int* site_curr_pq_impl_lut,
        int* site_curr_pq_impl_ff,
        int* site_curr_pq_impl_cksr,
        int* site_curr_pq_impl_ce,
        T* site_curr_scl_score,
        int* site_curr_scl_siteId,
        int* site_curr_scl_idx,
        int* site_curr_scl_validIdx,
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
        int* inst_curr_bestSite,
        int* inst_next_detSite,
        T* inst_next_bestScoreImprov,
        int* inst_next_bestSite,
        int* inst_score_improv,
        int* site_score_improv
        )
{
    for (int sIdx = threadIdx.x + blockDim.x * blockIdx.x;
                sIdx < num_clb_sites; sIdx += blockDim.x*gridDim.x)
    {
        int siteId = addr2site_map[sIdx];
        int numNbrGroups = (site_nbrRanges_idx[sIdx] == 0) ? 0 : site_nbrRanges_idx[sIdx]-1;

        int sPQ(sIdx*PQ_IDX), sSCL(sIdx*SCL_IDX), sNbrIdx(sIdx*maxList);
        int sdtopId = sIdx*SIG_IDX;
        int sdlutId = sIdx*SLICE_CAPACITY;
        int sdckId = sIdx*CKSR_IN_CLB;
        int sdceId = sIdx*CE_IN_CLB;

        int sclSigId = sSCL*SIG_IDX;
        int scllutIdx = sSCL*SLICE_CAPACITY;
        int sclckIdx = sSCL*CKSR_IN_CLB;
        int sclceIdx = sSCL*CE_IN_CLB;

        //(a)Try to commit Top candidates
        char commitTopCandidate(INVALID);

        int tsPQ(sPQ + site_curr_pq_top_idx[sIdx]);
        int topIdx(tsPQ*SIG_IDX);
        int lutIdx = tsPQ*SLICE_CAPACITY;
        int ckIdx = tsPQ*CKSR_IN_CLB;
        int ceIdx = tsPQ*CE_IN_CLB;

        if (site_curr_pq_idx[sIdx] == 0 || site_curr_stable[sIdx] < minStableIter ||
                !candidate_validity_check(is_mlab_node, SLICE_CAPACITY, topIdx,
                    site_curr_pq_sig_idx[tsPQ], site_curr_pq_siteId[tsPQ],
                    site_curr_pq_sig, inst_curr_detSite))
        {
            commitTopCandidate = 0;
        } else {

            for (int pIdx = 0; pIdx < site_curr_pq_sig_idx[tsPQ]; ++pIdx)
            {
                int pqInst = site_curr_pq_sig[topIdx + pIdx];

                if (inst_curr_detSite[pqInst] != siteId &&
                    inst_curr_bestSite[pqInst] != siteId)
                {
                    commitTopCandidate = 0;
                    break;
                }
            }
        }

        if (commitTopCandidate == INVALID)
        {
            //////
            site_det_score[sIdx] = site_curr_pq_score[tsPQ];
            site_det_siteId[sIdx] = site_curr_pq_siteId[tsPQ];
            site_det_sig_idx[sIdx] = site_curr_pq_sig_idx[tsPQ];

            for(int sg = 0; sg < site_curr_pq_sig_idx[tsPQ]; ++sg)
            {
                site_det_sig[sdtopId + sg] = site_curr_pq_sig[topIdx + sg];
            }
            for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
            {
                site_det_impl_lut[sdlutId + sg] = site_curr_pq_impl_lut[lutIdx + sg];
                site_det_impl_ff[sdlutId + sg] = site_curr_pq_impl_ff[lutIdx + sg];
            }
            for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
            {
                site_det_impl_cksr[sdckId + sg] = site_curr_pq_impl_cksr[ckIdx + sg];
            }
            for(int sg = 0; sg < CE_IN_CLB; ++sg)
            {
                site_det_impl_ce[sdceId + sg] = site_curr_pq_impl_ce[ceIdx + sg];
            }
            //////

            for(int iSig = 0; iSig < site_det_sig_idx[sIdx]; ++iSig)
            {
                int sigInst = site_det_sig[sdtopId + iSig];
                inst_next_detSite[sigInst] = siteId;
            }

            //Remove Incompatible Neighbors
            remove_incompatible_neighbors(node2outpinIdx_map, node2fence_region_map, lut_type,
                flat_node2pin_start_map, flat_node2pin_map, pin2net_map, pin_typeIds,
                flat_node2prclstrCount, flat_node2precluster_map, flop2ctrlSetId_map,
                flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map, site_det_impl_lut,
                site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce, site_det_sig,
                site_det_sig_idx, special_nodes, lutTypeInSliceUnit, lut_maxShared, sIdx,
                sNbrIdx, half_ctrl_mode, SLICE_CAPACITY, HALF_SLICE_CAPACITY, BLE_CAPACITY,
                NUM_BLE_PER_SLICE, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, lutId, ffId,
                site_nbr_idx, site_nbr);

            //Clear pq and make scl only contain the committed candidate
            //int sclCount = 0;
            for (int vId = 0; vId < PQ_IDX; ++vId)
            {
                int nPQId = sPQ + vId;
                //if (site_next_pq_validIdx[nPQId] != INVALID)
                //{
                //Clear contents thoroughly
                clear_cand_contents(
                        nPQId, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                        site_next_pq_sig_idx, site_next_pq_sig,
                        site_next_pq_impl_lut, site_next_pq_impl_ff,
                        site_next_pq_impl_cksr, site_next_pq_impl_ce);

                site_next_pq_validIdx[nPQId] = INVALID;
                site_next_pq_sig_idx[nPQId] = 0;
                site_next_pq_siteId[nPQId] = INVALID;
                site_next_pq_score[nPQId] = T(0.0);
                //++sclCount;
                //if (sclCount == site_next_pq_idx[sIdx])
                //{
                //    break;
                //}
                //}
            }
            site_next_pq_idx[sIdx] = 0;
            site_next_pq_top_idx[sIdx] = INVALID;

            int sclCount = 0;
            for (int vId = 0; vId < SCL_IDX; ++vId)
            {
                int cSclId = sSCL + vId;
                if (site_curr_scl_validIdx[cSclId] != INVALID)
                {
                    //Clear contents thoroughly
                    clear_cand_contents(
                            cSclId, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                            site_curr_scl_sig_idx, site_curr_scl_sig,
                            site_curr_scl_impl_lut, site_curr_scl_impl_ff,
                            site_curr_scl_impl_cksr, site_curr_scl_impl_ce);

                    site_curr_scl_validIdx[cSclId] = INVALID;
                    site_curr_scl_sig_idx[cSclId] = 0;
                    site_curr_scl_siteId[cSclId] = INVALID;
                    site_curr_scl_score[cSclId] = 0.0;
                    ++sclCount;
                    if (sclCount == site_curr_scl_idx[sIdx])
                    {
                        break;
                    }
                }
            }
            site_curr_scl_idx[sIdx] = 0;

            site_curr_scl_score[sSCL] = site_det_score[sIdx];
            site_curr_scl_siteId[sSCL] = site_det_siteId[sIdx];
            site_curr_scl_sig_idx[sSCL] = site_det_sig_idx[sIdx];
            site_curr_scl_validIdx[sSCL] = 1;

            for(int sg = 0; sg < site_det_sig_idx[sIdx]; ++sg)
            {
                site_curr_scl_sig[sclSigId + sg] = site_det_sig[sdtopId + sg];
            }
            for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
            {
                site_curr_scl_impl_lut[scllutIdx + sg] = site_det_impl_lut[sdlutId + sg];
                site_curr_scl_impl_ff[scllutIdx + sg] = site_det_impl_ff[sdlutId + sg];
            }
            for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
            {
                site_curr_scl_impl_cksr[sclckIdx + sg] = site_det_impl_cksr[sdckId + sg];
            }
            for(int sg = 0; sg < CE_IN_CLB; ++sg)
            {
                site_curr_scl_impl_ce[sclceIdx + sg] = site_det_impl_ce[sdceId + sg];
            }
            ++site_curr_scl_idx[sIdx];
            /////
            commitTopCandidate = 1;
        }

        if (commitTopCandidate == 0)
        {
            //Remove invalid candidates from site PQ
            if (site_next_pq_idx[sIdx] > 0)
            {
                //int snCnt = 0;
                //int maxEntries = site_next_pq_idx[sIdx];
                for (int nIdx = 0; nIdx < PQ_IDX; ++nIdx)
                {
                    int ssPQ = sPQ + nIdx;
                    int tpIdx = ssPQ*SIG_IDX;

                    if (site_next_pq_validIdx[ssPQ] != INVALID)
                    {
                        if (!candidate_validity_check(is_mlab_node, SLICE_CAPACITY, tpIdx,
                                site_next_pq_sig_idx[ssPQ], site_next_pq_siteId[ssPQ],
                                site_next_pq_sig, inst_curr_detSite))
                        {
                            //Clear contents thoroughly
                            clear_cand_contents(
                                    ssPQ, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                                    site_next_pq_sig_idx, site_next_pq_sig,
                                    site_next_pq_impl_lut, site_next_pq_impl_ff,
                                    site_next_pq_impl_cksr, site_next_pq_impl_ce);

                            site_next_pq_validIdx[ssPQ] = INVALID;
                            site_next_pq_sig_idx[ssPQ] = 0;
                            site_next_pq_siteId[ssPQ] = INVALID;
                            site_next_pq_score[ssPQ] = 0.0;
                            --site_next_pq_idx[sIdx];
                        }
                        //++snCnt;
                        //if (snCnt == maxEntries)
                        //{
                        //    break;
                        //}
                    }
                }

                site_next_pq_top_idx[sIdx] = INVALID;

                if (site_next_pq_idx[sIdx] > 0)
                {
                    int snCnt = 0;
                    int maxEntries = site_next_pq_idx[sIdx];
                    T maxScore(-1000.0);
                    int maxScoreId(INVALID);
                    //Recompute top idx
                    for (int nIdx = 0; nIdx < PQ_IDX; ++nIdx)
                    {
                        int ssPQ = sPQ + nIdx;
                        if (site_next_pq_validIdx[ssPQ] != INVALID)
                        {
                            if (site_next_pq_score[ssPQ] > maxScore)
                            {
                                maxScore = site_next_pq_score[ssPQ];
                                maxScoreId = nIdx;
                            }
                            ++snCnt;
                            if (snCnt == maxEntries)
                            {
                                break;
                            }
                        }
                    }
                    site_next_pq_top_idx[sIdx] = maxScoreId;
                }
            }

            //Remove invalid candidates from seed candidate list (scl)
            if (site_curr_scl_idx[sIdx] > 0)
            {
                int sclCount = 0;
                int maxEntries = site_curr_scl_idx[sIdx];
                for (int nIdx = 0; nIdx < SCL_IDX; ++nIdx)
                {
                    int ssPQ = sSCL + nIdx;
                    int tpIdx = ssPQ*SIG_IDX;

                    if (site_curr_scl_validIdx[ssPQ] != INVALID)
                    {
                        if (!candidate_validity_check(is_mlab_node, SLICE_CAPACITY, tpIdx,
                                site_curr_scl_sig_idx[ssPQ], site_curr_scl_siteId[ssPQ],
                                site_curr_scl_sig, inst_curr_detSite))
                        {
                            //Clear contents thoroughly
                            clear_cand_contents(
                                    ssPQ, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                                    site_curr_scl_sig_idx, site_curr_scl_sig,
                                    site_curr_scl_impl_lut, site_curr_scl_impl_ff,
                                    site_curr_scl_impl_cksr, site_curr_scl_impl_ce);

                            site_curr_scl_validIdx[ssPQ] = INVALID;
                            site_curr_scl_sig_idx[ssPQ] = 0;
                            site_curr_scl_siteId[ssPQ] = INVALID;
                            site_curr_scl_score[ssPQ] = 0.0;
                            --site_curr_scl_idx[sIdx];
                        }
                        ++sclCount;
                        if (sclCount == maxEntries)
                        {
                            break;
                        }
                    }
                }
            }
            //If site.scl becomes empty, add site.det into it as the seed
            if (site_curr_scl_idx[sIdx] == 0)
            {

                //site.curr.scl.emplace_back(site.det);
                site_curr_scl_score[sSCL] = site_det_score[sIdx];
                site_curr_scl_siteId[sSCL] = site_det_siteId[sIdx];
                site_curr_scl_sig_idx[sSCL] = site_det_sig_idx[sIdx];
                site_curr_scl_validIdx[sSCL] = 1;

                for(int sg = 0; sg < site_det_sig_idx[sIdx]; ++sg)
                {
                    site_curr_scl_sig[sclSigId + sg] = site_det_sig[sdtopId + sg];
                }
                for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                {
                    site_curr_scl_impl_lut[scllutIdx + sg] = site_det_impl_lut[sdlutId + sg];
                    site_curr_scl_impl_ff[scllutIdx + sg] = site_det_impl_ff[sdlutId + sg];
                }
                for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                {
                    site_curr_scl_impl_cksr[sclckIdx + sg] = site_det_impl_cksr[sdckId + sg];
                }
                for(int sg = 0; sg < CE_IN_CLB; ++sg)
                {
                    site_curr_scl_impl_ce[sclceIdx + sg] = site_det_impl_ce[sdceId + sg];
                }
                ++site_curr_scl_idx[sIdx];
            }
        }

        // (c) removeCommittedNeighbors(site)
        for (int sNIdx = 0; sNIdx < site_nbr_idx[sIdx]; ++sNIdx)
        {
            int siteInst = site_nbr[sNbrIdx + sNIdx];
            if (inst_curr_detSite[siteInst] != INVALID)
            {
                site_nbr[sNbrIdx + sNIdx] = INVALID;
            }
        }
        remove_invalid_neighbor(sIdx, sNbrIdx, site_nbr_idx, site_nbr);

        // (d) addNeighbors(site)
        ////reuse site_nbrGroup_idx to store the Ids for STAGGERED NEW CANDIDATE ADDITION 
        int maxNeighbors = site_nbrRanges[sIdx*(numGroups+1) + numGroups];
        if (site_nbr_idx[sIdx] < minNeighbors && site_nbrGroup_idx[sIdx] <= maxNeighbors)
        {
            int beg = site_nbrGroup_idx[sIdx];
            ////STAGGERED ADDITION SET TO SLICE/16 or SLICE_CAPACITY/8
            ///For ISPD'2016 benchmarks, SLICE=32 and SLICE_CAPACITY=16
            int end = DREAMPLACE_STD_NAMESPACE::min(site_nbrGroup_idx[sIdx]+SLICE_CAPACITY/8, maxNeighbors);
            site_nbrGroup_idx[sIdx] = end;

            for (int aNIdx = beg; aNIdx < end; ++aNIdx)
            {
                int instId = site_nbrList[sNbrIdx + aNIdx];

                if (inst_curr_detSite[instId] == INVALID && 
                    is_inst_in_cand_feasible(node2outpinIdx_map, node2fence_region_map,
                        lut_type, flat_node2pin_start_map, flat_node2pin_map,
                        pin2net_map, pin_typeIds, flat_node2prclstrCount,
                        flat_node2precluster_map, flop2ctrlSetId_map, flop_ctrlSets,
                        extended_ctrlSets, ext_ctrlSet_start_map, site_det_impl_lut,
                        site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce,
                        special_nodes, lutTypeInSliceUnit, lut_maxShared, sIdx, instId,
                        SLICE_CAPACITY, HALF_SLICE_CAPACITY, BLE_CAPACITY,
                        NUM_BLE_PER_SLICE, CKSR_IN_CLB, CE_IN_CLB, lutId, ffId, half_ctrl_mode))
                {
                    site_nbr[sNbrIdx + site_nbr_idx[sIdx]] = site_nbrList[sNbrIdx + aNIdx]; 
                    ++site_nbr_idx[sIdx];
                }
            }
        }

        //Generate indices for kernel_2
        int validId = 0;
        for (int scsIdx = 0; scsIdx < SCL_IDX; ++scsIdx)
        {
            int siteCurrIdx = sSCL + scsIdx;
            if (site_curr_scl_validIdx[siteCurrIdx] != INVALID)
            {
                validIndices_curr_scl[sSCL+validId] = siteCurrIdx;
                ++validId;
            }
            if (validId == site_curr_scl_idx[sIdx]) break;
        }

        // (e) createNewCandidates(site)
        //Generate new candidates by merging site_nbr to site_curr_scl

        const int limit_x = site_curr_scl_idx[sIdx];
        const int limit_y = site_nbr_idx[sIdx];
        ////RESTRICTED NEW CANDIDATE EXPLORATION SET TO SLICE/8 or SLICE_CAPACITY/4
        const int limit_cands = DREAMPLACE_STD_NAMESPACE::min(SLICE_CAPACITY/4,limit_x*limit_y);

        for (int scsIdx = 0; scsIdx < limit_cands; ++scsIdx)
        {
            int sclId = scsIdx/limit_y;
            int snIdx = scsIdx/limit_x;
            int siteCurrIdx = validIndices_curr_scl[sSCL + sclId];

            /////
            int sCKRId = siteCurrIdx*CKSR_IN_CLB;
            int sCEId = siteCurrIdx*CE_IN_CLB;
            int sFFId = siteCurrIdx*SLICE_CAPACITY;
            int sGId = siteCurrIdx*SIG_IDX;

            T nwCand_score = site_curr_scl_score[siteCurrIdx];
            int nwCand_siteId = site_curr_scl_siteId[siteCurrIdx];
            int nwCand_sigIdx = site_curr_scl_sig_idx[siteCurrIdx];

            //array instantiation
            int nwCand_sig[SIG_MAX_CAP];
            int nwCand_lut[SLICE_MAX_CAP];
            int nwCand_ff[SLICE_MAX_CAP];
            int nwCand_ce[CE_MAX_CAP];
            int nwCand_cksr[CKSR_MAX_CAP];

            for (int sg = 0; sg < nwCand_sigIdx; ++sg)
            {
                nwCand_sig[sg] = site_curr_scl_sig[sGId + sg];
            }
            for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
            {
                nwCand_lut[sg] = site_curr_scl_impl_lut[sFFId + sg];
                nwCand_ff[sg] = site_curr_scl_impl_ff[sFFId + sg];
            }
            for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
            {
                nwCand_cksr[sg] = site_curr_scl_impl_cksr[sCKRId + sg];
            }
            for (int sg = 0; sg < CE_IN_CLB; ++sg)
            {
                nwCand_ce[sg] = site_curr_scl_impl_ce[sCEId + sg];
            }

            int instId = site_nbr[sNbrIdx + snIdx];
            int instPcl = instId*3;

            int addInstToSig = INVALID;
            if (nwCand_sigIdx >= 2*SLICE_CAPACITY)
            {
                addInstToSig = 0;
            }

            if (addInstToSig == INVALID)
            {
                int temp[4]; //Max precluster size = 3
                int tIdx(0);

                for (int el = 0; el < flat_node2prclstrCount[instId]; ++el)
                {
                    int newInstId = flat_node2precluster_map[instPcl+el];
                    if (!val_in_array(nwCand_sig, nwCand_sigIdx, 0, newInstId))
                    {
                        temp[tIdx] = newInstId;
                        ++tIdx;
                    } else
                    {
                        addInstToSig = 0;
                        break;
                    }
                }

                if (addInstToSig == INVALID && (nwCand_sigIdx + tIdx > 2*SLICE_CAPACITY))
                {
                    addInstToSig = 0;
                }

                if (addInstToSig == INVALID)
                {
                    for (int mBIdx = 0; mBIdx < tIdx; ++mBIdx)
                    {
                        nwCand_sig[nwCand_sigIdx] = temp[mBIdx];
                        ++nwCand_sigIdx;
                    }
                    addInstToSig = 1;
                }
            }

            if (addInstToSig == 1)
            {
                //check cand sig is in site_next_pq
                int candSigInSiteNextPQ = INVALID;
                //int cnt = 0;
                for (int i = 0; i < PQ_IDX; ++i)
                {
                    int sigIdx = sPQ + i;
                    if (site_next_pq_validIdx[sigIdx] != INVALID)
                    {
                        if (site_next_pq_sig_idx[sigIdx] == nwCand_sigIdx)
                        {
                            int pqIdx(sigIdx*SIG_IDX), mtch(0);

                            for (int k = 0; k < nwCand_sigIdx; ++k)
                            {
                                for (int l = 0; l < nwCand_sigIdx; ++l)
                                {
                                    if (site_next_pq_sig[pqIdx + l] == nwCand_sig[k])
                                    {
                                        ++mtch;
                                        break;
                                    }
                                }
                            }
                            if (mtch == nwCand_sigIdx)
                            {
                                candSigInSiteNextPQ = 1;
                                break;
                            }
                        }
                    }
                }

                if (candSigInSiteNextPQ == INVALID &&
                    add_inst_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map,
                        flat_node2pin_map, pin2net_map, pin_typeIds, flat_node2prclstrCount,
                        flat_node2precluster_map, flop2ctrlSetId_map, node2fence_region_map,
                        flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map, special_nodes,
                        lutTypeInSliceUnit, lut_maxShared, instId, lutId, ffId, half_ctrl_mode,
                        CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY, HALF_SLICE_CAPACITY, BLE_CAPACITY,
                        NUM_BLE_PER_SLICE, nwCand_lut, nwCand_ff, nwCand_cksr, nwCand_ce))
                {
                    compute_candidate_score(pos_x, pos_y, pin_offset_x, pin_offset_y,
                        net_bbox, net_weights, site_xy, net_pinIdArrayX, net_pinIdArrayY,
                        flat_net2pin_start_map, flat_node2pin_start_map, flat_node2pin_map,
                        sorted_net_map, pin2net_map, pin2node_map, net2pincount, lut_type,
                        xWirelenWt, yWirelenWt, extNetCountWt, wirelenImprovWt,
                        netShareScoreMaxNetDegree, wlscoreMaxNetDegree, half_ctrl_mode,
                        nwCand_sig, nwCand_siteId, nwCand_sigIdx, nwCand_score);

                    int nxtId(INVALID);

                    if (site_next_pq_idx[sIdx] < PQ_IDX)
                    {
                        for (int vId = 0; vId < PQ_IDX; ++vId)
                        {
                            if (site_next_pq_validIdx[sPQ+vId] == INVALID)
                            {
                                nxtId = vId;
                                ++site_next_pq_idx[sIdx];
                                break;
                            }
                        }
                    } else
                    {
                        //find least score and replace if current score is greater
                        T ckscore(nwCand_score);
                        for (int vId = 0; vId < PQ_IDX; ++vId)
                        {
                            if (ckscore > site_next_pq_score[sPQ + vId])
                            {
                                ckscore = site_next_pq_score[sPQ + vId]; 
                                nxtId = vId;
                            }
                        }
                    }

                    if (nxtId != INVALID)
                    {
                        int nTId = sPQ + nxtId;
                        int nCKRId = nTId*CKSR_IN_CLB;
                        int nCEId = nTId*CE_IN_CLB;
                        int nFFId = nTId*SLICE_CAPACITY;
                        int nSGId = nTId*SIG_IDX;

                        /////
                        site_next_pq_validIdx[nTId] = 1;
                        site_next_pq_score[nTId] = nwCand_score;
                        site_next_pq_siteId[nTId] = nwCand_siteId;
                        site_next_pq_sig_idx[nTId] = nwCand_sigIdx;

                        for (int sg = 0; sg < nwCand_sigIdx; ++sg)
                        {
                            site_next_pq_sig[nSGId + sg] = nwCand_sig[sg];
                        }
                        for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                        {
                            site_next_pq_impl_lut[nFFId + sg] = nwCand_lut[sg];
                            site_next_pq_impl_ff[nFFId + sg] = nwCand_ff[sg];
                        }
                        for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                        {
                            site_next_pq_impl_cksr[nCKRId + sg] = nwCand_cksr[sg];
                        }
                        for (int sg = 0; sg < CE_IN_CLB; ++sg)
                        {
                            site_next_pq_impl_ce[nCEId + sg] = nwCand_ce[sg];
                        }
                        /////

                        if (site_next_pq_idx[sIdx] == 1 || 
                                nwCand_score > site_next_pq_score[sPQ + site_next_pq_top_idx[sIdx]])
                        {
                            site_next_pq_top_idx[sIdx] = nxtId;
                        }

                        nxtId = INVALID;

                        if (site_next_scl_idx[sIdx] < SCL_IDX)
                        {
                            for (int vId = 0; vId < SCL_IDX; ++vId)
                            {
                                if (site_next_scl_validIdx[sSCL+vId] == INVALID)
                                {
                                    nxtId = vId;
                                    ++site_next_scl_idx[sIdx];
                                    break;
                                }
                            }
                        } else
                        {
                            //find least score and replace if current score is greater
                            T ckscore(nwCand_score);
                            for (int vId = 0; vId < SCL_IDX; ++vId)
                            {
                                if (ckscore > site_next_scl_score[sSCL+vId])
                                {
                                    ckscore = site_next_scl_score[sSCL+vId]; 
                                    nxtId = vId;
                                }
                            }
                        }

                        if (nxtId != INVALID)
                        {
                            /////
                            nTId = sSCL + nxtId;
                            nCKRId = nTId*CKSR_IN_CLB;
                            nCEId = nTId*CE_IN_CLB;
                            nFFId = nTId*SLICE_CAPACITY;
                            nSGId = nTId*SIG_IDX;

                            site_next_scl_validIdx[nTId] = 1;
                            site_next_scl_score[nTId] = nwCand_score;
                            site_next_scl_siteId[nTId] = nwCand_siteId;
                            site_next_scl_sig_idx[nTId] = nwCand_sigIdx;

                            for (int sg = 0; sg < nwCand_sigIdx; ++sg)
                            {
                                site_next_scl_sig[nSGId + sg] = nwCand_sig[sg];
                            }
                            for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                            {
                                site_next_scl_impl_lut[nFFId + sg] = nwCand_lut[sg];
                                site_next_scl_impl_ff[nFFId + sg] = nwCand_ff[sg];
                            }
                            for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                            {
                                site_next_scl_impl_cksr[nCKRId + sg] = nwCand_cksr[sg];
                            }
                            for (int sg = 0; sg < CE_IN_CLB; ++sg)
                            {
                                site_next_scl_impl_ce[nCEId + sg] = nwCand_ce[sg];
                            }
                            /////
                        }
                    }
                }
            }
        }

        //Remove all candidates in scl that is worse than the worst candidate in PQ
        if (site_next_pq_idx[sIdx] > 0)
        {
            //Find worst candidate in PQ
            T ckscore(site_next_pq_score[sPQ + site_next_pq_top_idx[sIdx]]);

            int sclCount = 0;
            for (int vId = 0; vId < PQ_IDX; ++vId)
            {
                int nPQId = sPQ + vId;
                if (site_next_pq_validIdx[nPQId] != INVALID)
                {
                    if (ckscore > site_next_pq_score[nPQId])
                    {
                        ckscore = site_next_pq_score[nPQId]; 
                    }
                    ++sclCount;
                    if (sclCount == site_next_pq_idx[sIdx])
                    {
                        break;
                    }
                }
            }

            //Invalidate worst ones in scl
            sclCount = 0;
            int maxEntries = site_next_scl_idx[sIdx];
            for (int ckId = 0; ckId < SCL_IDX; ++ckId)
            {
                int vId = sSCL + ckId;
                if (site_next_scl_validIdx[vId] != INVALID)
                {
                    if (ckscore > site_next_scl_score[vId])
                    {
                        //Clear contents thoroughly
                        clear_cand_contents(
                                vId, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                                site_next_scl_sig_idx, site_next_scl_sig,
                                site_next_scl_impl_lut, site_next_scl_impl_ff,
                                site_next_scl_impl_cksr, site_next_scl_impl_ce);

                        site_next_scl_validIdx[vId] = INVALID;
                        site_next_scl_sig_idx[vId] = 0;
                        site_next_scl_siteId[vId] = INVALID;
                        site_next_scl_score[vId] = 0.0;
                        --site_next_scl_idx[sIdx];
                    }
                    ++sclCount;
                    if (sclCount == maxEntries)
                    {
                        break;
                    }
                }
            }
        }

        //Update stable Iteration count
        if (site_curr_pq_idx[sIdx] > 0 && site_next_pq_idx[sIdx] > 0 && 
                compare_pq_tops(site_curr_pq_score, site_curr_pq_top_idx,
                    site_curr_pq_validIdx, site_curr_pq_siteId, site_curr_pq_sig_idx,
                    site_curr_pq_sig, site_curr_pq_impl_lut, site_curr_pq_impl_ff,
                    site_curr_pq_impl_cksr, site_curr_pq_impl_ce, site_next_pq_score,
                    site_next_pq_top_idx, site_next_pq_validIdx, site_next_pq_siteId,
                    site_next_pq_sig_idx, site_next_pq_sig, site_next_pq_impl_lut,
                    site_next_pq_impl_ff, site_next_pq_impl_cksr, site_next_pq_impl_ce,
                    sIdx, sPQ, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY))
        {
            site_next_stable[sIdx] = site_curr_stable[sIdx] + 1;
        } else
        {
            site_next_stable[sIdx] = 0;
        }

        //// (f) broadcastTopCandidate(site)
        if (site_next_pq_idx[sIdx] > 0)
        {
            int tpIdx = sPQ + site_next_pq_top_idx[sIdx];
            int topSigId = tpIdx*SIG_IDX;

            T scoreImprov = site_next_pq_score[tpIdx] - site_det_score[sIdx];

            ////UPDATED SEQUENTIAL PORTION
            int scoreImprovInt = DREAMPLACE_STD_NAMESPACE::max(int(scoreImprov*10000), intMinVal);
            site_score_improv[sIdx] = scoreImprovInt + siteId;

            for (int ssIdx = 0; ssIdx < site_next_pq_sig_idx[tpIdx]; ++ssIdx)
            {
                int instId = site_next_pq_sig[topSigId + ssIdx];

                if (inst_curr_detSite[instId] == INVALID)
                {
                    atomicMax(&inst_score_improv[instId], scoreImprovInt);
                }
            }
        }
    }
}

//runDLIteration split kernel 1
template <typename T>
__global__ void runDLIteration_kernel_1(
        const int* node2fence_region_map,
        const int* flop2ctrlSetId_map,
        const int* flop_ctrlSets,
        const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map,
        const int* lut_type,
        const int* flat_node2pin_start_map,
        const int* flat_node2pin_map,
        const int* node2outpinIdx_map,
        const int* pin2net_map,
        const int* pin_typeIds,
        const int* flat_node2prclstrCount,
        const int* flat_node2precluster_map,
        const int* is_mlab_node,
        const int* site_nbrList,
        const int* site_nbrRanges,
        const int* site_nbrRanges_idx,
        const int* addr2site_map,
        const int* special_nodes,
        const int num_clb_sites,
        const int minStableIter,
        const int maxList,
        const int half_ctrl_mode,
        const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY,
        const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE,
        const int minNeighbors,
        const int numGroups,
        const int lutTypeInSliceUnit, 
        const int lut_maxShared,
        const int CKSR_IN_CLB,
        const int CE_IN_CLB,
        const int SCL_IDX,
        const int PQ_IDX,
        const int SIG_IDX,
        const int lutId,
        const int ffId,
        int* site_nbr_idx,
        int* site_nbr,
        int* site_nbrGroup_idx,
        int* site_curr_pq_top_idx,
        int* site_curr_pq_sig_idx,
        int* site_curr_pq_sig,
        int* site_curr_pq_idx,
        int* site_curr_stable,
        int* site_curr_pq_siteId,
        T* site_curr_pq_score,
        int* site_curr_pq_impl_lut,
        int* site_curr_pq_impl_ff,
        int* site_curr_pq_impl_cksr,
        int* site_curr_pq_impl_ce,
        T* site_curr_scl_score,
        int* site_curr_scl_siteId,
        int* site_curr_scl_idx,
        int* site_curr_scl_validIdx,
        int* site_curr_scl_sig_idx,
        int* site_curr_scl_sig,
        int* site_curr_scl_impl_lut,
        int* site_curr_scl_impl_ff,
        int* site_curr_scl_impl_cksr,
        int* site_curr_scl_impl_ce,
        int* site_next_pq_idx,
        int* site_next_pq_validIdx,
        int* site_next_pq_top_idx,
        int* site_next_pq_impl_lut,
        int* site_next_pq_impl_ff,
        int* site_next_pq_impl_cksr,
        int* site_next_pq_impl_ce,
        T* site_next_pq_score,
        int* site_next_pq_siteId,
        int* site_next_pq_sig_idx,
        int* site_next_pq_sig,
        T* site_det_score,
        int* site_det_siteId,
        int* site_det_sig_idx,
        int* site_det_sig,
        int* site_det_impl_lut,
        int* site_det_impl_ff,
        int* site_det_impl_cksr,
        int* site_det_impl_ce,
        int* inst_curr_detSite,
        int* inst_curr_bestSite,
        int* inst_next_detSite,
        int* validIndices_curr_scl,
        int* cumsum_curr_scl
        )
{
    for (int sIdx = threadIdx.x + blockDim.x * blockIdx.x;
            sIdx < num_clb_sites; sIdx += blockDim.x*gridDim.x)
    {
        int siteId = addr2site_map[sIdx];
        int numNbrGroups = (site_nbrRanges_idx[sIdx] == 0) ? 0 : site_nbrRanges_idx[sIdx]-1;

        int sPQ(sIdx*PQ_IDX), sSCL(sIdx*SCL_IDX), sNbrIdx(sIdx*maxList);
        int sdtopId = sIdx*SIG_IDX;
        int sdlutId = sIdx*SLICE_CAPACITY;
        int sdckId = sIdx*CKSR_IN_CLB;
        int sdceId = sIdx*CE_IN_CLB;

        int sclSigId = sSCL*SIG_IDX;
        int scllutIdx = sSCL*SLICE_CAPACITY;
        int sclckIdx = sSCL*CKSR_IN_CLB;
        int sclceIdx = sSCL*CE_IN_CLB;

        //(a)Try to commit Top candidates
        int commitTopCandidate(INVALID);

        int tsPQ(sPQ + site_curr_pq_top_idx[sIdx]);
        int topIdx(tsPQ*SIG_IDX);
        int lutIdx = tsPQ*SLICE_CAPACITY;
        int ckIdx = tsPQ*CKSR_IN_CLB;
        int ceIdx = tsPQ*CE_IN_CLB;

        if (site_curr_pq_idx[sIdx] == 0 || site_curr_stable[sIdx] < minStableIter ||
                !candidate_validity_check(is_mlab_node, SLICE_CAPACITY, topIdx,
                    site_curr_pq_sig_idx[tsPQ], site_curr_pq_siteId[tsPQ],
                    site_curr_pq_sig, inst_curr_detSite))
        {
            commitTopCandidate = 0;
        } else {
            for (int pIdx = 0; pIdx < site_curr_pq_sig_idx[tsPQ]; ++pIdx)
            {
                int pqInst = site_curr_pq_sig[topIdx + pIdx];

                if (inst_curr_detSite[pqInst] != siteId &&
                    inst_curr_bestSite[pqInst] != siteId)
                {
                    commitTopCandidate = 0;
                    break;
                }
            }
        }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d has commitTopCandidate: %d\n", sIdx, siteId, commitTopCandidate);
        //}
        ////DBG

        if (commitTopCandidate == INVALID)
        {
            //////
            site_det_score[sIdx] = site_curr_pq_score[tsPQ];
            site_det_siteId[sIdx] = site_curr_pq_siteId[tsPQ];
            site_det_sig_idx[sIdx] = site_curr_pq_sig_idx[tsPQ];

            for(int sg = 0; sg < site_curr_pq_sig_idx[tsPQ]; ++sg)
            {
                site_det_sig[sdtopId + sg] = site_curr_pq_sig[topIdx + sg];
            }
            for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
            {
                site_det_impl_lut[sdlutId + sg] = site_curr_pq_impl_lut[lutIdx + sg];
                site_det_impl_ff[sdlutId + sg] = site_curr_pq_impl_ff[lutIdx + sg];
            }
            for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
            {
                site_det_impl_cksr[sdckId + sg] = site_curr_pq_impl_cksr[ckIdx + sg];
            }
            for(int sg = 0; sg < CE_IN_CLB; ++sg)
            {
                site_det_impl_ce[sdceId + sg] = site_curr_pq_impl_ce[ceIdx + sg];
            }
            //////

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d commitTopCandidate: %d assign site_curr pq top to site_det with sig size: %d\n", sIdx, siteId, commitTopCandidate, site_det_sig_idx[sIdx]);
        //}
        ////DBG

            for(int iSig = 0; iSig < site_det_sig_idx[sIdx]; ++iSig)
            {
                int sigInst = site_det_sig[sdtopId + iSig];
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d commitTopCandidate: %d assign sigInst %d to site \n", sIdx, siteId, commitTopCandidate, sigInst);
        //}
        ////DBG

                inst_next_detSite[sigInst] = siteId;
            }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d commitTopCandidate: %d update inst_next_detSite \n", sIdx, siteId, commitTopCandidate);
        //}
        ////DBG

            //Remove Incompatible Neighbors
            remove_incompatible_neighbors(node2outpinIdx_map, node2fence_region_map, lut_type,
                flat_node2pin_start_map, flat_node2pin_map, pin2net_map, pin_typeIds,
                flat_node2prclstrCount, flat_node2precluster_map, flop2ctrlSetId_map,
                flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map, site_det_impl_lut,
                site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce, site_det_sig,
                site_det_sig_idx, special_nodes, lutTypeInSliceUnit, lut_maxShared, sIdx,
                sNbrIdx, half_ctrl_mode, SLICE_CAPACITY, HALF_SLICE_CAPACITY, BLE_CAPACITY,
                NUM_BLE_PER_SLICE, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, lutId, ffId,
                site_nbr_idx, site_nbr);

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d commitTopCandidate: %d complete remove incompatible neighbors\n", sIdx, siteId, commitTopCandidate);
        //}
        ////DBG

            //Clear pq and make scl only contain the committed candidate
            //int sclCount = 0;
            for (int vId = 0; vId < PQ_IDX; ++vId)
            {
                int nPQId = sPQ + vId;
                //if (site_next_pq_validIdx[nPQId] != INVALID)
                //{
                //Clear contents thoroughly
                clear_cand_contents(
                        nPQId, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                        site_next_pq_sig_idx, site_next_pq_sig,
                        site_next_pq_impl_lut, site_next_pq_impl_ff,
                        site_next_pq_impl_cksr, site_next_pq_impl_ce);

                site_next_pq_validIdx[nPQId] = INVALID;
                site_next_pq_sig_idx[nPQId] = 0;
                site_next_pq_siteId[nPQId] = INVALID;
                site_next_pq_score[nPQId] = T(0.0);
                //++sclCount;
                //if (sclCount == site_next_pq_idx[sIdx])
                //{
                //    break;
                //}
                //}
            }
            site_next_pq_idx[sIdx] = 0;
            site_next_pq_top_idx[sIdx] = INVALID;

            int sclCount = 0;
            for (int vId = 0; vId < SCL_IDX; ++vId)
            {
                int cSclId = sSCL + vId;
                if (site_curr_scl_validIdx[cSclId] != INVALID)
                {
                    //Clear contents thoroughly
                    clear_cand_contents(
                            cSclId, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                            site_curr_scl_sig_idx, site_curr_scl_sig,
                            site_curr_scl_impl_lut, site_curr_scl_impl_ff,
                            site_curr_scl_impl_cksr, site_curr_scl_impl_ce);

                    site_curr_scl_validIdx[cSclId] = INVALID;
                    site_curr_scl_sig_idx[cSclId] = 0;
                    site_curr_scl_siteId[cSclId] = INVALID;
                    site_curr_scl_score[cSclId] = 0.0;
                    ++sclCount;
                    if (sclCount == site_curr_scl_idx[sIdx])
                    {
                        break;
                    }
                }
            }
            site_curr_scl_idx[sIdx] = 0;

            site_curr_scl_score[sSCL] = site_det_score[sIdx];
            site_curr_scl_siteId[sSCL] = site_det_siteId[sIdx];
            site_curr_scl_sig_idx[sSCL] = site_det_sig_idx[sIdx];
            site_curr_scl_validIdx[sSCL] = 1;

            for(int sg = 0; sg < site_det_sig_idx[sIdx]; ++sg)
            {
                site_curr_scl_sig[sclSigId + sg] = site_det_sig[sdtopId + sg];
            }
            for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
            {
                site_curr_scl_impl_lut[scllutIdx + sg] = site_det_impl_lut[sdlutId + sg];
                site_curr_scl_impl_ff[scllutIdx + sg] = site_det_impl_ff[sdlutId + sg];
            }
            for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
            {
                site_curr_scl_impl_cksr[sclckIdx + sg] = site_det_impl_cksr[sdckId + sg];
            }
            for(int sg = 0; sg < CE_IN_CLB; ++sg)
            {
                site_curr_scl_impl_ce[sclceIdx + sg] = site_det_impl_ce[sdceId + sg];
            }
            ++site_curr_scl_idx[sIdx];
            /////
            commitTopCandidate = 1;
        }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    //printf("%d Site %d: After possible commit has commitTopCandidate: %d\n", sIdx, siteId, commitTopCandidate);
        //    printf("%d Site %d: Completed (a)", sIdx, siteId);
        //}
        ////DBG

        if (commitTopCandidate == 0)
        {
            //(b) removeInvalidCandidates

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: commitTopCandidate %d with %d elements in next PQ\n", sIdx, siteId, commitTopCandidate, site_next_pq_idx[sIdx]);
        //}
        ////DBG

            //Remove invalid candidates from site PQ
            if (site_next_pq_idx[sIdx] > 0)
            {
                //int snCnt = 0;
                //int maxEntries = site_next_pq_idx[sIdx];
                for (int nIdx = 0; nIdx < PQ_IDX; ++nIdx)
                {
                    int ssPQ = sPQ + nIdx;
                    int tpIdx = ssPQ*SIG_IDX;

                    if (site_next_pq_validIdx[ssPQ] != INVALID)
                    {
                        if (!candidate_validity_check(is_mlab_node, SLICE_CAPACITY, tpIdx,
                                site_next_pq_sig_idx[ssPQ], site_next_pq_siteId[ssPQ],
                                site_next_pq_sig, inst_curr_detSite))
                        {
                            //Clear contents thoroughly
                            clear_cand_contents(
                                    ssPQ, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                                    site_next_pq_sig_idx, site_next_pq_sig,
                                    site_next_pq_impl_lut, site_next_pq_impl_ff,
                                    site_next_pq_impl_cksr, site_next_pq_impl_ce);

                            site_next_pq_validIdx[ssPQ] = INVALID;
                            site_next_pq_sig_idx[ssPQ] = 0;
                            site_next_pq_siteId[ssPQ] = INVALID;
                            site_next_pq_score[ssPQ] = 0.0;
                            --site_next_pq_idx[sIdx];
                        }
                        //++snCnt;
                        //if (snCnt == maxEntries)
                        //{
                        //    break;
                        //}
                    }
                }

                site_next_pq_top_idx[sIdx] = INVALID;

                if (site_next_pq_idx[sIdx] > 0)
                {
                    int snCnt = 0;
                    int maxEntries = site_next_pq_idx[sIdx];
                    T maxScore(-1000.0);
                    int maxScoreId(INVALID);
                    //Recompute top idx
                    for (int nIdx = 0; nIdx < PQ_IDX; ++nIdx)
                    {
                        int ssPQ = sPQ + nIdx;
                        if (site_next_pq_validIdx[ssPQ] != INVALID)
                        {
                            if (site_next_pq_score[ssPQ] > maxScore)
                            {
                                maxScore = site_next_pq_score[ssPQ];
                                maxScoreId = nIdx;
                            }
                            ++snCnt;
                            if (snCnt == maxEntries)
                            {
                                break;
                            }
                        }
                    }
                    site_next_pq_top_idx[sIdx] = maxScoreId;
                }
            }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: commitTopCandidate %d removed invalid candiates in next PQ with %d elements, site curr scl has %d elements \n",
        //            sIdx, siteId, commitTopCandidate, site_next_pq_idx[sIdx], site_curr_scl_idx[sIdx]);
        //}
        ////DBG

            //Remove invalid candidates from seed candidate list (scl)
            if (site_curr_scl_idx[sIdx] > 0)
            {
                int sclCount = 0;
                int maxEntries = site_curr_scl_idx[sIdx];
                for (int nIdx = 0; nIdx < SCL_IDX; ++nIdx)
                {
                    int ssPQ = sSCL + nIdx;
                    int tpIdx = ssPQ*SIG_IDX;
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: commitTopCandidate %d nIdx %d ssPQ %d tpIdx %d site_curr_scl_validIdx[ssPQ] %d\n",
        //            sIdx, siteId, commitTopCandidate, nIdx, ssPQ, tpIdx, site_curr_scl_validIdx[ssPQ]);
        //}
        ////DBG

                    if (site_curr_scl_validIdx[ssPQ] != INVALID)
                    {
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: commitTopCandidate %d ssPQ %d site_curr_scl_validIdx[ssPQ] %d, site_curr_scl_sig_idx[ssPQ] %d\n",
        //            sIdx, siteId, commitTopCandidate, ssPQ, site_curr_scl_validIdx[ssPQ], site_curr_scl_sig_idx[ssPQ]);
        //}
        ////DBG

                        if (!candidate_validity_check(is_mlab_node, SLICE_CAPACITY, tpIdx,
                                site_curr_scl_sig_idx[ssPQ], site_curr_scl_siteId[ssPQ],
                                site_curr_scl_sig, inst_curr_detSite))
                        {
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: commitTopCandidate %d ssPQ %d site_curr_scl_validIdx[ssPQ] %d before clear_cand_contents %d\n",
        //            sIdx, siteId, commitTopCandidate, ssPQ, site_curr_scl_validIdx[ssPQ]);
        //}
        ////DBG
                            //Clear contents thoroughly
                            clear_cand_contents(
                                    ssPQ, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                                    site_curr_scl_sig_idx, site_curr_scl_sig,
                                    site_curr_scl_impl_lut, site_curr_scl_impl_ff,
                                    site_curr_scl_impl_cksr, site_curr_scl_impl_ce);
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: commitTopCandidate %d ssPQ %d site_curr_scl_validIdx[ssPQ] %d after clear_cand_contents %d\n",
        //            sIdx, siteId, commitTopCandidate, ssPQ, site_curr_scl_validIdx[ssPQ]);
        //}
        ////DBG

                            site_curr_scl_validIdx[ssPQ] = INVALID;
                            site_curr_scl_sig_idx[ssPQ] = 0;
                            site_curr_scl_siteId[ssPQ] = INVALID;
                            site_curr_scl_score[ssPQ] = 0.0;
                            --site_curr_scl_idx[sIdx];
                        }
                        ++sclCount;
                        if (sclCount == maxEntries)
                        {
                            break;
                        }
                    }
                }
            }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: commitTopCandidate %d removed invalid candiates in site curr scl with %d elements \n",
        //            sIdx, siteId, commitTopCandidate, site_curr_scl_idx[sIdx]);
        //}
        ////DBG


            //If site.scl becomes empty, add site.det into it as the seed
            if (site_curr_scl_idx[sIdx] == 0)
            {

                site_curr_scl_score[sSCL] = site_det_score[sIdx];
                site_curr_scl_siteId[sSCL] = site_det_siteId[sIdx];
                site_curr_scl_sig_idx[sSCL] = site_det_sig_idx[sIdx];
                site_curr_scl_validIdx[sSCL] = 1;

                for(int sg = 0; sg < site_det_sig_idx[sIdx]; ++sg)
                {
                    site_curr_scl_sig[sclSigId + sg] = site_det_sig[sdtopId + sg];
                }
                for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                {
                    site_curr_scl_impl_lut[scllutIdx + sg] = site_det_impl_lut[sdlutId + sg];
                    site_curr_scl_impl_ff[scllutIdx + sg] = site_det_impl_ff[sdlutId + sg];
                }
                for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                {
                    site_curr_scl_impl_cksr[sclckIdx + sg] = site_det_impl_cksr[sdckId + sg];
                }
                for(int sg = 0; sg < CE_IN_CLB; ++sg)
                {
                    site_curr_scl_impl_ce[sclceIdx + sg] = site_det_impl_ce[sdceId + sg];
                }
                ++site_curr_scl_idx[sIdx];

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: commitTopCandidate %d add site det to site curr scl with %d elements \n",
        //            sIdx, siteId, commitTopCandidate, site_curr_scl_idx[sIdx]);
        //}
        ////DBG


            }
        }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: Completed (a) and (b) \n", sIdx, siteId);
        //}
        ////DBG

        // (c) removeCommittedNeighbors(site)

        for (int sNIdx = 0; sNIdx < site_nbr_idx[sIdx]; ++sNIdx)
        {
            int siteInst = site_nbr[sNbrIdx + sNIdx];
            if (inst_curr_detSite[siteInst] != INVALID)
            {
                site_nbr[sNbrIdx + sNIdx] = INVALID;
            }
        }
        remove_invalid_neighbor(sIdx, sNbrIdx, site_nbr_idx, site_nbr);

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: Completed (c) \n", sIdx, siteId);
        //}
        ////DBG

        // (d) addNeighbors(site)
        ////STAGGERED ADDITION OF NEW NEIGHBORS
        int maxNeighbors = site_nbrRanges[sIdx*(numGroups+1) + numGroups];
        if (site_nbr_idx[sIdx] < minNeighbors && 
            site_nbrGroup_idx[sIdx] <= maxNeighbors)
        {
            int beg = site_nbrGroup_idx[sIdx];
            ///STAGGERED ADDITION SET TO SLICE/16 or SLICE_CAPACITY/8
            int end = DREAMPLACE_STD_NAMESPACE::min(site_nbrGroup_idx[sIdx]+SLICE_CAPACITY/8, maxNeighbors);
            site_nbrGroup_idx[sIdx] = end;

            for (int aNIdx = beg; aNIdx < end; ++aNIdx)
            {
                int instId = site_nbrList[sNbrIdx + aNIdx];

                if (inst_curr_detSite[instId] == INVALID && 
                    is_inst_in_cand_feasible(node2outpinIdx_map, node2fence_region_map,
                        lut_type, flat_node2pin_start_map, flat_node2pin_map,
                        pin2net_map, pin_typeIds, flat_node2prclstrCount,
                        flat_node2precluster_map, flop2ctrlSetId_map, flop_ctrlSets,
                        extended_ctrlSets, ext_ctrlSet_start_map, site_det_impl_lut,
                        site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce, special_nodes,
                        lutTypeInSliceUnit, lut_maxShared, sIdx, instId, SLICE_CAPACITY,
                        HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE, CKSR_IN_CLB,
                        CE_IN_CLB, lutId, ffId, half_ctrl_mode))
                {
                    site_nbr[sNbrIdx + site_nbr_idx[sIdx]] = site_nbrList[sNbrIdx + aNIdx]; 
                    ++site_nbr_idx[sIdx];
                }
            }
        }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: Completed (d) New Neighbor addition \n", sIdx, siteId);
        //}
        ////DBG

        //Generate indices for kernel_2
        int validId = 0;
        for (int scsIdx = 0; scsIdx < SCL_IDX; ++scsIdx)
        {
            int siteCurrIdx = sSCL + scsIdx;
            if (site_curr_scl_validIdx[siteCurrIdx] != INVALID)
            {
                validIndices_curr_scl[sSCL+validId] = siteCurrIdx;
                ++validId;
            }
            if (validId == site_curr_scl_idx[sIdx]) break;
        }

        cumsum_curr_scl[sIdx] = site_curr_scl_idx[sIdx]*site_nbr_idx[sIdx];

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: Completed valid indices generation for kernel_2 \n", sIdx, siteId);
        //}
        ////DBG
    }
}

//runDLIteration split kernel 2
template <typename T>
__global__ void runDLIteration_kernel_2(
        const T* pos_x,
        const T* pos_y,
        const T* pin_offset_x,
        const T* pin_offset_y,
        const T* net_bbox,
        const T* site_xy,
        const T* net_weights,
        const int* net_pinIdArrayX,
        const int* net_pinIdArrayY,
        const int* node2fence_region_map,
        const int* flop2ctrlSetId_map,
        const int* flop_ctrlSets,
        const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map,
        const int* flat_net2pin_start_map,
        const int* flat_node2pin_start_map,
        const int* flat_node2pin_map,
        const int* node2outpinIdx_map,
        const int* lut_type,
        const int* net2pincount,
        const int* pin2net_map,
        const int* pin_typeIds,
        const int* pin2node_map,
        const int* sorted_node_map,
        const int* sorted_net_map,
        const int* flat_node2prclstrCount,
        const int* flat_node2precluster_map,
        const int* validIndices_curr_scl,
        const int* sorted_clb_siteIds,
        const int* addr2site_map,
        const int* special_nodes,
        const T xWirelenWt,
        const T yWirelenWt,
        const T wirelenImprovWt,
        const T extNetCountWt,
        const int num_clb_sites,
        const int intMinVal,
        const int maxList,
        const int half_ctrl_mode,
        const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY,
        const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE,
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
        int* site_nbr_idx,
        int* site_nbr,
        int* site_curr_pq_top_idx,
        int* site_curr_pq_validIdx,
        int* site_curr_pq_sig_idx,
        int* site_curr_pq_sig,
        int* site_curr_pq_impl_lut,
        int* site_curr_pq_impl_ff,
        int* site_curr_pq_impl_cksr,
        int* site_curr_pq_impl_ce,
        int* site_curr_pq_idx,
        int* site_curr_stable,
        int* site_curr_pq_siteId,
        T* site_curr_pq_score,
        T* site_curr_scl_score,
        int* site_curr_scl_siteId,
        int* site_curr_scl_idx,
        int* site_curr_scl_validIdx,
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
        int* inst_curr_detSite,
        T* inst_next_bestScoreImprov,
        int* inst_next_bestSite,
        int* inst_score_improv,
        int* site_score_improv
        )
{
    for (int sId = threadIdx.x + blockDim.x * blockIdx.x;
             sId < num_clb_sites; sId += blockDim.x*gridDim.x)
    {
        const int sIdx = sorted_clb_siteIds[sId];

        int siteId = addr2site_map[sIdx];

        int sPQ(sIdx*PQ_IDX), sSCL(sIdx*SCL_IDX), sNbrIdx(sIdx*maxList);

        // (e) createNewCandidates(site)
        //Generate new candidates by merging site_nbr to site_curr_scl
        const int limit_x = site_curr_scl_idx[sIdx];
        const int limit_y = site_nbr_idx[sIdx];
        ///RESTRICTED NEW CANDIDATE SPACE EXPLORATION SET TO SLICE/8 or SLICE_CAPACITY/4
        const int limit_cands = DREAMPLACE_STD_NAMESPACE::min(SLICE_CAPACITY/4,limit_x*limit_y);

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: has %d candidates\n", sIdx, siteId, limit_cands);
        //}
        ////DBG

        for (int scsIdx = 0; scsIdx < limit_cands; ++scsIdx)
        {
            int sclId = scsIdx/limit_y;
            int snIdx = scsIdx/limit_x;
            int siteCurrIdx = validIndices_curr_scl[sSCL + sclId];

            /////
            int sCKRId = siteCurrIdx*CKSR_IN_CLB;
            int sCEId = siteCurrIdx*CE_IN_CLB;
            int sFFId = siteCurrIdx*SLICE_CAPACITY;
            int sGId = siteCurrIdx*SIG_IDX;

            T nwCand_score = site_curr_scl_score[siteCurrIdx];
            int nwCand_siteId = site_curr_scl_siteId[siteCurrIdx];
            int nwCand_sigIdx = site_curr_scl_sig_idx[siteCurrIdx];

            //array instantiation
            int nwCand_sig[SIG_MAX_CAP];
            int nwCand_lut[SLICE_MAX_CAP];
            int nwCand_ff[SLICE_MAX_CAP];
            int nwCand_ce[CE_MAX_CAP];
            int nwCand_cksr[CKSR_MAX_CAP];

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: cand has %d sig elements\n", sIdx, siteId, nwCand_sigIdx);
        //}
        ////DBG

            for (int sg = 0; sg < nwCand_sigIdx; ++sg)
            {
                nwCand_sig[sg] = site_curr_scl_sig[sGId + sg];
            }
            for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
            {
                nwCand_lut[sg] = site_curr_scl_impl_lut[sFFId + sg];
                nwCand_ff[sg] = site_curr_scl_impl_ff[sFFId + sg];
            }
            for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
            {
                nwCand_cksr[sg] = site_curr_scl_impl_cksr[sCKRId + sg];
            }
            for (int sg = 0; sg < CE_IN_CLB; ++sg)
            {
                nwCand_ce[sg] = site_curr_scl_impl_ce[sCEId + sg];
            }

            int instId = site_nbr[sNbrIdx + snIdx];
            int instPcl = instId*3;

            int addInstToSig = INVALID;
            if (nwCand_sigIdx >= 2*SLICE_CAPACITY)
            {
                addInstToSig = 0;
            }

            if (addInstToSig == INVALID)
            {
                int temp[4]; //Max precluster size = 3
                int tIdx(0);
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: Inst %d has %d precluster count\n", sIdx, siteId, instId, flat_node2prclstrCount[instId]);
        //}
        ////DBG

                for (int el = 0; el < flat_node2prclstrCount[instId]; ++el)
                {
                    int newInstId = flat_node2precluster_map[instPcl+el];
                    if (!val_in_array(nwCand_sig, nwCand_sigIdx, 0, newInstId))
                    {
                        temp[tIdx] = newInstId;
                        ++tIdx;
                    } else
                    {
                        addInstToSig = 0;
                        break;
                    }
                }

                if (addInstToSig == INVALID && (nwCand_sigIdx + tIdx > 2*SLICE_CAPACITY))
                {
                    addInstToSig = 0;
                }

                if (addInstToSig == INVALID)
                {
                    for (int mBIdx = 0; mBIdx < tIdx; ++mBIdx)
                    {
                        nwCand_sig[nwCand_sigIdx] = temp[mBIdx];
                        ++nwCand_sigIdx;
                    }
                    addInstToSig = 1;
                }
            }

            if (addInstToSig == 1)
            {
                //check cand sig is in site_next_pq
                int candSigInSiteNextPQ = INVALID;
                for (int i = 0; i < PQ_IDX; ++i)
                {
                    int sigIdx = sPQ + i;
                    if (site_next_pq_validIdx[sigIdx] != INVALID)
                    {
                        if (site_next_pq_sig_idx[sigIdx] == nwCand_sigIdx)
                        {
                            int pqIdx(sigIdx*SIG_IDX), mtch(0);

                            for (int k = 0; k < nwCand_sigIdx; ++k)
                            {
                                for (int l = 0; l < nwCand_sigIdx; ++l)
                                {
                                    if (site_next_pq_sig[pqIdx + l] == nwCand_sig[k])
                                    {
                                        ++mtch;
                                        break;
                                    }
                                }
                            }
                            if (mtch == nwCand_sigIdx)
                            {
                                candSigInSiteNextPQ = 1;
                                break;
                            }
                        }
                    }
                }
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: cand in site_next_pq: %d \n", sIdx, siteId, candSigInSiteNextPQ);
        //}
        ////DBG

                if (candSigInSiteNextPQ == INVALID &&
                    add_inst_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map,
                        flat_node2pin_map, pin2net_map, pin_typeIds, flat_node2prclstrCount,
                        flat_node2precluster_map, flop2ctrlSetId_map, node2fence_region_map,
                        flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map, special_nodes,
                        lutTypeInSliceUnit, lut_maxShared, instId, lutId, ffId, half_ctrl_mode,
                        CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY, HALF_SLICE_CAPACITY, BLE_CAPACITY,
                        NUM_BLE_PER_SLICE, nwCand_lut, nwCand_ff, nwCand_cksr, nwCand_ce))
                {
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: compute cand score\n", sIdx, siteId);
        //}
        ////DBG

                    compute_candidate_score(pos_x, pos_y, pin_offset_x, pin_offset_y,
                        net_bbox, net_weights, site_xy, net_pinIdArrayX, net_pinIdArrayY,
                        flat_net2pin_start_map, flat_node2pin_start_map, flat_node2pin_map,
                        sorted_net_map, pin2net_map, pin2node_map, net2pincount, lut_type,
                        xWirelenWt, yWirelenWt, extNetCountWt, wirelenImprovWt,
                        netShareScoreMaxNetDegree, wlscoreMaxNetDegree, half_ctrl_mode,
                        nwCand_sig, nwCand_siteId, nwCand_sigIdx, nwCand_score);
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0)
        //{
        //    printf("%d Site %d: cand score: %.2f \n", sIdx, siteId, nwCand_score);
        //}
        ////DBG

                    int nxtId(INVALID);

                    if (site_next_pq_idx[sIdx] < PQ_IDX)
                    {
                        for (int vId = 0; vId < PQ_IDX; ++vId)
                        {
                            if (site_next_pq_validIdx[sPQ+vId] == INVALID)
                            {
                                nxtId = vId;
                                ++site_next_pq_idx[sIdx];
                                break;
                            }
                        }
                    } else
                    {
                        //find least score and replace if current score is greater
                        T ckscore(nwCand_score);
                        for (int vId = 0; vId < PQ_IDX; ++vId)
                        {
                            if (ckscore > site_next_pq_score[sPQ + vId])
                            {
                                ckscore = site_next_pq_score[sPQ + vId]; 
                                nxtId = vId;
                            }
                        }
                    }

                    if (nxtId != INVALID)
                    {
                        int nTId = sPQ + nxtId;
                        int nCKRId = nTId*CKSR_IN_CLB;
                        int nCEId = nTId*CE_IN_CLB;
                        int nFFId = nTId*SLICE_CAPACITY;
                        int nSGId = nTId*SIG_IDX;

                        /////
                        site_next_pq_validIdx[nTId] = 1;
                        site_next_pq_score[nTId] = nwCand_score;
                        site_next_pq_siteId[nTId] = nwCand_siteId;
                        site_next_pq_sig_idx[nTId] = nwCand_sigIdx;

                        for (int sg = 0; sg < nwCand_sigIdx; ++sg)
                        {
                            site_next_pq_sig[nSGId + sg] = nwCand_sig[sg];
                        }
                        for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                        {
                            site_next_pq_impl_lut[nFFId + sg] = nwCand_lut[sg];
                            site_next_pq_impl_ff[nFFId + sg] = nwCand_ff[sg];
                        }
                        for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                        {
                            site_next_pq_impl_cksr[nCKRId + sg] = nwCand_cksr[sg];
                        }
                        for (int sg = 0; sg < CE_IN_CLB; ++sg)
                        {
                            site_next_pq_impl_ce[nCEId + sg] = nwCand_ce[sg];
                        }
                        /////

                        if (site_next_pq_idx[sIdx] == 1 || 
                                nwCand_score > site_next_pq_score[sPQ + site_next_pq_top_idx[sIdx]])
                        {
                            site_next_pq_top_idx[sIdx] = nxtId;
                        }

                        nxtId = INVALID;

                        if (site_next_scl_idx[sIdx] < SCL_IDX)
                        {
                            for (int vId = 0; vId < SCL_IDX; ++vId)
                            {
                                if (site_next_scl_validIdx[sSCL+vId] == INVALID)
                                {
                                    nxtId = vId;
                                    ++site_next_scl_idx[sIdx];
                                    break;
                                }
                            }
                        } else
                        {
                            //find least score and replace if current score is greater
                            T ckscore(nwCand_score);
                            for (int vId = 0; vId < SCL_IDX; ++vId)
                            {
                                if (ckscore > site_next_scl_score[sSCL+vId])
                                {
                                    ckscore = site_next_scl_score[sSCL+vId]; 
                                    nxtId = vId;
                                }
                            }
                        }

                        if (nxtId != INVALID)
                        {
                            /////
                            nTId = sSCL + nxtId;
                            nCKRId = nTId*CKSR_IN_CLB;
                            nCEId = nTId*CE_IN_CLB;
                            nFFId = nTId*SLICE_CAPACITY;
                            nSGId = nTId*SIG_IDX;

                            site_next_scl_validIdx[nTId] = 1;
                            site_next_scl_score[nTId] = nwCand_score;
                            site_next_scl_siteId[nTId] = nwCand_siteId;
                            site_next_scl_sig_idx[nTId] = nwCand_sigIdx;

                            for (int sg = 0; sg < nwCand_sigIdx; ++sg)
                            {
                                site_next_scl_sig[nSGId + sg] = nwCand_sig[sg];
                            }
                            for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                            {
                                site_next_scl_impl_lut[nFFId + sg] = nwCand_lut[sg];
                                site_next_scl_impl_ff[nFFId + sg] = nwCand_ff[sg];
                            }
                            for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                            {
                                site_next_scl_impl_cksr[nCKRId + sg] = nwCand_cksr[sg];
                            }
                            for (int sg = 0; sg < CE_IN_CLB; ++sg)
                            {
                                site_next_scl_impl_ce[nCEId + sg] = nwCand_ce[sg];
                            }
                            /////
                        }
                    }
                }
            }

        }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0 && limit_cands > 0)
        //{
        //    printf("%d Site %d: completed big for loop\n", sIdx, siteId);
        //}
        ////DBG

        //Remove all candidates in scl that is worse than the worst candidate in PQ
        if (site_next_pq_idx[sIdx] > 0)
        {
            //Find worst candidate in PQ
            T ckscore(site_next_pq_score[sPQ + site_next_pq_top_idx[sIdx]]);

            for (int vId = 0; vId < PQ_IDX; ++vId)
            {
                int nPQId = sPQ + vId;
                if (site_next_pq_validIdx[nPQId] != INVALID)
                {
                    if (ckscore > site_next_pq_score[nPQId])
                    {
                        ckscore = site_next_pq_score[nPQId]; 
                    }
                }
            }

            //Invalidate worst ones in scl
            int sclCount = 0;
            int maxEntries = site_next_scl_idx[sIdx];
            for (int ckId = 0; ckId < SCL_IDX; ++ckId)
            {
                int vId = sSCL + ckId;
                if (site_next_scl_validIdx[vId] != INVALID)
                {
                    if (ckscore > site_next_scl_score[vId])
                    {
                        //Clear contents thoroughly
                        clear_cand_contents(
                                vId, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                                site_next_scl_sig_idx, site_next_scl_sig,
                                site_next_scl_impl_lut, site_next_scl_impl_ff,
                                site_next_scl_impl_cksr, site_next_scl_impl_ce);

                        site_next_scl_validIdx[vId] = INVALID;
                        site_next_scl_sig_idx[vId] = 0;
                        site_next_scl_siteId[vId] = INVALID;
                        site_next_scl_score[vId] = 0.0;
                        --site_next_scl_idx[sIdx];
                    }
                    ++sclCount;
                    if (sclCount == maxEntries)
                    {
                        break;
                    }
                }
            }
        }

        //Update stable Iteration count
        if (site_curr_pq_idx[sIdx] > 0 && site_next_pq_idx[sIdx] > 0 && 
                compare_pq_tops(site_curr_pq_score, site_curr_pq_top_idx,
                    site_curr_pq_validIdx, site_curr_pq_siteId, site_curr_pq_sig_idx,
                    site_curr_pq_sig, site_curr_pq_impl_lut, site_curr_pq_impl_ff,
                    site_curr_pq_impl_cksr, site_curr_pq_impl_ce, site_next_pq_score,
                    site_next_pq_top_idx, site_next_pq_validIdx, site_next_pq_siteId,
                    site_next_pq_sig_idx, site_next_pq_sig, site_next_pq_impl_lut,
                    site_next_pq_impl_ff, site_next_pq_impl_cksr, site_next_pq_impl_ce,
                    sIdx, sPQ, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY))
        {
            site_next_stable[sIdx] = site_curr_stable[sIdx] + 1;
        } else
        {
            site_next_stable[sIdx] = 0;
        }

        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0 && limit_cands > 0)
        //{
        //    printf("%d Site %d: completed (e) \n", sIdx, siteId);
        //}
        ////DBG

        //// (f) broadcastTopCandidate(site)
        if (site_next_pq_idx[sIdx] > 0)
        {
            int tpIdx = sPQ + site_next_pq_top_idx[sIdx];
            int topSigId = tpIdx*SIG_IDX;

            T scoreImprov = site_next_pq_score[tpIdx] - site_det_score[sIdx];

            ////UPDATED SEQUENTIAL PORTION
            int scoreImprovInt = DREAMPLACE_STD_NAMESPACE::max(int(scoreImprov*10000), intMinVal);
            site_score_improv[sIdx] = scoreImprovInt + siteId;

            for (int ssIdx = 0; ssIdx < site_next_pq_sig_idx[tpIdx]; ++ssIdx)
            {
                int instId = site_next_pq_sig[topSigId + ssIdx];

                if (inst_curr_detSite[instId] == INVALID)
                {
                    atomicMax(&inst_score_improv[instId], scoreImprovInt);
                }
            }
        }
        ////DBG
        //if (threadIdx.x == 0 && threadIdx.y == 0 && threadIdx.z == 0 && blockIdx.x == 0 && limit_cands > 0)
        //{
        //    printf("%d Site %d: completed (f) \n", sIdx, siteId);
        //}
        ////DBG
    }
}

//runDLSyncSites
template <typename T>
__global__ void runDLSyncSites(
        const int* site_nbrRanges_idx,
        const int* site_nbrGroup_idx,
        const int* addr2site_map,
        const int num_clb_sites,
        const int SLICE_CAPACITY,
        const int CKSR_IN_CLB,
        const int CE_IN_CLB,
        const int SCL_IDX,
        const int PQ_IDX,
        const int SIG_IDX,
        int* site_curr_pq_top_idx,
        int* site_curr_pq_sig_idx,
        int* site_curr_pq_sig,
        int* site_curr_pq_idx,
        int* site_curr_stable,
        int* site_curr_pq_validIdx,
        int* site_curr_pq_siteId,
        T* site_curr_pq_score,
        int* site_curr_pq_impl_lut,
        int* site_curr_pq_impl_ff,
        int* site_curr_pq_impl_cksr,
        int* site_curr_pq_impl_ce,
        T* site_curr_scl_score,
        int* site_curr_scl_siteId,
        int* site_curr_scl_idx,
        int* site_curr_scl_validIdx,
        int* site_curr_scl_sig_idx,
        int* site_curr_scl_sig,
        int* site_curr_scl_impl_lut,
        int* site_curr_scl_impl_ff,
        int* site_curr_scl_impl_cksr,
        int* site_curr_scl_impl_ce,
        int* site_next_pq_validIdx,
        T* site_next_pq_score,
        int* site_next_pq_top_idx,
        int* site_next_pq_siteId,
        int* site_next_pq_sig_idx,
        int* site_next_pq_sig,
        int* site_next_pq_idx,
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
        int* activeStatus)
{
    int sIdx = threadIdx.x + blockDim.x * blockIdx.x;
    while(sIdx < num_clb_sites)
    {
        int numNbrGroups = (site_nbrRanges_idx[sIdx] == 0) ? 0 : site_nbrRanges_idx[sIdx]-1;
        int sPQ = sIdx*SCL_IDX;

        site_curr_stable[sIdx] = site_next_stable[sIdx];

        int curr_scl_size = site_curr_scl_idx[sIdx];
        site_curr_scl_idx[sIdx] = 0;
        int sclCount = 0;

        //Include valid entries of site.next.scl to site.curr.scl
        if (site_next_scl_idx[sIdx] > 0)
        {
            for (int id = 0; id < SCL_IDX; ++id)
            {
                int vIdx = sPQ+id;
                if (site_next_scl_validIdx[vIdx] != INVALID)
                {
                    int currId = sPQ+site_curr_scl_idx[sIdx];

                    site_curr_scl_validIdx[currId] = 1;
                    site_curr_scl_siteId[currId] = site_next_scl_siteId[vIdx];
                    site_curr_scl_score[currId] = site_next_scl_score[vIdx];
                    site_curr_scl_sig_idx[currId] = site_next_scl_sig_idx[vIdx];

                    int currFFId(currId*SLICE_CAPACITY), nxtFFId(vIdx*SLICE_CAPACITY);
                    int currCKId(currId*CKSR_IN_CLB), nxtCKId(vIdx*CKSR_IN_CLB);
                    int currCEId(currId*CE_IN_CLB), nxtCEId(vIdx*CE_IN_CLB);
                    int currSGId(currId*SIG_IDX), nxtSGId(vIdx*SIG_IDX);

                    for (int sg = 0; sg < site_next_scl_sig_idx[vIdx]; ++sg)
                    {
                        site_curr_scl_sig[currSGId + sg] = site_next_scl_sig[nxtSGId + sg];
                    }
                    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                    {
                        site_curr_scl_impl_lut[currFFId + sg] = site_next_scl_impl_lut[nxtFFId + sg];
                        site_curr_scl_impl_ff[currFFId + sg] = site_next_scl_impl_ff[nxtFFId + sg];
                    }
                    for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                    {
                        site_curr_scl_impl_cksr[currCKId + sg]  = site_next_scl_impl_cksr[nxtCKId + sg];
                    }
                    for (int sg = 0; sg < CE_IN_CLB; ++sg)
                    {
                        site_curr_scl_impl_ce[currCEId + sg] = site_next_scl_impl_ce[nxtCEId + sg];
                    }
                    ++site_curr_scl_idx[sIdx];
                    ++sclCount;
                    if (sclCount == site_next_scl_idx[sIdx])
                    {
                        break;
                    }
                }
            }
        }

        ////Invalidate the rest in site.curr.scl
        if (curr_scl_size > site_next_scl_idx[sIdx])
        {
            for (int ckId = site_curr_scl_idx[sIdx]; ckId < SCL_IDX; ++ckId)
            {
                int vIdx = sPQ+ckId;
                if (site_curr_scl_validIdx[vIdx] != INVALID)
                {
                    site_curr_scl_validIdx[vIdx] = INVALID;
                    site_curr_scl_sig_idx[vIdx] = 0;
                    site_curr_scl_siteId[vIdx] = INVALID;
                    site_curr_scl_score[vIdx] = T(0.0);
                    ++sclCount;
                    if (sclCount == curr_scl_size)
                    {
                        break;
                    }
                }
            }
        }

        int curr_pq_size = site_curr_pq_idx[sIdx];
        site_curr_pq_idx[sIdx] = 0;
        site_curr_pq_top_idx[sIdx] = INVALID;

        sPQ = sIdx*PQ_IDX;
        sclCount = 0;
        //Include valid entries of site.next.pq to site.curr.pq
        if (site_next_pq_idx[sIdx] > 0)
        {
            for (int id = 0; id < PQ_IDX; ++id)
            {
                int vIdx = sPQ+id;
                if (site_next_pq_validIdx[vIdx] != INVALID)
                {
                    int currId = sPQ+site_curr_pq_idx[sIdx];

                    site_curr_pq_validIdx[currId] = 1;
                    site_curr_pq_siteId[currId] = site_next_pq_siteId[vIdx];
                    site_curr_pq_score[currId] = site_next_pq_score[vIdx];
                    site_curr_pq_sig_idx[currId] = site_next_pq_sig_idx[vIdx];

                    int currFFId(currId*SLICE_CAPACITY), nxtFFId(vIdx*SLICE_CAPACITY);
                    int currCKId(currId*CKSR_IN_CLB), nxtCKId(vIdx*CKSR_IN_CLB);
                    int currCEId(currId*CE_IN_CLB), nxtCEId(vIdx*CE_IN_CLB);
                    int currSGId(currId*SIG_IDX), nxtSGId(vIdx*SIG_IDX);

                    for (int sg = 0; sg < site_next_pq_sig_idx[vIdx]; ++sg)
                    {
                        site_curr_pq_sig[currSGId + sg] = site_next_pq_sig[nxtSGId + sg];
                    }
                    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                    {
                        site_curr_pq_impl_lut[currFFId + sg] = site_next_pq_impl_lut[nxtFFId + sg];
                        site_curr_pq_impl_ff[currFFId + sg] = site_next_pq_impl_ff[nxtFFId + sg];
                    }
                    for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                    {
                        site_curr_pq_impl_cksr[currCKId + sg]  = site_next_pq_impl_cksr[nxtCKId + sg];
                    }
                    for (int sg = 0; sg < CE_IN_CLB; ++sg)
                    {
                        site_curr_pq_impl_ce[currCEId + sg] = site_next_pq_impl_ce[nxtCEId + sg];
                    }
                    if (id == site_next_pq_top_idx[sIdx])
                    {
                        site_curr_pq_top_idx[sIdx] = site_curr_pq_idx[sIdx];
                    }
                    ++site_curr_pq_idx[sIdx];
                    ++sclCount;
                    if (sclCount == site_next_pq_idx[sIdx])
                    {
                        break;
                    }
                }
            }
        }

        //Invalidate the rest in site.curr.pq
        if (curr_pq_size > site_next_pq_idx[sIdx])
        {
            for (int ckId = site_curr_pq_idx[sIdx]; ckId < PQ_IDX; ++ckId)
            {
                int vIdx = sPQ+ckId;
                if (site_curr_pq_validIdx[vIdx] != INVALID)
                {
                    site_curr_pq_validIdx[vIdx] = INVALID;
                    site_curr_pq_sig_idx[vIdx] = 0;
                    site_curr_pq_siteId[vIdx] = INVALID;
                    site_curr_pq_score[vIdx] = T(0.0);
                    ++sclCount;
                    if (sclCount == curr_pq_size)
                    {
                        break;
                    }
                }
            }
        }

        sPQ = sIdx*SCL_IDX;
        //sclCount = 0;
        for (int ckId = 0; ckId < SCL_IDX; ++ckId)
        {
            int vIdx = sPQ+ckId;
            //if (site_next_scl_validIdx[vIdx] != INVALID)
            //{
            //Clear contents thoroughly
            clear_cand_contents(
                    vIdx, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                    site_next_scl_sig_idx, site_next_scl_sig,
                    site_next_scl_impl_lut, site_next_scl_impl_ff,
                    site_next_scl_impl_cksr, site_next_scl_impl_ce);

            site_next_scl_validIdx[vIdx] = INVALID;
            site_next_scl_sig_idx[vIdx] = 0;
            site_next_scl_siteId[vIdx] = INVALID;
            site_next_scl_score[vIdx] = 0.0;
            //++sclCount;
            //if (sclCount == site_next_scl_idx[sIdx])
            //{
            //    break;
            //}
            //}
        }
        site_next_scl_idx[sIdx] = 0;

        activeStatus[addr2site_map[sIdx]] = (site_curr_pq_idx[sIdx] > 0 ||
                site_curr_scl_idx[sIdx] > 0 ||
                site_nbrGroup_idx[sIdx] < numNbrGroups) ? 1: 0;

        sIdx += blockDim.x * gridDim.x;
    }
}

//runDLSyncInsts
template <typename T>
__global__ void runDLSyncInsts(
        const T* pos_x,
        const T* pos_y,
        const T* site_xy,
        const int* site_types,
        const int* site2addr_map,
        const int* spiral_accessor,
        const int* lut_flop_indices,
        const int* site_score_improv,
        const int* site_curr_pq_top_idx,
        const int* site_curr_pq_sig_idx,
        const int* site_curr_pq_sig,
        const int* site_curr_pq_idx,
        const T maxDist,
        const int spiralBegin,
        const int spiralEnd,
        const int intMinVal,
        const int num_nodes,
        const int num_sites_x,
        const int num_sites_y,
        const int sliceId,
        const int maxSites,
        const int SIG_IDX,
        const int PQ_IDX,
        T* inst_curr_bestScoreImprov,
        T* inst_next_bestScoreImprov,
        int* inst_score_improv,
        int* inst_curr_detSite,
        int* inst_curr_bestSite,
        int* inst_next_detSite,
        int* inst_next_bestSite,
        int* illegalStatus)
{
    int nIdx = threadIdx.x + blockDim.x * blockIdx.x;
    while(nIdx < num_nodes)
    {
        const int nodeId = lut_flop_indices[nIdx];
        if (inst_curr_detSite[nodeId] == INVALID) //Only LUT/FF
        {
            //POST PROCESSING TO IDENTIFY INSTANCE BEST SITE
            //REPLACEMENT FOR SEQUENTIAL PORTION
            if (inst_score_improv[nodeId] > intMinVal)
            {
                int bestSite = maxSites;
                int &instScoreImprov = inst_score_improv[nodeId];
                T instScoreImprovT =  T(instScoreImprov/10000.0);
                T posX = pos_x[nodeId];
                T posY = pos_y[nodeId];

                for (int spIdx = spiralBegin; spIdx < spiralEnd; ++spIdx)
                {
                    int saIdx = spIdx*2;
                    int xVal = posX + spiral_accessor[saIdx];
                    int yVal = posY + spiral_accessor[saIdx+1];

                    int siteId = xVal * num_sites_y + yVal;

                    if (xVal >= 0 && xVal < num_sites_x &&
                        yVal >= 0 && yVal < num_sites_y &&
                        site_types[siteId] == sliceId)
                    {
                        int stMpId = siteId *2;
                        int sIdx = site2addr_map[siteId];
                        int tsPQ = sIdx*PQ_IDX + site_curr_pq_top_idx[sIdx];
                        int topIdx = tsPQ*SIG_IDX;
                        int site_score = site_score_improv[sIdx] - siteId;

                        T dist = DREAMPLACE_STD_NAMESPACE::abs(posX - site_xy[stMpId]) +
                                DREAMPLACE_STD_NAMESPACE::abs(posY - site_xy[stMpId+1]);

                        if (instScoreImprov == site_score &&
                            site_curr_pq_idx[sIdx] > 0)
                        {
                            for (int idx = 0; idx < site_curr_pq_sig_idx[tsPQ]; ++idx)
                            {
                                if (site_curr_pq_sig[topIdx+idx] == nodeId &&
                                        siteId < bestSite && dist < maxDist)
                                {
                                    bestSite = siteId;
                                    inst_next_bestSite[nodeId] = siteId;
                                    inst_next_bestScoreImprov[nodeId] = instScoreImprovT;
                                }
                            }
                        }
                    }
                }
                instScoreImprov = intMinVal;
            }
            //END post processing


            inst_curr_detSite[nodeId] = inst_next_detSite[nodeId];
            inst_curr_bestSite[nodeId] = inst_next_bestSite[nodeId];
            inst_curr_bestScoreImprov[nodeId] = inst_next_bestScoreImprov[nodeId];

            inst_next_bestSite[nodeId] = INVALID;
            inst_next_bestScoreImprov[nodeId] = T(-10000.0);

            illegalStatus[nodeId] = (inst_curr_detSite[nodeId] == INVALID) ? 1 : 0;
        }
        nIdx += blockDim.x * gridDim.x;
    }
}

//legalize Mlab
template <typename T>
__global__ void legalizeMlab_kernel(
        const T* pos_x,
        const T* pos_y,
        const T* site_xy,
        const T* mlab_locX,
        const T* mlab_locY,
        const int* mlab_indices,
        const int* site2addr_map,
        const T max_score,
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
        int* sites_with_special_nodes)
{
    int nIdx = threadIdx.x + blockDim.x * blockIdx.x;
    while(nIdx < num_mlab_nodes)
    {
        const int instId = mlab_indices[nIdx];

        T xVal = mlab_locX[nIdx];
        T yVal = mlab_locY[nIdx];

        int siteId = xVal * num_sites_y + yVal;
        int sIdx = site2addr_map[siteId];

        dist_moved[nIdx] = DREAMPLACE_STD_NAMESPACE::abs(pos_x[instId] - site_xy[siteId*2]) + 
            DREAMPLACE_STD_NAMESPACE::abs(pos_y[instId] - site_xy[siteId*2+1]);

        int sdtopId = sIdx*SIG_IDX;
        int sdlutId = sIdx*SLICE_CAPACITY;

        if (site_det_sig_idx[sIdx] == 0)
        {
            sites_with_special_nodes[sIdx] = 1;
            site_det_score[sIdx] = max_score;
            site_det_siteId[sIdx] = siteId;

            site_det_sig_idx[sIdx] = 2*SLICE_CAPACITY;
            site_det_sig[sdtopId] = instId;
            site_det_impl_lut[sdlutId] = instId;

            inst_curr_detSite[instId] = siteId;
            inst_curr_bestSite[instId] = siteId;
            inst_curr_bestScoreImprov[instId] = max_score;

            inst_next_detSite[instId] = siteId;
            inst_next_bestSite[instId] = siteId;
            inst_next_bestScoreImprov[instId] = max_score;
        } 
        //DBG
        else {
            printf("ERROR: Slice site not empty - MLAB %d not legalized at (%.2f, %.2f)\n", instId, xVal, yVal);
        }
        //DBG

        nIdx += blockDim.x * gridDim.x;
    }
}

///////////////////////////////////////////////////////////////////////////////////////////////////////////////

//init nets and precluster
template <typename T>
int initLGCudaLauncher(
        const T* pos_x,
        const T* pos_y,
        const T* pin_offset_x,
        const T* pin_offset_y,
        const int* sorted_node_map,
        const int* sorted_node_idx,
        const int* sorted_net_idx,
        const int* flat_net2pin_map,
        const int* flat_net2pin_start_map,
        const int* flop2ctrlSetId_map,
        const int* flop_ctrlSets,
        const int* node2fence_region_map,
        const int* node2outpinIdx_map,
        const int* pin2net_map,
        const int* pin2node_map,
        const int* pin_typeIds,
        const int* net2pincount,
        const int* is_mlab_node,
        const T preClusteringMaxDist,
        const int ffId,
        const int lutId,
        const int num_nets,
        const int num_nodes,
        const int wlscoreMaxNetDegree,
        T* net_bbox,
        int* net_pinIdArrayX,
        int* net_pinIdArrayY,
        int* flat_node2precluster_map,
        int* flat_node2prclstrCount)
{
    int block_count = ceilDiv(num_nets + THREAD_COUNT-1, THREAD_COUNT);
    initNets<<<block_count, THREAD_COUNT>>>(
            pos_x, pos_y, pin_offset_x, pin_offset_y,
            flat_net2pin_start_map, flat_net2pin_map,
            sorted_net_idx, pin2node_map, net2pincount,
            num_nets, wlscoreMaxNetDegree, net_bbox,
            net_pinIdArrayX, net_pinIdArrayY);

    int nodes_block_count = ceilDiv(num_nodes + THREAD_COUNT-1, THREAD_COUNT);
    preClustering<<<nodes_block_count, THREAD_COUNT>>>(
            pos_x, pos_y, pin_offset_x, pin_offset_y,
            sorted_node_map, sorted_node_idx,
            flat_net2pin_start_map, flat_net2pin_map,
            flop2ctrlSetId_map, flop_ctrlSets,
            node2fence_region_map, node2outpinIdx_map,
            pin2net_map, pin2node_map, pin_typeIds,
            is_mlab_node, preClusteringMaxDist,
            lutId, ffId, num_nodes,
            flat_node2precluster_map, flat_node2prclstrCount);

    cudaDeviceSynchronize();
    return 0;
}

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
        int* sorted_clb_siteIds
        )
{
    int block_count = ceilDiv(num_clb_sites + THREAD_COUNT-1, THREAD_COUNT);

    //- Uncomment below line for debg
    //DL kernel split Implementation to enable scheduling 
    //Use below line for debg
    //runDLIteration_kernel_1<<<1, 1>>>(
    runDLIteration_kernel_1<<<block_count, THREAD_COUNT>>>(
            node2fence_region_map, flop2ctrlSetId_map, flop_ctrlSets,
            extended_ctrlSets, ext_ctrlSet_start_map, lut_type,
            flat_node2pin_start_map, flat_node2pin_map, node2outpinIdx_map, pin2net_map,
            pin_typeIds, flat_node2prclstrCount, flat_node2precluster_map,
            is_mlab_node, site_nbrList, site_nbrRanges, site_nbrRanges_idx,
            addr2site_map, special_nodes, num_clb_sites, minStableIter,
            maxList, half_ctrl_mode, SLICE_CAPACITY,
            HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE, minNeighbors,
            numGroups, lutTypeInSliceUnit, lut_maxShared, CKSR_IN_CLB, CE_IN_CLB,
            SCL_IDX, PQ_IDX, SIG_IDX, lutId, ffId, site_nbr_idx, site_nbr,
            site_nbrGroup_idx, site_curr_pq_top_idx, site_curr_pq_sig_idx,
            site_curr_pq_sig, site_curr_pq_idx, site_curr_stable,
            site_curr_pq_siteId, site_curr_pq_score, site_curr_pq_impl_lut,
            site_curr_pq_impl_ff, site_curr_pq_impl_cksr, site_curr_pq_impl_ce,
            site_curr_scl_score, site_curr_scl_siteId, site_curr_scl_idx,
            site_curr_scl_validIdx, site_curr_scl_sig_idx, site_curr_scl_sig,
            site_curr_scl_impl_lut, site_curr_scl_impl_ff, site_curr_scl_impl_cksr,
            site_curr_scl_impl_ce, site_next_pq_idx, site_next_pq_validIdx,
            site_next_pq_top_idx, site_next_pq_impl_lut, site_next_pq_impl_ff,
            site_next_pq_impl_cksr, site_next_pq_impl_ce,
            site_next_pq_score, site_next_pq_siteId,
            site_next_pq_sig_idx, site_next_pq_sig, site_det_score,
            site_det_siteId, site_det_sig_idx, site_det_sig, site_det_impl_lut,
            site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce,
            inst_curr_detSite, inst_curr_bestSite, inst_next_detSite,
            validIndices_curr_scl, cumsum_curr_scl);

    cudaDeviceSynchronize();
    //printf("Completed ruNDLIter_k1");

    //////Use thrust to sort cumsum_curr_scl to compute sorted siteIds based on load
    thrust::device_ptr<int> cumsum_ptr = thrust::device_pointer_cast(cumsum_curr_scl);
    thrust::device_ptr<int> sortedId_ptr = thrust::device_pointer_cast(sorted_clb_siteIds);

    thrust::sequence(sortedId_ptr, sortedId_ptr+num_clb_sites, 0);
    thrust::sort_by_key(cumsum_ptr, cumsum_ptr+num_clb_sites, sortedId_ptr, thrust::greater<int>());
    //Note: order of cumsum_curr_scl is also changed but it is not used in the next steps
    //printf("Completed sorting of indices\n");

    //Use below line for debg
    //runDLIteration_kernel_2<<<1, 1>>>(
    runDLIteration_kernel_2<<<block_count, THREAD_COUNT>>>(
            pos_x, pos_y, pin_offset_x, pin_offset_y, net_bbox, site_xy,
            net_weights, net_pinIdArrayX, net_pinIdArrayY, node2fence_region_map,
            flop2ctrlSetId_map, flop_ctrlSets, extended_ctrlSets,
            ext_ctrlSet_start_map, flat_net2pin_start_map,
            flat_node2pin_start_map, flat_node2pin_map, node2outpinIdx_map, lut_type, net2pincount,
            pin2net_map, pin_typeIds, pin2node_map, sorted_node_map,
            sorted_net_map, flat_node2prclstrCount, flat_node2precluster_map,
            validIndices_curr_scl, sorted_clb_siteIds, addr2site_map,
            special_nodes, xWirelenWt, yWirelenWt, wirelenImprovWt, extNetCountWt,
            num_clb_sites, intMinVal, maxList, half_ctrl_mode, SLICE_CAPACITY, 
            HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE, netShareScoreMaxNetDegree,
            wlscoreMaxNetDegree, lutTypeInSliceUnit, lut_maxShared, CKSR_IN_CLB,
            CE_IN_CLB, SCL_IDX, PQ_IDX, SIG_IDX, lutId, ffId, site_nbr_idx,
            site_nbr, site_curr_pq_top_idx, site_curr_pq_validIdx,
            site_curr_pq_sig_idx, site_curr_pq_sig, site_curr_pq_impl_lut,
            site_curr_pq_impl_ff, site_curr_pq_impl_cksr, site_curr_pq_impl_ce,
            site_curr_pq_idx, site_curr_stable, site_curr_pq_siteId,
            site_curr_pq_score, site_curr_scl_score, site_curr_scl_siteId,
            site_curr_scl_idx, site_curr_scl_validIdx, site_curr_scl_sig_idx,
            site_curr_scl_sig, site_curr_scl_impl_lut, site_curr_scl_impl_ff,
            site_curr_scl_impl_cksr, site_curr_scl_impl_ce, site_next_pq_idx,
            site_next_pq_validIdx, site_next_pq_top_idx, site_next_pq_score,
            site_next_pq_siteId, site_next_pq_sig_idx, site_next_pq_sig,
            site_next_pq_impl_lut, site_next_pq_impl_ff, site_next_pq_impl_cksr,
            site_next_pq_impl_ce, site_next_scl_score, site_next_scl_siteId,
            site_next_scl_idx, site_next_scl_validIdx, site_next_scl_sig_idx,
            site_next_scl_sig, site_next_scl_impl_lut, site_next_scl_impl_ff,
            site_next_scl_impl_cksr, site_next_scl_impl_ce, site_next_stable,
            site_det_score, inst_curr_detSite, inst_next_bestScoreImprov,
            inst_next_bestSite, inst_score_improv, site_score_improv);

    cudaDeviceSynchronize();
    //printf("Completed ruNDLIter_k2\n");

    ////Use either combined runDLIteration or runDLIter1 + runDLIter2
    //runDLIteration<<<block_count, THREAD_COUNT>>>(
    //        pos_x, pos_y, pin_offset_x, pin_offset_y, net_bbox, site_xy,
    //        net_pinIdArrayX, net_pinIdArrayY, node2fence_region_map,
    //        flop2ctrlSetId_map, flop_ctrlSets, extended_ctrlSets,
    //        ext_ctrlSet_start_map, lut_type, flat_node2pin_start_map,
    //        flat_node2pin_map, node2outpinIdx_map, net2pincount, pin2net_map, pin_typeIds,
    //        flat_net2pin_start_map, pin2node_map, sorted_net_map, sorted_node_map,
    //        flat_node2prclstrCount, flat_node2precluster_map, is_mlab_node, site_nbrList,
    //        site_nbrRanges, site_nbrRanges_idx, net_weights, addr2site_map,
    //        special_nodes, num_clb_sites, minStableIter, maxList, half_ctrl_mode, SLICE_CAPACITY,
    //        HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE, minNeighbors,
    //        intMinVal, numGroups, netShareScoreMaxNetDegree, wlscoreMaxNetDegree,
    //        lutTypeInSliceUnit, lut_maxShared, xWirelenWt, yWirelenWt,
    //        wirelenImprovWt, extNetCountWt, CKSR_IN_CLB, CE_IN_CLB, SCL_IDX,
    //        PQ_IDX, SIG_IDX, lutId, ffId, validIndices_curr_scl, site_nbr_idx,
    //        site_nbr, site_nbrGroup_idx, site_curr_pq_top_idx, site_curr_pq_validIdx, site_curr_pq_sig_idx,
    //        site_curr_pq_sig, site_curr_pq_idx, site_curr_stable,
    //        site_curr_pq_siteId, site_curr_pq_score, site_curr_pq_impl_lut,
    //        site_curr_pq_impl_ff, site_curr_pq_impl_cksr, site_curr_pq_impl_ce,
    //        site_curr_scl_score, site_curr_scl_siteId, site_curr_scl_idx,
    //        site_curr_scl_validIdx, site_curr_scl_sig_idx, site_curr_scl_sig,
    //        site_curr_scl_impl_lut, site_curr_scl_impl_ff, site_curr_scl_impl_cksr,
    //        site_curr_scl_impl_ce, site_next_pq_idx, site_next_pq_validIdx,
    //        site_next_pq_top_idx, site_next_pq_score, site_next_pq_siteId,
    //        site_next_pq_sig_idx, site_next_pq_sig, site_next_pq_impl_lut,
    //        site_next_pq_impl_ff, site_next_pq_impl_cksr, site_next_pq_impl_ce,
    //        site_next_scl_score, site_next_scl_siteId, site_next_scl_idx,
    //        site_next_scl_validIdx, site_next_scl_sig_idx, site_next_scl_sig,
    //        site_next_scl_impl_lut, site_next_scl_impl_ff, site_next_scl_impl_cksr,
    //        site_next_scl_impl_ce, site_next_stable, site_det_score,
    //        site_det_siteId, site_det_sig_idx, site_det_sig, site_det_impl_lut,
    //        site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce,
    //        inst_curr_detSite, inst_curr_bestSite, inst_next_detSite,
    //        inst_next_bestScoreImprov, inst_next_bestSite, inst_score_improv,
    //        site_score_improv);
    //cudaDeviceSynchronize();

    int nodes_block_count = ceilDiv(num_lutflops + THREAD_COUNT - 1, THREAD_COUNT);
    int maxSites = num_sites_x*num_sites_y;

    runDLSyncInsts<<<nodes_block_count, THREAD_COUNT>>>(
            pos_x, pos_y, site_xy, site_types, site2addr_map, spiral_accessor,
            lut_flop_indices, site_score_improv, site_curr_pq_top_idx,
            site_curr_pq_sig_idx, site_curr_pq_sig, site_curr_pq_idx, maxDist,
            spiralBegin, spiralEnd, intMinVal, num_lutflops, num_sites_x,
            num_sites_y, sliceId, maxSites, SIG_IDX, PQ_IDX,
            inst_curr_bestScoreImprov, inst_next_bestScoreImprov, inst_score_improv,
            inst_curr_detSite, inst_curr_bestSite, inst_next_detSite,
            inst_next_bestSite, illegalStatus);

    cudaDeviceSynchronize();
    //printf("End of runDLSyncInsts\n");

    runDLSyncSites<<<block_count, THREAD_COUNT>>>(
            site_nbrRanges_idx, site_nbrGroup_idx, addr2site_map, num_clb_sites,
            SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB, SCL_IDX, PQ_IDX, SIG_IDX,
            site_curr_pq_top_idx, site_curr_pq_sig_idx, site_curr_pq_sig,
            site_curr_pq_idx, site_curr_stable, site_curr_pq_validIdx,
            site_curr_pq_siteId, site_curr_pq_score, site_curr_pq_impl_lut,
            site_curr_pq_impl_ff, site_curr_pq_impl_cksr, site_curr_pq_impl_ce,
            site_curr_scl_score, site_curr_scl_siteId, site_curr_scl_idx,
            site_curr_scl_validIdx, site_curr_scl_sig_idx, site_curr_scl_sig,
            site_curr_scl_impl_lut, site_curr_scl_impl_ff, site_curr_scl_impl_cksr,
            site_curr_scl_impl_ce, site_next_pq_validIdx, site_next_pq_score,
            site_next_pq_top_idx, site_next_pq_siteId, site_next_pq_sig_idx,
            site_next_pq_sig, site_next_pq_idx, site_next_pq_impl_lut,
            site_next_pq_impl_ff, site_next_pq_impl_cksr, site_next_pq_impl_ce,
            site_next_scl_score, site_next_scl_siteId, site_next_scl_idx,
            site_next_scl_validIdx, site_next_scl_sig_idx, site_next_scl_sig,
            site_next_scl_impl_lut, site_next_scl_impl_ff, site_next_scl_impl_cksr,
            site_next_scl_impl_ce, site_next_stable, activeStatus);

    cudaDeviceSynchronize();
    //printf("End of runDLSyncSites\n");

    return 0;
}

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
        int* sites_with_special_nodes)
{
    int block_count = ceilDiv(num_mlab_nodes + THREAD_COUNT-1, THREAD_COUNT);

    T max_score = T(10000.0);

    legalizeMlab_kernel<<<block_count, THREAD_COUNT>>>(
            pos_x, pos_y, site_xy, mlab_locX, mlab_locY, mlab_indices,
            site2addr_map, max_score, num_mlab_nodes, num_sites_y,
            SIG_IDX, SLICE_CAPACITY, dist_moved, site_det_score,
            inst_curr_bestScoreImprov, inst_next_bestScoreImprov,
            site_det_siteId, site_det_sig_idx, site_det_sig,
            site_det_impl_lut, inst_curr_detSite, inst_curr_bestSite,
            inst_next_detSite, inst_next_bestSite, sites_with_special_nodes);

    cudaDeviceSynchronize();
    //printf("Completed legalize Mlab");

    return 0;
}

#define REGISTER_KERNEL_LAUNCHER(T)                                                 \
    template int initLGCudaLauncher<T>                                              \
        (const T* pos_x, const T* pos_y, const T* pin_offset_x,                     \
         const T* pin_offset_y, const int* sorted_node_map,                         \
         const int* sorted_node_idx, const int* sorted_net_idx,                     \
         const int* flat_net2pin_map, const int* flat_net2pin_start_map,            \
         const int* flop2ctrlSetId_map, const int* flop_ctrlSets,                   \
         const int* node2fence_region_map, const int* node2outpinIdx_map,           \
         const int* pin2net_map, const int* pin2node_map,                           \
         const int* pin_typeIds, const int* net2pincount,                           \
         const int* is_mlab_node, const T preClusteringMaxDist,                     \
         const int ffId, const int lutId, const int num_nets,                       \
         const int num_nodes, const int WLscoreMaxNetDegre, T* net_bbox,            \
         int* net_pinIdArrayX, int* net_pinIdArrayY, int* flat_node2precluster_map, \
         int* flat_node2prclstrCount);                                              \
                                                                                    \
    template int runDLCudaLauncher<T>                                               \
        (const T* pos_x, const T* pos_y, const T* pin_offset_x,                     \
         const T* pin_offset_y, const T* net_bbox, const T* site_xy,                \
         const T* net_weights, const int* net_pinIdArrayX,                          \
         const int* net_pinIdArrayY, const int* site_types,                         \
         const int* spiral_accessor, const int* node2fence_region_map,              \
         const int* lut_flop_indices, const int* flop2ctrlSetId_map,                \
         const int* flop_ctrlSets, const int* extended_ctrlSets,                    \
         const int* ext_ctrlSet_start_map, const int* lut_type,                     \
         const int* flat_node2pin_start_map, const int* flat_node2pin_map,          \
         const int* node2outpinIdx_map, const int* node2pincount,                   \
         const int* net2pincount, const int* pin2net_map, const int* pin_typeIds,   \
         const int* flat_net2pin_start_map, const int* pin2node_map,                \
         const int* sorted_net_map, const int* sorted_node_map,                     \
         const int* flat_node2prclstrCount, const int* flat_node2precluster_map,    \
         const int* is_mlab_node, const int* site_nbrList,                          \
         const int* site_nbrRanges, const int* site_nbrRanges_idx,                  \
         const int* addr2site_map, const int* site2addr_map,                        \
         const int* special_nodes, const T maxDist, const T xWirelenWt,             \
         const T yWirelenWt, const T wirelenImprovWt, const T extNetCountWt,        \
         const int num_sites_x, const int num_sites_y,                              \
         const int num_clb_sites, const int num_lutflops,                           \
         const int minStableIter, const int maxList, const int half_ctrl_mode,      \
         const int SLICE_CAPACITY, const int HALF_SLICE_CAPACITY,                   \
         const int BLE_CAPACITY, const int NUM_BLE_PER_SLICE,                       \
         const int minNeighbors, const int spiralBegin, const int spiralEnd,        \
         const int intMinVal, const int numGroups,                                  \
         const int netShareScoreMaxNetDegree, const int wlscoreMaxNetDegree,        \
         const int lutTypeInSliceUnit, const int lut_maxShared,                     \
         const int CKSR_IN_CLB, const int CE_IN_CLB, const int SCL_IDX,             \
         const int PQ_IDX, const int SIG_IDX, const int ludId,                      \
         const int ffId, const int sliceId, int* site_nbr_idx,                      \
         int* site_nbr, int* site_nbrGroup_idx, int* site_curr_pq_top_idx,          \
         int* site_curr_pq_sig_idx, int* site_curr_pq_sig,                          \
         int* site_curr_pq_idx, int* site_curr_stable,                              \
         int* site_curr_pq_siteId, int* site_curr_pq_validIdx,                      \
         T* site_curr_pq_score, int* site_curr_pq_impl_lut,                         \
         int* site_curr_pq_impl_ff, int* site_curr_pq_impl_cksr,                    \
         int* site_curr_pq_impl_ce, T* site_curr_scl_score,                         \
         int* site_curr_scl_siteId, int* site_curr_scl_idx,                         \
         int* cumsum_curr_scl, int* site_curr_scl_validIdx,                         \
         int* validIndices_curr_scl, int* site_curr_scl_sig_idx,                    \
         int* site_curr_scl_sig, int* site_curr_scl_impl_lut,                       \
         int* site_curr_scl_impl_ff, int* site_curr_scl_impl_cksr,                  \
         int* site_curr_scl_impl_ce, int* site_next_pq_idx,                         \
         int* site_next_pq_validIdx, int* site_next_pq_top_idx,                     \
         T* site_next_pq_score, int* site_next_pq_siteId,                           \
         int* site_next_pq_sig_idx, int* site_next_pq_sig,                          \
         int* site_next_pq_impl_lut, int* site_next_pq_impl_ff,                     \
         int* site_next_pq_impl_cksr, int* site_next_pq_impl_ce,                    \
         T* site_next_scl_score, int* site_next_scl_siteId,                         \
         int* site_next_scl_idx, int* site_next_scl_validIdx,                       \
         int* site_next_scl_sig_idx, int* site_next_scl_sig,                        \
         int* site_next_scl_impl_lut, int* site_next_scl_impl_ff,                   \
         int* site_next_scl_impl_cksr, int* site_next_scl_impl_ce,                  \
         int* site_next_stable, T* site_det_score, int* site_det_siteId,            \
         int* site_det_sig_idx, int* site_det_sig, int* site_det_impl_lut,          \
         int* site_det_impl_ff, int* site_det_impl_cksr,                            \
         int* site_det_impl_ce, int* inst_curr_detSite,                             \
         T* inst_curr_bestScoreImprov, int* inst_curr_bestSite,                     \
         int* inst_next_detSite, T* inst_next_bestScoreImprov,                      \
         int* inst_next_bestSite, int* activeStatus, int* illegalStatus,            \
         int* inst_score_improv, int* site_score_improv,                            \
         int* sorted_clb_siteIds);                                                  \
                                                                                    \
    template int legalizeMlabCudaLauncher<T>                                        \
        (const T* pos_x, const T* pos_y, const T* site_xy, const T* mlab_locX,      \
        const T* mlab_locY, const int* mlab_indices, const int* site2addr_map,      \
        const int num_mlab_nodes, const int num_sites_y, const int SIG_IDX,         \
        const int SLICE_CAPACITY, T* dist_moved, T* site_det_score,                 \
        T* inst_curr_bestScoreImprov, T* inst_next_bestScoreImprov,                 \
        int* site_det_siteId, int* site_det_sig_idx, int* site_det_sig,             \
        int* site_det_impl_lut, int* inst_curr_detSite, int* inst_curr_bestSite,    \
        int* inst_next_detSite, int* inst_next_bestSite,                            \
        int* sites_with_special_nodes);

REGISTER_KERNEL_LAUNCHER(float);
REGISTER_KERNEL_LAUNCHER(double);

DREAMPLACE_END_NAMESPACE

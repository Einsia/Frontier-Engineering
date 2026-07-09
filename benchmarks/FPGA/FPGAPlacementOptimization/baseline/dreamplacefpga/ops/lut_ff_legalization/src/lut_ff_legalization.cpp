/**
 * @file   lut_ff_legalization.cpp
 * @author Rachel Selina (DREAMPlaceFPGA-PL)
 * @date   Oct 2023
 * @brief  Legalize LUT/FF
 */

#include <omp.h>
#include <mutex>
#include <chrono>
#include <limits>
#include <vector>
#include <sstream>
#include <algorithm>
//pybind Dependency
#include <pybind11/pybind11.h>
#include <pybind11/stl_bind.h>
#include <pybind11/numpy.h>
//Lemon Graph Dependency 
#include "lemon/list_graph.h"
#include "lemon/matching.h"
#include "lemon/network_simplex.h"
//Common Dependency
#include "utility/src/torch.h"
#include "utility/src/utils.h"

DREAMPLACE_BEGIN_NAMESPACE

static const int INVALID = -1;
//Reset below values if required for the architecture
static const int SLICE_MAX_CAP = 20;
static const int SIG_MAX_CAP = 40;
static const int CE_MAX_CAP = 7;
static const int CKSR_MAX_CAP = 2;

//Mutex for critical section
std::mutex mtx;

//Struct for Candidate 
template <typename T>
struct Candidate 
{
    T score = 0.0;
    int siteId = INVALID;
    int sigIdx = 0;
    int sig[SIG_MAX_CAP];
    int impl_lut[SLICE_MAX_CAP];
    int impl_ff[SLICE_MAX_CAP];
    int impl_cksr[CKSR_MAX_CAP];
    int impl_ce[CE_MAX_CAP];

    void reset()
    {
        score = 0.0;
        siteId = INVALID;
        sigIdx = 0;

        for(int sg = 0; sg < SIG_MAX_CAP; ++sg)
        {
            sig[sg] = INVALID;
        }
        for(int sg = 0; sg < SLICE_MAX_CAP; ++sg)
        {
            impl_lut[sg] = INVALID;
            impl_ff[sg] = INVALID;
        }
        for(int sg = 0; sg < CKSR_MAX_CAP; ++sg)
        {
            impl_cksr[sg] = INVALID;
        }
        for(int sg = 0; sg < CE_MAX_CAP; ++sg)
        {
            impl_ce[sg] = INVALID;
        }
    }
};

//Struct for RipUpCand
template <typename T>
struct RipUpCand
{
    // If a < b, then a has higher priority than b
    bool operator<(const RipUpCand &rhs) const
    {
        return (legal == rhs.legal ? score > rhs.score : legal);
    }

    int siteId = INVALID;
    T score = -10000.0; 
    bool legal = false;
    Candidate<T> cand;

    void reset()
    {
        siteId = INVALID;
        score = -10000.0; 
        legal = false;
        cand.reset();
    }

};

//Struct for subSlice
template <typename T>
struct subSlice 
{
    int lut[2] = {INVALID, INVALID};
    int ff[2] = {INVALID, INVALID};
    T score = 0.0;
    T improv = 0.0;
};

//////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////

void clear_cand_contents(
        const int tsPQ, const int SIG_IDX, const int SLICE_CAPACITY,
        const int CKSR_IN_CLB, const int CE_IN_CLB,
        int* site_sig_idx, int* site_sig,
        int* site_impl_lut, int* site_impl_ff,
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
    site_sig_idx[tsPQ] = 0;
}

// check if candidate is valid
// Candidate is valid if the instance is not commited to a site
inline bool candidate_validity_check(
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

// define inst_in_sig
inline bool inst_in_sig(const int instId, const int siteDetSigSize, const int* site_det_sig, const int siteDetIdx)
{
    for(int i = 0; i < siteDetSigSize; ++i)
    {
        if (site_det_sig[siteDetIdx + i] == instId)
        {
            return true;
        }
    }
    return false;
}

// define two_lut_compatibility_check
inline bool two_lut_compatibility_check(
        const int* lut_type, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int lutTypeInSliceUnit, const int lut_maxShared, const int lutAId,
        const int lutBId)
{
    if (lut_type[lutAId] == lutTypeInSliceUnit || lut_type[lutBId] == lutTypeInSliceUnit)
    {
        return false;
    }

    int numInputs = lut_type[lutAId] + lut_type[lutBId];

    if (numInputs <= lut_maxShared)
    {
        return true;
    }

    //Handle LUT0
    if (lut_type[lutAId] == 0 || lut_type[lutBId] == 0)
    {
        return false;
    }

    //Note: It is important that nets of lutA and lutB are sorted before comparison
    std::vector<int> lutAiNets, lutBiNets;

    int lutAIt = flat_node2pin_start_map[lutAId];
    int lutBIt = flat_node2pin_start_map[lutBId];
    int lutAEnd = flat_node2pin_start_map[lutAId+1];
    int lutBEnd = flat_node2pin_start_map[lutBId+1];

    for (int el = lutAIt; el < lutAEnd; ++el)
    {
        //Skip if not an input pin
        if (pin_typeIds[flat_node2pin_map[el]] != 1) continue;

        int netId = pin2net_map[flat_node2pin_map[el]];
        lutAiNets.emplace_back(netId);
    }
    if (lutAiNets.size() > 1)
    {
        std::sort(lutAiNets.begin(), lutAiNets.end());
    }

    for (int el = lutBIt; el < lutBEnd; ++el)
    {
        //Skip if not an input pin
        if (pin_typeIds[flat_node2pin_map[el]] != 1) continue;

        int netId = pin2net_map[flat_node2pin_map[el]];
        lutBiNets.emplace_back(netId);
    }
    if (lutBiNets.size() > 1)
    {
        std::sort(lutBiNets.begin(), lutBiNets.end());
    }

    if (lutAiNets.size() == 0 || lutBiNets.size() == 0)
    {
        return false;
    }

    int idxA = 0, idxB = 0;
    int netIdA = lutAiNets[idxA];
    int netIdB = lutBiNets[idxB];

    while(numInputs > lut_maxShared)
    {
        if (netIdA < netIdB)
        {
            ++idxA;
            if (idxA < lutAiNets.size())
            {
                netIdA = lutAiNets[idxA];
            } else
            {
                break;
            }
        } else if (netIdA > netIdB)
        {
            ++idxB;
            if (idxB < lutBiNets.size())
            {
                netIdB = lutBiNets[idxB];
            } else
            {
                break;
            }

        } else
        {
            --numInputs;
            ++idxA;
            ++idxB;

            if (idxA < lutAiNets.size() && idxB < lutBiNets.size())
            {
                netIdA = lutAiNets[idxA];
                netIdB = lutBiNets[idxB];
            } else
            {
                break;
            }
        }
    }

    return numInputs <= lut_maxShared;
}

//Ensure flops in subSlice share the same set of ctrl signals
inline bool ffs_ctrl_match(
    const int* flat_node2pin_start_map, const int* flat_node2pin_map, 
    const int* pin_typeIds, const int* pin2net_map,
    const int ffInst, const int offInst)
{
    if (ffInst == INVALID || offInst == INVALID)
    {
        return true;
    }

    std::vector<int> ff_ctrl(10, INVALID);
    std::vector<int> off_ctrl(10, INVALID);
    std::vector<int> ff_pins, off_pins;

    int elIt = flat_node2pin_start_map[ffInst];
    int elEnd = flat_node2pin_start_map[ffInst+1];

    //std::cout << "FF " << ffInst << " has " << elEnd - elIt << " pins" << std::endl;

    for (int el = elIt; el < elEnd; ++el)
    {
        //Skip if not an input or output pin
        int pinType = pin_typeIds[flat_node2pin_map[el]];
        if (pinType < 3 || pinType > 9) continue;

        int netId = pin2net_map[flat_node2pin_map[el]];
        ff_ctrl[pinType] = netId;
        ff_pins.emplace_back(pinType);
    }

    if (ff_pins.size() == 0)
    {
        return true;
    }
    
    elIt = flat_node2pin_start_map[offInst];
    elEnd = flat_node2pin_start_map[offInst+1];
    //std::cout << "Other FF " << offInst << " has " << elEnd - elIt << " pins" << std::endl;

    for (int el = elIt; el < elEnd; ++el)
    {
        //Skip if not an input or output pin
        int pinType = pin_typeIds[flat_node2pin_map[el]];
        if (pinType < 3 || pinType > 9) continue;

        int netId = pin2net_map[flat_node2pin_map[el]];
        off_ctrl[pinType] = netId;
        off_pins.emplace_back(pinType);
    }

    if (off_pins.size() == 0)
    {
        return true;
    }
    
    std::sort(ff_pins.begin(), ff_pins.end());
    std::sort(off_pins.begin(), off_pins.end());

    int idxA = 0, idxB = 0;
    int pinTypeA = ff_pins[idxA];
    int pinTypeB = off_pins[idxB];

    //Only compare if pinType matches
    while (idxA < ff_pins.size() && idxB < off_pins.size())
    {
        if (pinTypeA < pinTypeB)
        {
            ++idxA;

            if (idxA < ff_pins.size())
            {
                pinTypeA = ff_pins[idxA];
            } else
            {
                break;
            }
        }
        else if (pinTypeA > pinTypeB)
        {
            ++idxB;

            if (idxB < off_pins.size())
            {
                pinTypeB = off_pins[idxB];
            } else
            {
                break;
            }
        } else
        {
            if (ff_ctrl[pinTypeA] != off_ctrl[pinTypeB])
            {
                return false;
            }

            ++idxA;
            ++idxB;

            if (idxA < ff_pins.size() && idxB < off_pins.size())
            {
                pinTypeA = ff_pins[idxA];
                pinTypeB = off_pins[idxB];
            } else
            {
                break;
            }
        }
    }

    return true;
}

//Ensure unique inputs and loopbacks of subSlice are within limits
inline bool subSlice_compatibility(
        const int* node2outpinIdx_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int* node2fence_region_map, const int* res_ff, const int* res_lut,
        const int lutId, const int SLICE_CAPACITY, const int BLE_CAPACITY,
        const int MAX_INPUTS_IN_SUBSLICE, const int MAX_LOOPBACK_IN_SUBSLICE,
        const int k, const int ssInstId)
{
    ////DBG
    //char printMsg = 0, foundLut(0), foundFF(0);    
    //int dbgLUTId = INVALID;
    //int dbgLUT1Id = INVALID;
    //int dbgFFId = INVALID;
    //int dbgFF1Id = INVALID;
    ////DBG

    int ssId = int(k/2)*2;
    std::vector<int> subSliceElements;

    if (res_lut[ssId] != INVALID)
    {
        subSliceElements.emplace_back(res_lut[ssId]);
        ////DBG
        //if (res_lut[ssId] == dbgLUTId || res_lut[ssId] == dbgLUT1Id)
        //{
        //    ++foundLut;
        //}
        ////DBG
    }

    if (res_ff[ssId] != INVALID)
    {
        subSliceElements.emplace_back(res_ff[ssId]);
        ////DBG
        //if (res_ff[ssId] == dbgFFId || res_ff[ssId] == dbgFF1Id)
        //{
        //    ++foundFF;
        //}
        ////DBG
    }

    if (res_lut[ssId+1] != INVALID)
    {
        subSliceElements.emplace_back(res_lut[ssId+1]);
        ////DBG
        //if (res_lut[ssId+1] == dbgLUTId || res_lut[ssId+1] == dbgLUT1Id)
        //{
        //    ++foundLut;
        //}
        ////DBG
    }

    if (res_ff[ssId+1] != INVALID)
    {
        subSliceElements.emplace_back(res_ff[ssId+1]);
        ////DBG
        //if (res_ff[ssId+1] == dbgFFId || res_ff[ssId+1] == dbgFF1Id)
        //{
        //    ++foundFF;
        //}
        ////DBG
    }

    //Check the new inst for compatibility
    if (ssInstId != INVALID)
    {
        subSliceElements.emplace_back(ssInstId);
        ////DBG
        //if (ssInstId == dbgLUTId || ssInstId == dbgLUT1Id)
        //{
        //    ++foundLut;
        //}
        //if (ssInstId == dbgFFId || ssInstId == dbgFF1Id)
        //{
        //    ++foundFF;
        //}
        ////DBG

        int lut_type = (node2fence_region_map[ssInstId] == lutId);
        int location_available = lut_type ? res_lut[k] == INVALID : res_ff[k] == INVALID;

        if (location_available == 0)
        {
            return false;
        }
        if (lut_type == 0 && (res_ff[ssId] != INVALID || res_ff[ssId + 1] != INVALID))
        {
            int ffA = (res_ff[ssId] != INVALID) ? res_ff[ssId] : res_ff[ssId + 1];
            if (!ffs_ctrl_match(flat_node2pin_start_map, flat_node2pin_map, 
                        pin_typeIds, pin2net_map, ffA, ssInstId))
            {
                return false;
            }
        }
    }

    if(subSliceElements.size() > 2*BLE_CAPACITY)
    {
        return false;
    }

    ////DBG
    //if (foundLut > 1 && foundFF > 1)
    //{
    //    printMsg = 1;
    //}
    ////DBG

    std::vector<int> all_inNets;
    //Check if LUT is driving FF in same subSlice
    int lut_ff_conns = 0;
    std::vector<int> lut_outNets;
    std::vector<int> ff_inNets;

    for (int elId = 0; elId < subSliceElements.size(); ++elId)
    {
        int instId = subSliceElements[elId];

        int lut_inst = (node2fence_region_map[instId] == lutId);

        int elIt = flat_node2pin_start_map[instId];
        int elEnd = flat_node2pin_start_map[instId+1];

        for (int el = elIt; el < elEnd; ++el)
        {
            //Skip if not an input or output pin
            int pinType = pin_typeIds[flat_node2pin_map[el]];

            if (lut_inst == 1 && pinType == 0)
            {
                lut_outNets.emplace_back(pin2net_map[flat_node2pin_map[el]]);
            }
            if (pinType != 1) continue;

            int netId = pin2net_map[flat_node2pin_map[el]];

            all_inNets.emplace_back(netId);

            if (lut_inst == 0)
            {
                ff_inNets.emplace_back(netId);
            }
        }
    }

    if (lut_outNets.size() > 0 && ff_inNets.size() > 0)
    {
        std::sort(lut_outNets.begin(), lut_outNets.end());
        lut_outNets.erase(std::unique(lut_outNets.begin(), lut_outNets.end()), lut_outNets.end());

        std::sort(ff_inNets.begin(), ff_inNets.end());
        ff_inNets.erase(std::unique(ff_inNets.begin(), ff_inNets.end()), ff_inNets.end());

        int idxIn = 0, idxOut = 0;
        int netIn = ff_inNets[idxIn];
        int netOut = lut_outNets[idxOut];

        while (true)
        {
            if (netIn < netOut)
            {
                ++idxIn;
                if (idxIn < ff_inNets.size())
                {
                    netIn = ff_inNets[idxIn];
                } else
                {
                    break;
                }
            } else if (netIn > netOut)
            {
                ++idxOut;
                if (idxOut < lut_outNets.size())
                {
                    netOut = lut_outNets[idxOut];
                } else
                {
                    break;
                }
            } else
            {
                ++lut_ff_conns;
                break;
            }
        }
    }

    std::sort(all_inNets.begin(), all_inNets.end());
    all_inNets.erase(std::unique(all_inNets.begin(), all_inNets.end()), all_inNets.end());

    if (all_inNets.size() > MAX_INPUTS_IN_SUBSLICE)
    {
        return false;
    }

    //////DBG
    ////if (printMsg == 1)
    ////{
    ////    printf("%d insts in subSlice: ", subSliceElements.size());
    ////    for (int elId = 0; elId < subSliceElements.size(); ++elId)
    ////    {
    ////        printf("%d ",subSliceElements[elId]);
    ////    }
    ////    printf("\n");

    ////    printf("There are %d input nets in ALM: ", all_inNets.size());
    ////    for (int elId = 0; elId < all_inNets.size(); ++elId)
    ////    {
    ////        printf("%d ",all_inNets[elId]);
    ////    }
    ////    printf("\n");
    ////}
    //////DBG


    ////Check loopback of all subSlices in the Slice
    //Get input nets from all subSlices
    for (int sg = 0; sg < SLICE_CAPACITY; sg += BLE_CAPACITY)
    {
        std::vector<int> subSlice_insts;

        if (sg == ssId) continue;

        //FFs
        if (res_ff[sg] != INVALID)
        {
            subSlice_insts.emplace_back(res_ff[sg]);
        }
        if (res_ff[sg+1] != INVALID)
        {
            subSlice_insts.emplace_back(res_ff[sg+1]);
        }

        //LUTs
        if (res_lut[sg] != INVALID)
        {
            subSlice_insts.emplace_back(res_lut[sg]);
        }
        if (res_lut[sg+1] != INVALID)
        {
            subSlice_insts.emplace_back(res_lut[sg+1]);
        }

        //Get input nets
        for (int el = 0; el < subSlice_insts.size(); ++el)
        {
            int instId = subSlice_insts[el];
            int pStart = flat_node2pin_start_map[instId];
            int pEnd = flat_node2pin_start_map[instId+1];

            for (int pId = pStart; pId < pEnd; ++pId)
            {
                int pinType = pin_typeIds[flat_node2pin_map[pId]];

                if (pinType != 1) continue;
                all_inNets.emplace_back(pin2net_map[flat_node2pin_map[pId]]);
            }
        }
    }

    std::sort(all_inNets.begin(), all_inNets.end());
    all_inNets.erase(std::unique(all_inNets.begin(), all_inNets.end()), all_inNets.end());

    if (all_inNets.size() == 0)
    {
        return true;
    }

    //Get nets from all subSlices
    for (int sg = 0; sg < SLICE_CAPACITY; sg += BLE_CAPACITY)
    {
        std::vector<int> subSlice_insts;
        std::vector<int> subSlice_outNets;

        if (sg == ssId)
        {
            subSlice_insts = subSliceElements;
        } else
        {
            //FFs
            if (res_ff[sg] != INVALID)
            {
                subSlice_insts.emplace_back(res_ff[sg]);
            }
            if (res_ff[sg+1] != INVALID)
            {
                subSlice_insts.emplace_back(res_ff[sg+1]);
            }

            //LUTs
            if (res_lut[sg] != INVALID)
            {
                subSlice_insts.emplace_back(res_lut[sg]);
            }
            if (res_lut[sg+1] != INVALID)
            {
                subSlice_insts.emplace_back(res_lut[sg+1]);
            }
        }

        for (int idx = 0; idx < subSlice_insts.size(); ++idx)
        {
            int instId = subSlice_insts[idx];

            int ndOutId = 4*instId;
            int ndOutPins = ndOutId + 4;
            for (int nodeOutId = ndOutId; nodeOutId < ndOutPins; ++nodeOutId)
            {
                int outPinId = node2outpinIdx_map[nodeOutId];
                if (outPinId == INVALID) continue;

                int outNetId = pin2net_map[outPinId];
                subSlice_outNets.emplace_back(outNetId);
            }
        }
        if (subSlice_outNets.size() <= MAX_LOOPBACK_IN_SUBSLICE) continue;
        std::sort(subSlice_outNets.begin(), subSlice_outNets.end());
        subSlice_outNets.erase(std::unique(subSlice_outNets.begin(), subSlice_outNets.end()), subSlice_outNets.end());

        int num_loopbacks = 0;
        //Compare sorted subSlice outNets with Slice input nets

        int idxIn = 0, idxOut = 0;
        int netIn = all_inNets[idxIn];
        int netOut = subSlice_outNets[idxOut];

        while (num_loopbacks <= MAX_LOOPBACK_IN_SUBSLICE)
        {
            if (netIn < netOut)
            {
                ++idxIn;
                if (idxIn < all_inNets.size())
                {
                    netIn = all_inNets[idxIn];
                } else
                {
                    break;
                }
            } else if (netIn > netOut)
            {
                ++idxOut;
                if (idxOut < subSlice_outNets.size())
                {
                    netOut = subSlice_outNets[idxOut];
                } else
                {
                    break;
                }
            } else
            {
                ++num_loopbacks;
                ++idxIn;
                ++idxOut;
                if (idxIn < all_inNets.size() && idxOut < subSlice_outNets.size())
                {
                    netIn = all_inNets[idxIn];
                    netOut = subSlice_outNets[idxOut];
                } else
                {
                    break;
                }
            }
        }
        if (sg == ssId && lut_ff_conns > 0)
        {
            --num_loopbacks;
        }

        if (num_loopbacks > MAX_LOOPBACK_IN_SUBSLICE)
        {
            return false;
        }
    }

    return true;
}

//Given lut arrangement, fit FFs
inline bool fit_ffs(
        const int* node2outpinIdx_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int* node2fence_region_map, const int* res_lut, const int lutId,
        const int lut_maxShared, const int SLICE_CAPACITY, const int BLE_CAPACITY,
        int* res_ff)
{
    ////DBG
    //char printMsg = 0;
    //int dbgInstId = INVALID;
    ////DBG

    //Rearrange all FFs based on compatibility
    std::vector<int> rem_ffs;
    int temp_ffs[SLICE_MAX_CAP];

    for (int sg = 0; sg < SLICE_CAPACITY; sg += BLE_CAPACITY)
    {
        temp_ffs[sg] = res_ff[sg];
        temp_ffs[sg + 1] = res_ff[sg + 1];

        if (res_ff[sg] != INVALID || res_ff[sg + 1] != INVALID)
        {
            if (!subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map,
                        flat_node2pin_map, pin2net_map, pin_typeIds, node2fence_region_map,
                        res_ff, res_lut, lutId, SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared,
                        BLE_CAPACITY, sg, INVALID))
            {
                if (res_ff[sg] != INVALID)
                {
                    rem_ffs.emplace_back(res_ff[sg]);
                    res_ff[sg] = INVALID;
                }
                if (res_ff[sg+1] != INVALID)
                {
                    rem_ffs.emplace_back(res_ff[sg+1]);
                    res_ff[sg+1] = INVALID;
                }
            }
        }
    }

    if (rem_ffs.size() == 0) return true;

    //Greedily assign FF to empty compatible location
    char ffLocFound = 0;
    for (int el = 0; el < rem_ffs.size(); ++el)
    {
        int ffId = rem_ffs[el];
        for (int sg = 0; sg < SLICE_CAPACITY; sg += BLE_CAPACITY)
        {
            if (res_ff[sg] == INVALID)
            {
                if (subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map, flat_node2pin_map,
                            pin2net_map, pin_typeIds, node2fence_region_map, res_ff, res_lut, lutId,
                            SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared, BLE_CAPACITY, sg, ffId))
                {
                    res_ff[sg] = ffId;
                    ++ffLocFound;
                    break;
                }
            } else if (res_ff[sg + 1] == INVALID)
            {
                if (subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map, flat_node2pin_map,
                            pin2net_map, pin_typeIds, node2fence_region_map, res_ff, res_lut, lutId,
                            SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared, BLE_CAPACITY, sg + 1, ffId))
                {
                    res_ff[sg + 1] = ffId;
                    ++ffLocFound;
                    break;
                }
            }
        }
    }

    if (ffLocFound == rem_ffs.size())
    {
        ////DBG
        //if (printMsg == 1)
        //{
        //    std::cout << "FFs after fit ffs: ";
        //    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
        //    {
        //        std::cout << res_ff[sg] << " ";
        //    }
        //    std::cout << std::endl;
        //}
        ////DBG

        return true;
    }

    ////DBG
    //if (printMsg == 1)
    //{
    //    std::cout << "FFs after fit ffs (failed): ";
    //    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
    //    {
    //        std::cout << res_ff[sg] << " ";
    //    }
    //    std::cout << std::endl;
    //}
    ////DBG

    //Revert
    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
    {
        res_ff[sg] = temp_ffs[sg];
    }

    return false;
}

//define check_sig_in_site_next_pq_sig
inline bool check_sig_in_site_next_pq_sig(
        const int* nwCand_sig, const int nwCand_sigIdx, const int sPQ,
        const int PQ_IDX, const int* site_next_pq_validIdx,
        const int* site_next_pq_sig, const int* site_next_pq_sig_idx,
        const int SIG_IDX)
{
    std::vector<int> candEls, nextEls;
    for (int x = 0; x < nwCand_sigIdx; ++x)
    {
        candEls.emplace_back(nwCand_sig[x]);
    }
    std::sort(candEls.begin(), candEls.end());

    for (int i = 0; i < PQ_IDX; ++i)
    {
        int sigIdx = sPQ + i;
        if (site_next_pq_validIdx[sigIdx] != INVALID && 
            site_next_pq_sig_idx[sigIdx] == nwCand_sigIdx)
        {
            int pqIdx(sigIdx*SIG_IDX);

            nextEls.clear();

            for (int x = 0; x < site_next_pq_sig_idx[sigIdx]; ++x)
            {
                nextEls.emplace_back(site_next_pq_sig[pqIdx + x]);
            }

            std::sort(nextEls.begin(), nextEls.end());

            if (candEls == nextEls)
            {
                return true;
            }
        }
    }
    return false;
}

//define add_inst_to_sig
inline bool add_inst_to_sig(
        const int node2prclstrCount, const int* flat_node2precluster_map,
        const int instPcl, int* nwCand_sig,
        int& nwCand_sigIdx, const int SLICE_CAPACITY)
{
    std::vector<int> temp;

    for (int el = 0; el < node2prclstrCount; ++el)
    {
        int newInstId = flat_node2precluster_map[instPcl+el];
        //Ensure instance is not in sig
        if (!inst_in_sig(newInstId, nwCand_sigIdx, nwCand_sig, 0))
        {
            temp.emplace_back(newInstId);
        } else
        {
            return false;
        }
    }

    if (nwCand_sigIdx + temp.size() > 2*SLICE_CAPACITY)
    {
        return false;
    }

    for (int mBIdx = 0; mBIdx < temp.size(); ++mBIdx)
    {
        nwCand_sig[nwCand_sigIdx] = temp[mBIdx];
        ++nwCand_sigIdx;
    }
    return true;
}

//define add flop to candidate
inline bool add_flop_to_candidate_impl(
        const int* node2outpinIdx_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int* extended_ctrlSets, const int* ext_ctrlSet_start_map,
        const int* flop2ctrlSetId_map, const int* node2fence_region_map,
        const int* res_lut, const int lutId, const int ffCKSR,
        const int ffCE, const int ffId, const int half_ctrl_mode,
        const int SLICE_CAPACITY, const int HALF_SLICE_CAPACITY,
        const int CKSR_IN_CLB, const int CE_IN_CLB, const int BLE_CAPACITY,
        const int lut_maxShared, int* res_ff, int* res_cksr, int* res_ce)
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

            ////DBG
            //int numffCtrls = fCEndId - fCStartId;
            //std::cout << "add flop to candidate: " << ffId << " with CKSR: "
            //          << ffCKSR << " and " << numffCtrls << " Ctrl signals to candidate" << std::endl;
            //std::cout << "FF Ctrl signals: ";
            //for (int j = fCStartId; j < fCEndId; ++j)
            //{
            //    std::cout << extended_ctrlSets[j] << " ";
            //}
            //std::cout << std::endl;
            //std::cout << "Existing Candidate ffs: ";
            //for (int t = 0; t < SLICE_CAPACITY; ++t)
            //{
            //    std::cout << res_ff[t] << " ";
            //}
            //std::cout << std::endl;
            //std::cout << " FF CKSR: ";
            //for (int t = 0; t < CKSR_IN_CLB; ++t)
            //{
            //    std::cout << res_cksr[t] << " ";
            //}
            //std::cout << std::endl;
            //std::cout << " FF CE: ";
            //for (int t = 0; t < CE_IN_CLB; ++t)
            //{
            //    std::cout << res_ce[t] << " ";
            //}
            //std::cout << std::endl;
            ////DBG

            std::vector<int> upd_ctrls;
            for (int sg = 0; sg < CE_IN_CLB; ++sg)
            {
                if (res_ce[sg] != INVALID)
                {
                    upd_ctrls.emplace_back(res_ce[sg]);
                }
            }

            int initial_ctrls = upd_ctrls.size();

            //For multiple ff ctrl signals - Ensure all signals can be accomodated
            for (int j = fCStartId; j < fCEndId; ++j)
            {
                int ffCtrl = extended_ctrlSets[j];
                upd_ctrls.emplace_back(ffCtrl);
            }

            if (upd_ctrls.size() > initial_ctrls)
            {
                std::sort(upd_ctrls.begin(), upd_ctrls.end());
                upd_ctrls.erase(std::unique(upd_ctrls.begin(), upd_ctrls.end()), upd_ctrls.end());
            }

            if (upd_ctrls.size() > CE_IN_CLB)
            {
                return false;
            }

            int fIndex = INVALID;
            for (int i = 0; i < SLICE_CAPACITY; i += BLE_CAPACITY)
            {
                if (res_ff[i] == INVALID)
                {
                    if(subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map, flat_node2pin_map,
                                pin2net_map, pin_typeIds, node2fence_region_map, res_ff, res_lut, lutId,
                                SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared, BLE_CAPACITY, i, ffId))
                    {
                        fIndex = i;
                    }
                } else if (res_ff[i+1] == INVALID)
                {

                    if(subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map, flat_node2pin_map,
                                pin2net_map, pin_typeIds, node2fence_region_map, res_ff, res_lut, lutId,
                                SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared, BLE_CAPACITY, i+1, ffId))
                    {
                        fIndex = i+1;
                    }
                }

                if (fIndex == INVALID)
                {
                    continue;
                }

                res_ff[fIndex] = ffId;
                res_cksr[ckID] = ffCKSR;

                for (int j = 0; j < upd_ctrls.size(); ++j)
                {
                    res_ce[j] = upd_ctrls[j];
                }
                for (int j = upd_ctrls.size(); j < CE_IN_CLB; ++j)
                {
                    res_ce[j] = INVALID;
                }

                ////DBG
                //std::cout << "SUCCEEDED to add flop: " << ffId << " with CKSR: "
                //          << ffCKSR << " and CE: " << ffCE << " to candidate" << std::endl;
                //std::cout << "UPDATED Candidate ffs: ";
                //for (int t = 0; t < SLICE_CAPACITY; ++t)
                //{
                //    std::cout << res_ff[t] << " ";
                //}
                //std::cout << std::endl;
                //std::cout << " FF CKSR: ";
                //for (int t = 0; t < CKSR_IN_CLB; ++t)
                //{
                //    std::cout << res_cksr[t] << " ";
                //}
                //std::cout << std::endl;
                //std::cout << " FF CE: ";
                //for (int t = 0; t < CE_IN_CLB; ++t)
                //{
                //    std::cout << res_ce[t] << " ";
                //}
                //std::cout << std::endl;
                ////DBG

                return true;
            }
        }
    }
    ////DBG
    //std::cout << "FAILED to add flop: " << ffId << " with CKSR: "
    //          << ffCKSR << " and CE: " << ffCE << "to candidate" << std::endl;
    ////DBG
    return false;
}

// define remove_invalid_neighbor
inline void remove_invalid_neighbor(
    const int sIdx, const int sNbrIdx, int* site_nbr_idx, int* site_nbr)
{
    std::vector<int> temp;
    for (int i = 0; i < site_nbr_idx[sIdx]; ++i)
    {
        if (site_nbr[sNbrIdx+i] != INVALID)
        {
            temp.emplace_back(site_nbr[sNbrIdx+i]);
        }
    }

    for(unsigned int j = 0; j < temp.size(); ++j)
    {
        site_nbr[sNbrIdx+j] = temp[j];
    }
    for(int j = (int)temp.size(); j < site_nbr_idx[sIdx]; ++j)
    {
        site_nbr[sNbrIdx+j] = INVALID;
    }
    site_nbr_idx[sIdx] = temp.size();
}

// define compute_wirelength_improv
template <typename T>
void compute_wirelength_improv(
        const T* pos_x, const T* pos_y, const T* net_bbox, const T* pin_offset_x,
        const T* pin_offset_y, const T* net_weights, const int* net_pinIdArrayX,
        const int* net_pinIdArrayY, const int* flat_net2pin_start_map,
        const int* pin2node_map, const int* net2pincount, const T* site_xy,
        const T xWirelenWt, const T yWirelenWt, const int currNetId,
        const int cand_siteId, const std::vector<int> &pins, T &result)
{
    int cNbId(currNetId*4);
    T netXlen = net_bbox[cNbId+2] - net_bbox[cNbId];
    T netYlen = net_bbox[cNbId+3] - net_bbox[cNbId+1];
    if ((int)pins.size() == net2pincount[currNetId])
    {
        T bXLo(pin_offset_x[pins[0]]);
        T bXHi(pin_offset_x[pins[0]]);
        T bYLo(pin_offset_y[pins[0]]);
        T bYHi(pin_offset_y[pins[0]]);

        for(auto poI = 1; poI < pins.size(); ++poI)
        {
            T poX = pin_offset_x[pins[poI]];
            T poY = pin_offset_y[pins[poI]];
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
        result += net_weights[currNetId] * (xWirelenWt * (netXlen - (bXHi-bXLo)) + yWirelenWt * (netYlen - (bYHi - bYLo)));
        return;
    }
    T bXLo(net_bbox[cNbId]);
    T bYLo(net_bbox[cNbId+1]);
    T bXHi(net_bbox[cNbId+2]);
    T bYHi(net_bbox[cNbId+3]);
    int cStId = cand_siteId*2;
    T locX = site_xy[cStId];
    T locY = site_xy[cStId+1];

    if (locX <= bXLo)
    {
        bXLo = locX;
    } else
    {
        int n2pId = flat_net2pin_start_map[currNetId];
        while(n2pId < flat_net2pin_start_map[currNetId+1] && 
                std::find(pins.begin(), pins.end(), net_pinIdArrayX[n2pId]) != pins.end())
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
        while(n2pId >= flat_net2pin_start_map[currNetId] && 
                std::find(pins.begin(), pins.end(), net_pinIdArrayX[n2pId]) != pins.end())
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
        while(n2pId < flat_net2pin_start_map[currNetId+1] && 
                std::find(pins.begin(), pins.end(), net_pinIdArrayY[n2pId]) != pins.end())
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
        while(n2pId >= flat_net2pin_start_map[currNetId] && 
                std::find(pins.begin(), pins.end(), net_pinIdArrayY[n2pId]) != pins.end())
        {
            --n2pId;
        }
        int reqPId = net_pinIdArrayY[n2pId];
        T pinY = pos_y[pin2node_map[reqPId]] + pin_offset_y[reqPId];
        bYHi = DREAMPLACE_STD_NAMESPACE::max(pinY, locY);
    }
    result += net_weights[currNetId] * (xWirelenWt * (netXlen - (bXHi-bXLo)) + yWirelenWt * (netYlen - (bYHi - bYLo)));
    return;
}

//addLUTToCandidateImpl
inline bool add_lut_to_cand_impl(
        const int* node2outpinIdx_map, const int* lut_type, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int* node2fence_region_map, const int* res_ff, const int lutId,
        const int lutTypeInSliceUnit, const int lut_maxShared,
        const int lutInstId, const int SLICE_CAPACITY, const int BLE_CAPACITY,
        const int half_ctrl_mode, int* res_lut)
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
                if (subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map,
                            flat_node2pin_map, pin2net_map, pin_typeIds, node2fence_region_map,
                            res_ff, res_lut, lutId, SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared,
                            BLE_CAPACITY, i, lutInstId))
                {
                    res_lut[i] = lutInstId;
                    return true;
                }
            } else if (res_lut[i+1] == INVALID)
            {
                if (subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map,
                            flat_node2pin_map, pin2net_map, pin_typeIds, node2fence_region_map,
                            res_ff, res_lut, lutId, SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared,
                            BLE_CAPACITY, i+1, lutInstId))
                {
                    res_lut[i+1] = lutInstId;
                    return true;
                }
            }
        }
    }

    return false;
}

//computeCandidateScore
template <typename T>
inline void compute_candidate_score(
        const T* pos_x, const T* pos_y, const T* pin_offset_x, const T* pin_offset_y,
        const T* net_bbox, const T* net_weights, const T* site_xy,
        const int* net_pinIdArrayX, const int* net_pinIdArrayY,
        const int* flat_net2pin_start_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* sorted_net_map, const int* pin2net_map,
        const int* pin2node_map, const int* net2pincount, const int* lut_type,
        const T xWirelenWt, const T yWirelenWt, const T extNetCountWt,
        const T wirelenImprovWt, const int netShareScoreMaxNetDegree,
        const int wlScoreMaxNetDegree, const int half_ctrl_mode,
        const int* res_sig, const int res_siteId, const int res_sigIdx, T &result)
{
    T netShareScore(0.0), wirelenImprov(0.0);
    T typeScore(0.0);
    std::vector<int> pins;

    for (int i = 0; i < res_sigIdx; ++i)
    {
        int instId = res_sig[i];
        //For macro nodes, same instId is repeated in sig
        if (i != 0 && instId == res_sig[i-1]) continue;
        for (int pId = flat_node2pin_start_map[instId]; pId < flat_node2pin_start_map[instId+1]; ++pId)
        {
            pins.emplace_back(flat_node2pin_map[pId]);
        }
        if (half_ctrl_mode == 0)
        {
            typeScore += lut_type[instId];
        }
    }
    std::sort(pins.begin(), pins.end(), [&pin2net_map,&sorted_net_map](const auto &a, const auto &b){ return pin2net_map[a] ==  pin2net_map[b] ? a < b : sorted_net_map[pin2net_map[a]] < sorted_net_map[pin2net_map[b]]; });

    if (pins.empty())
    {
        result = T(0.0);
        return;
    } 

    int maxNetDegree = DREAMPLACE_STD_NAMESPACE::max(netShareScoreMaxNetDegree, wlScoreMaxNetDegree);
    int currNetId = pin2net_map[pins[0]];

    if (net2pincount[currNetId] > maxNetDegree)
    {
        result = T(0.0);
        return;
    } 

    int numIntNets(0), numNets(0);
    std::vector<int> currNetIntPins;

    currNetIntPins.emplace_back(pins[0]);

    for(unsigned int pIdx = 1; pIdx < pins.size(); ++pIdx)
    {
        int netId = pin2net_map[pins[pIdx]];
        if (netId == currNetId)
        {
            currNetIntPins.emplace_back(pins[pIdx]);
        } else
        {
            if (net2pincount[currNetId] <= netShareScoreMaxNetDegree)
            {
                ++numNets;
                numIntNets += (currNetIntPins.size() == net2pincount[currNetId] ? 1 : 0);
                netShareScore += net_weights[currNetId] * (currNetIntPins.size() - 1.0) / DREAMPLACE_STD_NAMESPACE::max(1.0, net2pincount[currNetId] - 1.0);
            }
            if (net2pincount[currNetId] <= wlScoreMaxNetDegree)
            {
                compute_wirelength_improv(pos_x, pos_y, net_bbox, pin_offset_x, pin_offset_y, net_weights, net_pinIdArrayX, net_pinIdArrayY, flat_net2pin_start_map, pin2node_map, net2pincount, site_xy, xWirelenWt, yWirelenWt, currNetId, res_siteId, currNetIntPins, wirelenImprov);
            }
            currNetId = netId;
            if (net2pincount[currNetId] > maxNetDegree)
            {
                break;
            }
            currNetIntPins.clear();
            currNetIntPins.emplace_back(pins[pIdx]);
        }
    }

    if (net2pincount[currNetId] <= netShareScoreMaxNetDegree)
    {
        ++numNets;
        numIntNets += (currNetIntPins.size() == net2pincount[currNetId] ? 1 : 0);
        netShareScore += net_weights[currNetId] * (currNetIntPins.size() - 1.0) / DREAMPLACE_STD_NAMESPACE::max(1.0, net2pincount[currNetId] - 1.0);
    }
    ////DBG
    //if (res_siteId == dbg_siteId && res_sigIdx == dbg_sigIdx)
    //{
    //    std::cout << "Candidate score computation for res_siteId: " << res_siteId 
    //              << " with " << numNets << " total nets and " << numIntNets
    //              << " internal nets and net share score: " << netShareScore << std::endl;
    //}
    ////DBG

    if (net2pincount[currNetId] <= wlScoreMaxNetDegree)
    {
        compute_wirelength_improv(pos_x, pos_y, net_bbox, pin_offset_x, pin_offset_y,
                net_weights, net_pinIdArrayX, net_pinIdArrayY, flat_net2pin_start_map,
                pin2node_map, net2pincount, site_xy, xWirelenWt, yWirelenWt, currNetId,
                res_siteId, currNetIntPins, wirelenImprov);
    }

    netShareScore /= (T(1.0) + extNetCountWt * (numNets - numIntNets));
    result = netShareScore + wirelenImprovWt * wirelenImprov;

    if (half_ctrl_mode == 0)
    {
        result += T(0.1)*typeScore;
    }

    ////DBG
    //if (res_siteId == dbg_siteId && res_sigIdx == dbg_sigIdx)
    //{
    //    std::cout << "Candidate score computation for res_siteId: " << res_siteId 
    //              << " with updated netShareScore: " << netShareScore << " and final score: "
    //              << result << " based on wirelength improvement of " << wirelenImprov
    //              << std::endl;
    //}
    ////DBG
}

//fitLUTsToCandidateImpl
inline bool fit_luts_to_candidate_impl(
        const int* node2outpinIdx_map, const int* lut_type, const int* node2pincount,
        const int* net2pincount, const int* pin2net_map, const int* pin_typeIds,
        const int* flat_node2pin_start_map, const int* flat_node2pin_map,
        const int* flat_node2precluster_map, const int* node2fence_region_map,
        const int* special_nodes, const int half_ctrl_mode, const int lutTypeInSliceUnit,
        const int lut_maxShared, const int instPcl, const int node2prclstrCount,
        const int NUM_BLE_PER_SLICE, const int SLICE_CAPACITY, const int BLE_CAPACITY,
        const int lutId, int* res_ff, int* res_lut)
{
    std::vector<int> luts, lut6s, splNodes;

    ////DBG
    //std::cout << "fit luts to candidate impl: Try to add " << node2prclstrCount << " luts using graph matching to candidate: ";
    //for (int idx = 0; idx < node2prclstrCount; ++idx)
    //{
    //    int clInstId = flat_node2precluster_map[instPcl + idx];
    //    if (node2fence_region_map[clInstId] == lutId)
    //    {
    //        std::cout << clInstId << "(" << lut_type[clInstId] << ") ";
    //    }
    //}
    //std::cout << std::endl;

    //std::cout << " Candidate luts: ";
    //for (int t = 0; t < SLICE_CAPACITY; ++t)
    //{
    //    std::cout << res_lut[t] << "(" << lut_type[res_lut[t]] << ") ";
    //}
    //std::cout << std::endl;
    ////DBG
    //Ensure subSlice-level shared input count is met
    int temp_lut[SLICE_MAX_CAP];

    for (int i = 0; i < SLICE_CAPACITY; ++i)
    {
        if (res_lut[i] != INVALID)
        {
            if (special_nodes[res_lut[i]] == 1)
            {
                splNodes.emplace_back(res_lut[i]);
            } else
            {
                if (lut_type[res_lut[i]] < lutTypeInSliceUnit)
                {
                    luts.emplace_back(res_lut[i]);
                } else
                {
                    lut6s.emplace_back(res_lut[i]);
                }
            }
        }
        if (half_ctrl_mode == 0)
        {
            temp_lut[i] = res_lut[i];
        }
    }

    for (int idx = 0; idx < node2prclstrCount; ++idx)
    {
        int clInstId = flat_node2precluster_map[instPcl + idx];
        if (node2fence_region_map[clInstId] == lutId)
        {
            if (lut_type[clInstId] < lutTypeInSliceUnit)
            {
                luts.emplace_back(clInstId);
                std::sort(luts.begin(), luts.end());
                luts.erase(std::unique(luts.begin(), luts.end()), luts.end());
            } else
            {
                lut6s.emplace_back(clInstId);
                std::sort(lut6s.begin(), lut6s.end());
                lut6s.erase(std::unique(lut6s.begin(), lut6s.end()), lut6s.end());
            }
        }
    }

    int splNodeSpace = splNodes.size();
    splNodeSpace += (splNodes.size() & 1) ? 1 : 0;

    if (luts.size() + 2*lut6s.size() + splNodeSpace > SLICE_CAPACITY)
    {
        return false;
    }

    lemon::ListGraph graph;
    std::vector<lemon::ListGraph::Node> nodes;
    std::vector<lemon::ListGraph::Edge> edges;
    std::vector<std::pair<uint32_t, uint32_t> > edgePairs;
    graph.clear();
    nodes.clear();
    edges.clear();
    edgePairs.clear();

    int n = luts.size();
    //

    for (int il = 0; il < n; ++il)
    {
        nodes.emplace_back(graph.addNode());
    }
    for(int ll = 0; ll < n; ++ll)
    {
        for(int rl = ll+1; rl < n; ++rl)
        {
            if (two_lut_compatibility_check(lut_type, flat_node2pin_start_map, flat_node2pin_map,
                        pin2net_map, pin_typeIds, lutTypeInSliceUnit, lut_maxShared,
                        luts[ll], luts[rl]))
            {
                edges.emplace_back(graph.addEdge(nodes[ll], nodes[rl]));
                edgePairs.emplace_back(ll, rl);
            }
        }
    }

    lemon::MaxMatching<lemon::ListGraph> mm(graph);
    mm.run();

    int otherNodePairs = lut6s.size() + splNodeSpace/2;
    if (n - (int)mm.matchingSize() + otherNodePairs > NUM_BLE_PER_SLICE)
    {
        return false;
    } 

    int idxL(0);
    //Include special nodes first
    if (splNodes.size() > 0)
    {
        for (int spId = 0; spId < splNodes.size(); ++spId)
        {
            res_lut[idxL] = splNodes[spId];
            ++idxL;
        }
        if (splNodeSpace > splNodes.size())
        {
            res_lut[idxL] = INVALID;
            ++idxL;
        }
    }
    for (int iil = 0; iil < n; ++iil)
    {
        if (mm.mate(nodes[iil]) == lemon::INVALID && luts[iil] != INVALID)
        {
            res_lut[idxL] = luts[iil];
            res_lut[idxL + 1] = INVALID;
            idxL += BLE_CAPACITY;
        }
    }
    for(unsigned int iil = 0; iil < lut6s.size(); ++iil)
    {
        res_lut[idxL] = lut6s[iil];
        res_lut[idxL + 1] = INVALID;
        idxL += BLE_CAPACITY;
    }
    for (unsigned int iil = 0; iil < edges.size(); ++iil)
    {
        if (mm.matching(edges[iil]))
        {
            const auto &p = edgePairs[iil];
            res_lut[idxL] = luts[p.first];
            res_lut[idxL + 1] = luts[p.second];
            idxL += BLE_CAPACITY;
        }
    }

    for (int lIdx = idxL; lIdx < SLICE_CAPACITY; ++lIdx)
    {
        res_lut[lIdx] = INVALID;
    }

    ////DBG
    //std::cout << "SUCCEEDED fit luts to candidate impl: Try to add " << node2prclstrCount << " luts using graph matching to candidate: ";
    //for (int idx = 0; idx < node2prclstrCount; ++idx)
    //{
    //    int clInstId = flat_node2precluster_map[instPcl + idx];
    //    if (node2fence_region_map[clInstId] == lutId)
    //    {
    //        std::cout << clInstId << "(" << lut_type[clInstId] << ") ";
    //    }
    //}
    //std::cout << std::endl;

    //std::cout << " Candidate luts: ";
    //for (int t = 0; t < SLICE_CAPACITY; ++t)
    //{
    //    std::cout << res_lut[t] << "(" << lut_type[res_lut[t]] << ") ";
    //}
    //std::cout << std::endl;
    ////DBG


    //Ensure subSlice-level shared input count is met
    if (half_ctrl_mode == 0)
    {
        //Try to rearrange ffs if there are compatibility issues
        if (fit_ffs(node2outpinIdx_map, flat_node2pin_start_map, flat_node2pin_map,
                pin2net_map, pin_typeIds, node2fence_region_map, res_lut, lutId,
                lut_maxShared, SLICE_CAPACITY, BLE_CAPACITY, res_ff))
        {
            return true;
        }

        //Revert
        for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
        {
            res_lut[sg] = temp_lut[sg];
        }
        return false;
    }

    return true;
}

//template <typename T>
inline bool is_inst_in_cand_feasible(
        const int* node2outpinIdx_map, const int* node2fence_region_map, const int* lut_type,
        const int* flat_node2pin_start_map, const int* flat_node2pin_map,
        const int* node2pincount, const int* net2pincount, const int* pin2net_map,
        const int* pin_typeIds, const int* flat_node2prclstrCount,
        const int* flat_node2precluster_map, const int* flop2ctrlSetId_map,
        const int* flop_ctrlSets, const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map, const int* site_det_impl_lut,
        const int* site_det_impl_ff, const int* site_det_impl_cksr,
        const int* site_det_impl_ce, const int* special_nodes,
        const int lutTypeInSliceUnit, const int lut_maxShared,
        const int siteId, const int instId, const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY, const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE, const int CKSR_IN_CLB, const int CE_IN_CLB,
        const int lutId, const int ffId, const int half_ctrl_mode)
{
    int instPcl = instId*3;

    int sdlutId = siteId*SLICE_CAPACITY;
    int sdckId = siteId*CKSR_IN_CLB;
    int sdceId = siteId*CE_IN_CLB;

    /////
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

    bool lutFail(false);
    for (int idx = 0; idx < flat_node2prclstrCount[instId]; ++idx)
    {
        int clInstId = flat_node2precluster_map[instPcl + idx];
        int clInstCKSR = flop2ctrlSetId_map[clInstId]*3 + 1;
        int clInstCE = flop2ctrlSetId_map[clInstId]*3 + 2;

        if (node2fence_region_map[clInstId] == lutId) //LUT
        {
            if (!lutFail && !add_lut_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map,
                    flat_node2pin_map, pin2net_map, pin_typeIds, node2fence_region_map, res_ff, lutId,
                    lutTypeInSliceUnit, lut_maxShared, clInstId, SLICE_CAPACITY, BLE_CAPACITY,
                    half_ctrl_mode, res_lut))

            {
                lutFail = true;
            }
        } else if (node2fence_region_map[clInstId] == ffId) //FF
        {
            if(!add_flop_to_candidate_impl(node2outpinIdx_map, flat_node2pin_start_map,
                    flat_node2pin_map, pin2net_map, pin_typeIds, extended_ctrlSets, ext_ctrlSet_start_map,
                    flop2ctrlSetId_map, node2fence_region_map, res_lut, lutId, flop_ctrlSets[clInstCKSR],
                    flop_ctrlSets[clInstCE], clInstId, half_ctrl_mode, SLICE_CAPACITY, HALF_SLICE_CAPACITY,
                    CKSR_IN_CLB, CE_IN_CLB, BLE_CAPACITY, lut_maxShared, res_ff, res_cksr, res_ce))
            {
                return false;
            }
        }
    }
    if (!lutFail)
    {
        return true;
    }

    return fit_luts_to_candidate_impl(node2outpinIdx_map, lut_type, node2pincount, net2pincount,
                pin2net_map, pin_typeIds, flat_node2pin_start_map, flat_node2pin_map,
                flat_node2precluster_map, node2fence_region_map, special_nodes,
                half_ctrl_mode, lutTypeInSliceUnit, lut_maxShared, instPcl,
                flat_node2prclstrCount[instId], NUM_BLE_PER_SLICE, SLICE_CAPACITY,
                BLE_CAPACITY, lutId, res_ff, res_lut);
}

inline bool add_inst_to_cand_impl(
        const int* node2outpinIdx_map, const int* lut_type, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* node2pincount, const int* net2pincount,
        const int* pin2net_map, const int* pin_typeIds, const int* flat_node2prclstrCount,
        const int* flat_node2precluster_map, const int* flop2ctrlSetId_map,
        const int* node2fence_region_map, const int* flop_ctrlSets, const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map, const int* special_nodes, const int lutTypeInSliceUnit,
        const int lut_maxShared, const int instId, const int lutId, const int ffId,
        const int half_ctrl_mode, const int CKSR_IN_CLB, const int CE_IN_CLB, const int SLICE_CAPACITY, 
        const int HALF_SLICE_CAPACITY, const int BLE_CAPACITY, const int NUM_BLE_PER_SLICE,
        int* nwCand_lut, int* nwCand_ff, int* nwCand_cksr, int* nwCand_ce)
{
    int instPcl = instId*3;

    int res_lut[SLICE_MAX_CAP];
    int res_ff[SLICE_MAX_CAP];
    int res_ce[CE_MAX_CAP];
    int res_cksr[CKSR_MAX_CAP];

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

    bool lutFail(false);
    for (int idx = 0; idx < flat_node2prclstrCount[instId]; ++idx)
    {
        int clInstId = flat_node2precluster_map[instPcl + idx];
        int clInstCKSR = flop2ctrlSetId_map[clInstId]*3 + 1;
        int clInstCE = flop2ctrlSetId_map[clInstId]*3 + 2;

        if (node2fence_region_map[clInstId] == lutId) //LUT
        {
            if (!lutFail && !add_lut_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map, 
                    flat_node2pin_map, pin2net_map, pin_typeIds, node2fence_region_map, res_ff, lutId,
                    lutTypeInSliceUnit, lut_maxShared, clInstId, SLICE_CAPACITY, BLE_CAPACITY, half_ctrl_mode,
                    res_lut))
            {
                lutFail = true;
            }
        } else if (node2fence_region_map[clInstId] == ffId) //FF
        {
            if(!add_flop_to_candidate_impl(node2outpinIdx_map, flat_node2pin_start_map, flat_node2pin_map,
                    pin2net_map, pin_typeIds, extended_ctrlSets, ext_ctrlSet_start_map, flop2ctrlSetId_map,
                    node2fence_region_map, res_lut, lutId, flop_ctrlSets[clInstCKSR], flop_ctrlSets[clInstCE],
                    clInstId, half_ctrl_mode, SLICE_CAPACITY, HALF_SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB,
                    BLE_CAPACITY, lut_maxShared, res_ff, res_cksr, res_ce))
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
    if (fit_luts_to_candidate_impl(node2outpinIdx_map, lut_type, node2pincount,
            net2pincount, pin2net_map, pin_typeIds, flat_node2pin_start_map,
            flat_node2pin_map, flat_node2precluster_map, node2fence_region_map,
            special_nodes, half_ctrl_mode, lutTypeInSliceUnit, lut_maxShared,
            instPcl, flat_node2prclstrCount[instId], NUM_BLE_PER_SLICE,
            SLICE_CAPACITY, BLE_CAPACITY, lutId, res_ff, res_lut))
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
inline void remove_incompatible_neighbors(
        const int* node2outpinIdx_map, const int* node2fence_region_map, const int* lut_type,
        const int* flat_node2pin_start_map, const int* flat_node2pin_map, const int* node2pincount,
        const int* net2pincount, const int* pin2net_map, const int* pin_typeIds,
        const int* flat_node2prclstrCount, const int* flat_node2precluster_map,
        const int* flop2ctrlSetId_map,  const int* flop_ctrlSets, const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map, const int* site_det_impl_lut, const int* site_det_impl_ff,
        const int* site_det_impl_cksr, const int* site_det_impl_ce, const int* site_det_sig, 
        const int* site_det_sig_idx, const int* special_nodes, const int lutTypeInSliceUnit,
        const int lut_maxShared, const int siteId, const int sNbrIdx, const int half_ctrl_mode,
        const int SLICE_CAPACITY, const int HALF_SLICE_CAPACITY, const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE, const int SIG_IDX, const int CKSR_IN_CLB, const int CE_IN_CLB,
        const int lutId, const int ffId, int* site_nbr_idx, int* site_nbr)
{
    int sdtopId = siteId*SIG_IDX;
    for (int nbrId = 0; nbrId < site_nbr_idx[siteId]; ++nbrId)
    {
        int instId = site_nbr[sNbrIdx + nbrId];

        if (inst_in_sig(instId, site_det_sig_idx[siteId], site_det_sig, sdtopId) || 
            !is_inst_in_cand_feasible(node2outpinIdx_map, node2fence_region_map, lut_type, 
                flat_node2pin_start_map, flat_node2pin_map, node2pincount, net2pincount,
                pin2net_map, pin_typeIds, flat_node2prclstrCount, flat_node2precluster_map,
                flop2ctrlSetId_map, flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map,
                site_det_impl_lut, site_det_impl_ff, site_det_impl_cksr,
                site_det_impl_ce, special_nodes, lutTypeInSliceUnit, lut_maxShared,
                siteId, instId, SLICE_CAPACITY, HALF_SLICE_CAPACITY, BLE_CAPACITY,
                NUM_BLE_PER_SLICE, CKSR_IN_CLB, CE_IN_CLB, lutId, ffId, half_ctrl_mode))
        {
            site_nbr[sNbrIdx + nbrId] = INVALID;
        }
    }
    //Remove invalid neighbor instances
    remove_invalid_neighbor(siteId, sNbrIdx, site_nbr_idx, site_nbr);
}

template <typename T>
inline void computeBLEScore(
        const int* flat_node2pin_start_map, const int* flat_node2pin_map,
        const int* flat_net2pin_start_map, const int* flat_net2pin_map,
        const int* pin2net_map, const int* pin2node_map,
        const int* node2outpinIdx_map, const int* pin_typeIds,
        const int* lut_type, const int half_ctrl_mode, const int lutA,
        const int lutB, const int ffA, const int ffB, T& score)
{
    int numShareInputs = 0;

    if (lutA != INVALID && lutB != INVALID && lut_type[lutA] != 0 && lut_type[lutB] != 0)
    {
        //Note: It is important that nets of lutA and lutB are sorted before comparison
        std::vector<int> lutAiNets, lutBiNets;

        int lutAIt = flat_node2pin_start_map[lutA];
        int lutBIt = flat_node2pin_start_map[lutB];
        int lutAEnd = flat_node2pin_start_map[lutA+1];
        int lutBEnd = flat_node2pin_start_map[lutB+1];

        for (int el = lutAIt; el < lutAEnd; ++el)
        {
            //Skip if not an input pin
            if (pin_typeIds[flat_node2pin_map[el]] != 1) continue;

            int netId = pin2net_map[flat_node2pin_map[el]];
            lutAiNets.emplace_back(netId);
        }
        std::sort(lutAiNets.begin(), lutAiNets.end());

        for (int el = lutBIt; el < lutBEnd; ++el)
        {
            //Skip if not an input pin
            if (pin_typeIds[flat_node2pin_map[el]] != 1) continue;

            int netId = pin2net_map[flat_node2pin_map[el]];
            lutBiNets.emplace_back(netId);
        }
        std::sort(lutBiNets.begin(), lutBiNets.end());

        int idxA = 0, idxB = 0;
        int netIdA = lutAiNets[idxA];
        int netIdB = lutBiNets[idxB];

        while(true)
        {
            if (netIdA < netIdB)
            {
                ++idxA;
                if (idxA < lutAiNets.size())
                {
                    netIdA = lutAiNets[idxA];
                } else
                {
                    break;
                }
            } else if (netIdA > netIdB)
            {
                ++idxB;
                if (idxB < lutBiNets.size())
                {
                    netIdB = lutBiNets[idxB];
                } else
                {
                    break;
                }

            } else
            {
                ++numShareInputs;
                ++idxA;
                ++idxB;

                if (idxA < lutAiNets.size() && idxB < lutBiNets.size())
                {
                    netIdA = lutAiNets[idxA];
                    netIdB = lutBiNets[idxB];
                } else
                {
                    break;
                }
            }
        }
    }


    int numIntNets = 0;
    for (int id : {lutA, lutB})
    {
        if (id == INVALID) continue;

        int ndOutId = 4*id;
        int ndOutPins = ndOutId + 4;
        for (int nodeOutId = ndOutId; nodeOutId < ndOutPins; ++nodeOutId)
        {
            int outPinId = node2outpinIdx_map[nodeOutId];
            if (outPinId == INVALID) continue;

            int outNetId = pin2net_map[outPinId];
            for (int pId = flat_net2pin_start_map[outNetId];
                    pId < flat_net2pin_start_map[outNetId+1]; ++pId)
            {
                int pinId = flat_net2pin_map[pId];
                int nodeId = pin2node_map[pinId];
                if (pin_typeIds[pinId] == 1 && (nodeId == ffA || nodeId == ffB))
                {
                    ++numIntNets;
                }
            }
        }
    }
    score = T(0.1) * numShareInputs + numIntNets;
    T numFF = (ffA == INVALID ? 0:1) + (ffB == INVALID ? 0 : 1);

    if (half_ctrl_mode == 1)
    {
        score -= T(0.01)*numFF;
    } else
    {
        //Prefer more ffs being packed
        score += T(0.01)*numFF;
    }
}

template <typename T>
inline void findBestFFs(
        const int* flop_ctrlSets, const int* flop2ctrlSetId_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* flat_net2pin_start_map, const int* flat_net2pin_map,
        const int* pin2net_map, const int* node2pincount, const int* pin_typeIds, const int* net2pincount,
        const int* node2outpinIdx_map, const int* pin2node_map, const int* sorted_net_map,
        const int* lut_type, const std::vector<int> &ff, const int half_ctrl_mode,
        const int cksr, const int ce0, const int ce1, subSlice<T>& ble)
{
    ble.score = 0.0;
    ble.ff[0] = INVALID;
    ble.ff[1] = INVALID;

    for(unsigned int aIdx = 0; aIdx < ff.size(); ++aIdx)
    {
        const int ffA = ff[aIdx];
        int cksrA = flop_ctrlSets[flop2ctrlSetId_map[ffA]*3 + 1];
        int ceA = flop_ctrlSets[flop2ctrlSetId_map[ffA]*3 + 2];

        if (cksrA == cksr && (ceA == ce0 || ceA == ce1))
        {
            T score = 0.0; 
            computeBLEScore(flat_node2pin_start_map, flat_node2pin_map,flat_net2pin_start_map,
                flat_net2pin_map, pin2net_map, pin2node_map, node2outpinIdx_map,
                pin_typeIds, lut_type, half_ctrl_mode, ble.lut[0], ble.lut[1], ffA, INVALID, score);

            if (score > ble.score)
            {
                ble.ff[0] = ffA;
                ble.ff[1] = INVALID;
                if (ceA != ce0)
                {
                    std::swap(ble.ff[0], ble.ff[1]);
                }
                ble.score = score;
            }
        }
        //FF pairs
        for(unsigned int bIdx = aIdx + 1; bIdx < ff.size(); ++bIdx)
        {
            int ffB = ff[bIdx];
            int cksrB = flop_ctrlSets[flop2ctrlSetId_map[ffB]*3 + 1];
            int ceB = flop_ctrlSets[flop2ctrlSetId_map[ffB]*3 + 2];
            if (cksrA == cksr && cksrB == cksr && ((ceA == ce0 && ceB == ce1) || (ceA == ce1 && ceB == ce0)))
            {
                T score = 0.0; 
                computeBLEScore(flat_node2pin_start_map, flat_node2pin_map,flat_net2pin_start_map,
                    flat_net2pin_map, pin2net_map, pin2node_map, node2outpinIdx_map,
                    pin_typeIds, lut_type, half_ctrl_mode, ble.lut[0], ble.lut[1], ffA, ffB, score);

                if (score > ble.score)
                {
                    ble.ff[0] = ffA;
                    ble.ff[1] = ffB;
                    if (ceA != ce0)
                    {
                        std::swap(ble.ff[0], ble.ff[1]);
                    }
                    ble.score = score;
                }
            }
        }
    }
}

template <typename T>
void pairLUTs(
        const std::vector<int> &lut, const std::vector<subSlice<T> > &bleP, const std::vector<subSlice<T> > &bleS,
        const T slotAssignFlowWeightScale, const T slotAssignFlowWeightIncr, const int NUM_BLE_PER_SLICE,
        std::vector<subSlice<T> > &bleLP)
{
    lemon::ListGraph graph;
    std::vector<lemon::ListGraph::Node> nodes;
    std::vector<lemon::ListGraph::Edge> edges;
    graph.clear();
    nodes.clear();
    edges.clear();
    lemon::ListGraph::EdgeMap<int> wtMap(graph);

    // Get LUT ID to index mapping
    std::unordered_map<int, int> idxMap;
    for (unsigned int i = 0; i < lut.size(); ++i)
    {
        idxMap[lut[i]] = i;
    }
    // Build the graph use LUT pair score improvement as the edge weights
    for (unsigned int i = 0; i < lut.size(); ++i)
    {
        nodes.emplace_back(graph.addNode());
    }

    for (const auto &ble: bleP)
    {
        edges.emplace_back(graph.addEdge(nodes[idxMap[ble.lut[0]]], nodes[idxMap[ble.lut[1]]]));
        wtMap[edges.back()] = ble.improv * slotAssignFlowWeightScale;
    }
    // Use iterative max-weighted matching to find the best legal LUT pairing
    while (true)
    {
        lemon::MaxWeightedMatching<lemon::ListGraph, lemon::ListGraph::EdgeMap<int> > mwm(graph, wtMap);
        mwm.run();
        if (nodes.size() - mwm.matchingSize() <= NUM_BLE_PER_SLICE)
        {
            bleLP.clear();
            // Collect the LUT pairing solution
            for (unsigned int i = 0; i < edges.size(); ++i)
            {
                if (mwm.matching(edges[i]))
                {
                    bleLP.emplace_back(bleP[i]);
                }
            }
            for (unsigned int i = 0; i < nodes.size(); ++i)
            {
                if (mwm.mate(nodes[i]) == lemon::INVALID)
                {
                    bleLP.emplace_back(bleS[i]);
                }
            }
            return;
        }
        // Increase all edge weight to get a tighter LUT pairing solution
        int incr = slotAssignFlowWeightIncr * slotAssignFlowWeightScale;
        for (const auto &e : edges)
        {
            wtMap[e] += incr;
        }
    }
}

template <typename T>
inline bool compare_pq_tops(
        const T* site_curr_pq_score, const int* site_curr_pq_top_idx, const int* site_curr_pq_validIdx,
        const int* site_curr_pq_siteId, const int* site_curr_pq_sig_idx, const int* site_curr_pq_sig,
        const int* site_curr_pq_impl_lut, const int* site_curr_pq_impl_ff, const int* site_curr_pq_impl_cksr,
        const int* site_curr_pq_impl_ce, const T* site_next_pq_score, const int* site_next_pq_top_idx,
        const int* site_next_pq_validIdx, const int* site_next_pq_siteId, const int* site_next_pq_sig_idx,
        const int* site_next_pq_sig, const int* site_next_pq_impl_lut, const int* site_next_pq_impl_ff,
        const int* site_next_pq_impl_cksr, const int* site_next_pq_impl_ce, const int siteId,
        const int sPQ, const int SIG_IDX, const int CKSR_IN_CLB, const int CE_IN_CLB, const int SLICE_CAPACITY)
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
        /////
        return true;
    }
    return false;
}

//////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////

#define CHECK_FLAT(x) AT_ASSERTM(!x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on CPU")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel() & 1) == 0, #x "must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

// Initialize Nets
template <typename T>
int initializeNets(const T* pos_x,
                   const T* pos_y,
                   const T* pin_offset_x,
                   const T* pin_offset_y,
                   const int* flat_net2pin_start_map,
                   const int* flat_net2pin_map,
                   const int* sorted_net_idx,
                   const int* pin2node_map,
                   const int* net2pincount,
                   const int num_nets,
                   T* net_bbox,
                   int* net_pinIdArrayX,
                   int* net_pinIdArrayY,
                   int WLscoreMaxNetDegree,
                   const int num_threads)
{
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nets / num_threads / 16), 1);
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < num_nets; ++i)
    {
        const int idx = sorted_net_idx[i];

        if (net2pincount[idx] > 0 && net2pincount[idx] <= WLscoreMaxNetDegree)
        {
            int xLo = idx*4;
            int yLo = xLo+1;
            int xHi = xLo+2;
            int yHi = xLo+3;

            int pinIdBeg = flat_net2pin_start_map[idx];
            int pinIdEnd = flat_net2pin_start_map[idx+1];

            int pnIdx = flat_net2pin_map[pinIdBeg];
            int nodeIdx = pin2node_map[pnIdx];

            std::vector<std::pair<int, T> > tempX, tempY;

            net_bbox[xLo] = pos_x[nodeIdx] + pin_offset_x[pnIdx];
            net_bbox[yLo] = pos_y[nodeIdx] + pin_offset_y[pnIdx];
            net_bbox[xHi] = net_bbox[xLo];
            net_bbox[yHi] = net_bbox[yLo];

            tempX.emplace_back(pnIdx, net_bbox[xLo]);
            tempY.emplace_back(pnIdx, net_bbox[yLo]);

            //Update Net Bbox based on node location and pin offset
            for (int pId = pinIdBeg+1; pId < pinIdEnd; ++pId)
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

                tempX.emplace_back(pinIdx, valX);
                tempY.emplace_back(pinIdx, valY);
            }

            //Sort pinIdArray based on node loc and pin offset
            std::sort(tempX.begin(), tempX.end(), [&](const auto &a, const auto &b){ return a.second < b.second; });
            std::sort(tempY.begin(), tempY.end(), [&](const auto &a, const auto &b){ return a.second < b.second; });

            //Assign sorted values back
            int tempId(0);
            for (int pId = pinIdBeg; pId < pinIdEnd; ++pId)
            {
                net_pinIdArrayX[pId] = tempX[tempId].first;
                net_pinIdArrayY[pId] = tempY[tempId].first;
                ++tempId;
            }
        }
    }
    return 0;
}

// preClustering 
template <typename T>
int preClustering(const T* pos_x,
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
                  const int lutId,
                  const int ffId,
                  const int num_nodes,
                  const T preClusteringMaxDist,
                  int* flat_node2precluster_map,
                  int* flat_node2prclstrCount,
                  const int num_threads)
{
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nodes / num_threads / 16), 1);
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < num_nodes; ++i)
    {
        const int instId = sorted_node_idx[i];
        if (node2fence_region_map[instId] == lutId) //Only consider LUTs
        {
            std::vector<std::pair<int, T> > ffs;
            int nPIdx = instId*4;
            for (int nodeOutId = nPIdx; nodeOutId < nPIdx+4; ++nodeOutId)
            {
                int outPinId = node2outpinIdx_map[nodeOutId];
                if (outPinId == INVALID) continue;

                int outNetId = pin2net_map[outPinId];

                int pinIdxBeg = flat_net2pin_start_map[outNetId];
                int pinIdxEnd = flat_net2pin_start_map[outNetId+1];

                T instLocX = pos_x[instId] + pin_offset_x[outPinId];
                T instLocY = pos_y[instId] + pin_offset_y[outPinId];
                for (int pinId = pinIdxBeg; pinId < pinIdxEnd; ++pinId)
                {
                    int pinIdx = flat_net2pin_map[pinId];
                    int nodeIdx = pin2node_map[pinIdx];

                    T distX = instLocX - pos_x[nodeIdx] - pin_offset_x[pinIdx];
                    T distY = instLocY - pos_y[nodeIdx] - pin_offset_y[pinIdx];

                    T dist = DREAMPLACE_STD_NAMESPACE::abs(distX) + DREAMPLACE_STD_NAMESPACE::abs(distY);

                    if (pin_typeIds[pinIdx] == 1 && node2fence_region_map[nodeIdx] == ffId &&
                            dist <= preClusteringMaxDist)
                    {
                        ffs.emplace_back(std::make_pair(nodeIdx, dist));
                    }
                }
            }
            if (ffs.empty())
            {
                continue;
            }

            //Get FF index with min value (without Sort FFs)
            std::sort(ffs.begin(), ffs.end(), [&sorted_node_map](const auto &a, const auto &b){ return a.second == b.second ? sorted_node_map[a.first] < sorted_node_map[b.first] : a.second < b.second; });

            nPIdx = instId*3;
            flat_node2precluster_map[nPIdx + flat_node2prclstrCount[instId]] = ffs[0].first;
            ++flat_node2prclstrCount[instId];
            int fcIdx = flop2ctrlSetId_map[ffs[0].first]*3 + 1;
            int cksr = flop_ctrlSets[fcIdx];

            for (unsigned int fIdx = 1; fIdx < ffs.size(); ++fIdx)
            {
                int ctrlIdx = flop2ctrlSetId_map[ffs[fIdx].first]*3 + 1;
                int fCksr = flop_ctrlSets[ctrlIdx];

                if (fCksr == cksr)
                {
                    flat_node2precluster_map[nPIdx + flat_node2prclstrCount[instId]] = ffs[fIdx].first;
                    ++flat_node2prclstrCount[instId];
                    //std::cout << "BEFORE SORT: Inst Id: " << instId << " has precluster: " << flat_node2precluster_map[nPIdx] << ", " << flat_node2precluster_map[nPIdx + 1] << ", " <<  flat_node2precluster_map[nPIdx + 2] << std::endl;
                    break;
                }
            }

            std::sort(flat_node2precluster_map+nPIdx, flat_node2precluster_map+nPIdx + flat_node2prclstrCount[instId], [&sorted_node_map](const auto &a, const auto &b){return sorted_node_map[a] < sorted_node_map[b];});

            for (int prcl = 0; prcl < flat_node2prclstrCount[instId]; ++prcl) 
            {
                int fIdx = flat_node2precluster_map[nPIdx + prcl];
                int fID = fIdx*3;
                if (fIdx != instId)
                {
                    for (int cl = 0; cl < flat_node2prclstrCount[instId]; ++cl)
                    {
                        flat_node2precluster_map[fID + cl] = flat_node2precluster_map[nPIdx + cl];
                    }
                    flat_node2prclstrCount[fIdx] = flat_node2prclstrCount[instId];
                }
            }
        }
    }
    return 0;
}

//TODO-Remove is_mlab_node when MLABs are treated separately
//Preclustering to handle carry chains and mlabs
template <typename T>
int preClusteringUpd(
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
        int* flat_node2prclstrCount,
        const int num_threads)
{
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nodes / num_threads / 16), 1);
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < num_nodes; ++i)
    {
        const int instId = sorted_node_idx[i];
        //Only consider LUTs and skip MLABs
        if (node2fence_region_map[instId] == lutId && is_mlab_node[instId] == 0)
        {
            std::vector<std::pair<int, T> > ffs;
            int nPIdx = instId*4;
            for (int nodeOutId = nPIdx; nodeOutId < nPIdx+4; ++nodeOutId)
            {
                int outPinId = node2outpinIdx_map[nodeOutId];
                if (outPinId == INVALID) continue;

                int outNetId = pin2net_map[outPinId];

                int pinIdxBeg = flat_net2pin_start_map[outNetId];
                int pinIdxEnd = flat_net2pin_start_map[outNetId+1];

                T instLocX = pos_x[instId] + pin_offset_x[outPinId];
                T instLocY = pos_y[instId] + pin_offset_y[outPinId];

                for (int pinId = pinIdxBeg; pinId < pinIdxEnd; ++pinId)
                {
                    int pinIdx = flat_net2pin_map[pinId];
                    int nodeIdx = pin2node_map[pinIdx];

                    T distX = instLocX - pos_x[nodeIdx] - pin_offset_x[pinIdx];
                    T distY = instLocY - pos_y[nodeIdx] - pin_offset_y[pinIdx];

                    T dist = DREAMPLACE_STD_NAMESPACE::abs(distX) + DREAMPLACE_STD_NAMESPACE::abs(distY);

                    if (pin_typeIds[pinIdx] == 1 && node2fence_region_map[nodeIdx] == ffId &&
                            dist <= preClusteringMaxDist)
                    {
                        ffs.emplace_back(std::make_pair(nodeIdx, dist));
                    }
                }
            }
            if (ffs.empty())
            {
                continue;
            }

            //Get FF index with min value (without Sort FFs)
            std::sort(ffs.begin(), ffs.end(), [&sorted_node_map](const auto &a, const auto &b){ return a.second == b.second ? sorted_node_map[a.first] < sorted_node_map[b.first] : a.second < b.second; });

            nPIdx = instId*3;
            flat_node2precluster_map[nPIdx + flat_node2prclstrCount[instId]] = ffs[0].first;
            ++flat_node2prclstrCount[instId];
            int fcIdx = flop2ctrlSetId_map[ffs[0].first]*3 + 1;
            int cksr = flop_ctrlSets[fcIdx];

            if (ffs.size() > 1)
            {
                for (unsigned int fIdx = 1; fIdx < ffs.size(); ++fIdx)
                {
                    int ctrlIdx = flop2ctrlSetId_map[ffs[fIdx].first]*3 + 1;
                    int fCksr = flop_ctrlSets[ctrlIdx];

                    if (fCksr == cksr)
                    {
                        flat_node2precluster_map[nPIdx + flat_node2prclstrCount[instId]] = ffs[fIdx].first;
                        ++flat_node2prclstrCount[instId];
                        //std::cout << "BEFORE SORT: Inst Id: " << instId << " has precluster: " << flat_node2precluster_map[nPIdx] << ", " << flat_node2precluster_map[nPIdx + 1] << ", " <<  flat_node2precluster_map[nPIdx + 2] << std::endl;
                        break;
                    }
                }
            }

            std::sort(flat_node2precluster_map+nPIdx, flat_node2precluster_map+nPIdx + flat_node2prclstrCount[instId], [&sorted_node_map](const auto &a, const auto &b){return sorted_node_map[a] < sorted_node_map[b];});

            for (int prcl = 0; prcl < flat_node2prclstrCount[instId]; ++prcl)
            {
                int fIdx = flat_node2precluster_map[nPIdx + prcl];
                int fID = fIdx*3;
                if (fIdx != instId)
                {
                    for (int cl = 0; cl < flat_node2prclstrCount[instId]; ++cl)
                    {
                        flat_node2precluster_map[fID + cl] = flat_node2precluster_map[nPIdx + cl];
                    }
                    flat_node2prclstrCount[fIdx] = flat_node2prclstrCount[instId];
                }
            }
        }
    }
    return 0;
}

// legalize carry chains
template <typename T>
int legalizeCarryChainsLauncher(
        const T* pos_x,
        const T* pos_y,
        const T* site_xy,
        const T* wlPrecond,
        const int* site2addr_map,
        const int* flat_cc2node_start_map,
        const int* flat_cc2node_map,
        const int* spiral_accessor,
        const int* site_types,
        const int spiralBegin,
        const int spiralEnd,
        const int num_carry_chains,
        const int num_sites_x,
        const int num_sites_y,
        const int sliceId,
        const int SIG_IDX,
        const int SLICE_CAPACITY,
        const int num_carryInstsInSlice,
        const int slice_minX,
        const int slice_maxX,
        const int slice_minY,
        const int slice_maxY,
        T* carry_chain_displacements,
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
        int* sites_with_special_nodes,
        const int num_threads)
{
    int maxRad = DREAMPLACE_STD_NAMESPACE::max(num_sites_x, num_sites_y);

    std::vector<std::vector<int> > carry_chain(num_carry_chains);
    std::vector<int> carry_chain_size(num_carry_chains, 0);
    std::vector<T> centroidX(num_carry_chains, 0.0), centroidY(num_carry_chains, 0.0);

    int HALF_SLICE_CAPACITY = int(SLICE_CAPACITY/2);

    uint32_t legalcc = 0;

    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_carry_chains / num_threads / 16), 1);
#pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < num_carry_chains; ++i)
    {
        T cenX(0), cenY(0), totalWt(0);

        for (int ccIdx = flat_cc2node_start_map[i]; ccIdx < flat_cc2node_start_map[i+1]; ++ccIdx)
        {
            int instId = flat_cc2node_map[ccIdx];
            carry_chain[i].emplace_back(instId);

            cenX += pos_x[instId] * wlPrecond[instId];
            cenY += pos_y[instId] * wlPrecond[instId];
            totalWt += wlPrecond[instId];
        }

        carry_chain_size[i] = carry_chain[i].size();

        if (totalWt > 0)
        {
            cenX /= totalWt;
            cenY /= totalWt;
        }

        centroidX[i] = cenX;
        centroidY[i] = cenY;
    }

    //Sort based on carry chain size
    std::vector<int> sorted_carry_chains(num_carry_chains);
    std::iota(sorted_carry_chains.begin(),sorted_carry_chains.end(),0); //Initializing
    std::sort(sorted_carry_chains.begin(),sorted_carry_chains.end(), [&](int i,int j){return carry_chain_size[i]>carry_chain_size[j];} );

    for (int i = 0; i < num_carry_chains; ++i)
    {
        const int idx = sorted_carry_chains[i];
        int elCount = carry_chain_size[idx];
        dreamplaceAssertMsg(elCount, "Carry chain of size 0 encountered - CHECK");

        int sliceSpread = std::ceil(elCount/num_carryInstsInSlice) + 1;

        int cenX = centroidX[idx];
        int cenY = centroidY[idx];

        int beg(spiralBegin), end(spiralEnd);
        T bestX = INVALID;
        T bestY = INVALID;
        T bestScore = 10000000;

        for (int sId = beg; sId < end; ++sId)
        {
            int xVal = cenX + spiral_accessor[2*sId];
            int yVal = cenY + spiral_accessor[2*sId+1];
            int siteId = xVal*num_sites_y + yVal;
            int sIdx = site2addr_map[siteId];

            //Check within bounds
            if (xVal < slice_minX || xVal > slice_maxX || yVal < slice_minY || yVal > slice_maxY)
            {
                continue;
            }

            int startY = yVal + sliceSpread-1;

            if (site_types[siteId] == sliceId && startY <= slice_maxY)
            {
                char space_available = 1;
                for (int yId = yVal; yId <= startY; ++yId)
                {
                    int siteMap = xVal*num_sites_y + yId;
                    int sMap = site2addr_map[siteMap];

                    if (site_types[siteMap] != sliceId || site_det_sig_idx[sMap] > 0)
                    {
                        space_available = 0;
                        break;
                    }
                }

                //Legalize carry chain if space is available
                if (space_available == 1)
                {
                    if (bestScore == 10000000)
                    {
                        int r = DREAMPLACE_STD_NAMESPACE::abs(spiral_accessor[2*sId]) +
                            DREAMPLACE_STD_NAMESPACE::abs(spiral_accessor[2*sId+1]); 
                        r += 2;
                        int nwR = DREAMPLACE_STD_NAMESPACE::min(maxRad, r);
                        end = nwR ? 2 * (nwR + 1) * nwR + 1 : 1;
                    }

                    T dist_score = DREAMPLACE_STD_NAMESPACE::abs(cenX - site_xy[siteId*2]) + 
                        DREAMPLACE_STD_NAMESPACE::abs(cenY - site_xy[siteId*2+1]);
                    if (dist_score < bestScore)
                    {
                        bestX = xVal;
                        bestY = yVal;
                        bestScore = dist_score;
                    }
                }
            }
        }

        if (bestX != INVALID && bestY != INVALID)
        {
            carry_chain_displacements[idx] = 0;
            int startY = bestY + sliceSpread -1;
            int elements_left = elCount;
            int instOffset = 0;

            for (int yId = startY; yId >= bestY; --yId)
            {
                int bSiteId = bestX * num_sites_y + yId;
                int bSIdx = site2addr_map[bSiteId];
                int sdtopId = bSIdx*SIG_IDX;
                int sdlutId = bSIdx*SLICE_CAPACITY;

                int insts_added = DREAMPLACE_STD_NAMESPACE::min(elements_left, SLICE_CAPACITY);

                elements_left -= insts_added;

                if (site_det_sig_idx[bSIdx] == 0)
                {
                    sites_with_special_nodes[bSIdx] = 1;
                    site_det_score[bSIdx] = 100.0;
                    site_det_siteId[bSIdx] = bSiteId;
                    for(int sg = 0; sg < insts_added; ++sg)
                    {
                        int instAdd = carry_chain[idx][instOffset];
                        site_det_sig[sdtopId + sg] = instAdd;
                        site_det_impl_lut[sdlutId + sg] = instAdd;

                        inst_curr_detSite[instAdd] = bSiteId;
                        inst_curr_bestSite[instAdd] = bSiteId;
                        inst_curr_bestScoreImprov[instAdd] = 10000.0;

                        inst_next_detSite[instAdd] = bSiteId;
                        inst_next_bestSite[instAdd] = bSiteId;
                        inst_next_bestScoreImprov[instAdd] = 10000.0;

                        carry_chain_displacements[idx] += DREAMPLACE_STD_NAMESPACE::abs(pos_x[instAdd] - site_xy[bSiteId*2]) + 
                            DREAMPLACE_STD_NAMESPACE::abs(pos_y[instAdd] - site_xy[bSiteId*2+1]);

                        ++instOffset;
                    }
                    site_det_sig_idx[bSIdx] += insts_added;
                }
                //DBG
                else {
                    std::cout << "ERROR: More than one carry chain node legalized at site: (" << bestX << ", " << yId << ")" << std::endl;
                }
                //DBG
            }
            carry_chain_displacements[idx] /= elCount;
            ++legalcc;
        }
    }

    //DBG
    if (legalcc != num_carry_chains)
    {
        std::cout << "ERROR: Only " << legalcc << " carry chains legalized out of " << num_carry_chains << " - CHECK!" << std::endl;
    }
    //DBG

    return 0;
}

// legalize Slice Macros 
template <typename T>
int legalizeMacrosLauncher(
        const T* pos_x,
        const T* pos_y,
        const T* site_xy,
        const int* macro2node_map,
        const int* macro_site_height,
        const int* macro_element_count,
        const int* site2addr_map,
        const int* spiral_accessor,
        const int* site_types,
        const int spiralBegin,
        const int spiralEnd,
        const int num_macros,
        const int num_sites_x,
        const int num_sites_y,
        const int slice_minX,
        const int slice_maxX,
        const int slice_minY,
        const int slice_maxY,
        const int sliceId,
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
    int maxRad = DREAMPLACE_STD_NAMESPACE::max(num_sites_x, num_sites_y);
    //Use macro_site_x/y locations as guidance to legalize macros
    std::vector<int> sorted_macroIds(num_macros);
    std::iota(sorted_macroIds.begin(),sorted_macroIds.end(),0); //Initializing

    //Sort macros based on Slices occupied
    std::sort(sorted_macroIds.begin(),sorted_macroIds.end(), [&](int i,int j){return macro_element_count[i]>macro_element_count[j];} );

    for (int i = 0; i < num_macros; ++i)
    {
        const int macroId = sorted_macroIds[i];
        const int instId = macro2node_map[macroId];
        int sliceSpread = macro_site_height[macroId];
        dreamplaceAssertMsg(sliceSpread, "Macro of size 0 encountered - CHECK");
        int macroElCount = macro_element_count[macroId];

        T initX = pos_x[instId];
        T initY = pos_y[instId];

        int beg(spiralBegin), end(spiralEnd);
        T bestX = INVALID;
        T bestY = INVALID;
        T bestScore = 10000000;

        for (int sId = beg; sId < end; ++sId)
        {
            int xVal = initX + spiral_accessor[2*sId]; 
            int yVal = initY + spiral_accessor[2*sId+1]; 
            int siteId = xVal * num_sites_y + yVal;
            int sIdx = site2addr_map[siteId];

            //Check within bounds
            if (xVal < slice_minX || xVal > slice_maxX || yVal < slice_minY || yVal > slice_maxY)
            {
                continue;
            }

            int startY = yVal + sliceSpread -1;
            if (site_types[siteId] == sliceId && startY <= slice_maxY)
            {
                char space_available = 1;
                for (int yId = yVal; yId <= startY; ++yId)
                {
                    int siteMap = xVal*num_sites_y + yId;
                    int sMap = site2addr_map[siteMap];
                    if (site_types[siteMap] != sliceId || site_det_sig_idx[sMap] > 0)
                    {
                        space_available = 0;
                    }
                }

                if (space_available == 1)
                {
                    if (bestScore == 10000000)
                    {
                        int r = DREAMPLACE_STD_NAMESPACE::abs(spiral_accessor[2*sId]) +
                            DREAMPLACE_STD_NAMESPACE::abs(spiral_accessor[2*sId+1]); 
                        r += 2;
                        int nwR = DREAMPLACE_STD_NAMESPACE::min(maxRad, r);
                        end = nwR ? 2 * (nwR + 1) * nwR + 1 : 1;
                    }

                    T dist_score = DREAMPLACE_STD_NAMESPACE::abs(pos_x[instId] - site_xy[siteId*2]) + 
                        DREAMPLACE_STD_NAMESPACE::abs(pos_y[instId] - site_xy[siteId*2+1]);
                    if (dist_score < bestScore)
                    {
                        bestX = xVal;
                        bestY = yVal;
                        bestScore = dist_score;
                    }
                }
            }
        }

        if (bestX != INVALID && bestY != INVALID)
        {
            dist_moved[macroId] = bestScore;
            int elements_left = macroElCount;
            int bSiteId = bestX * num_sites_y + bestY;

            inst_curr_detSite[instId] = bSiteId;
            inst_curr_bestSite[instId] = bSiteId;
            inst_curr_bestScoreImprov[instId] = 10000.0;

            inst_next_detSite[instId] = bSiteId;
            inst_next_bestSite[instId] = bSiteId;
            inst_next_bestScoreImprov[instId] = 10000.0;

            int startY = bestY + sliceSpread -1;

            for (int yId = startY; yId >= bestY; --yId)
            {
                bSiteId = bestX * num_sites_y + yId;
                int bSIdx = site2addr_map[bSiteId];
                int sdtopId = bSIdx*SIG_IDX;
                int sdlutId = bSIdx*SLICE_CAPACITY;

                int insts_added = DREAMPLACE_STD_NAMESPACE::min(elements_left, SLICE_CAPACITY);

                elements_left -= insts_added;
                if (site_det_sig_idx[bSIdx] == 0)
                {
                    sites_with_special_nodes[bSIdx] = 1;
                    site_det_score[bSIdx] = 1000.0;
                    site_det_siteId[bSIdx] = bSiteId;
                    for(int sg = 0; sg < insts_added; ++sg)
                    {
                        //Include same nodeId across the macro span
                        site_det_sig[sdtopId + sg] = instId;
                        site_det_impl_lut[sdlutId + sg] = instId;
                    }
                    site_det_sig_idx[bSIdx] += insts_added;
                }
                //DBG
                else {
                    std::cout << "ERROR: Site not empty - Macro not legalized at (" << bestX << ", " << yId << ")" << std::endl;
                }
                //DBG
            }
        }
    }

    return 0;
}

// legalize mlabs
template <typename T>
int legalizeMlabsLauncher(
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
        int* sites_with_special_nodes,
        const int num_threads)
{
    //Assign mlabs to site locations provided
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_mlab_nodes/ num_threads / SLICE_CAPACITY), 1);
#pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < num_mlab_nodes; ++i)
    {
        const int instId = mlab_indices[i];

        T xVal = mlab_locX[i];
        T yVal = mlab_locY[i];

        int siteId = xVal * num_sites_y + yVal;
        int sIdx = site2addr_map[siteId];

        dist_moved[i] = DREAMPLACE_STD_NAMESPACE::abs(pos_x[instId] - site_xy[siteId*2]) + 
            DREAMPLACE_STD_NAMESPACE::abs(pos_y[instId] - site_xy[siteId*2+1]);

        int sdtopId = sIdx*SIG_IDX;
        int sdlutId = sIdx*SLICE_CAPACITY;

        if (site_det_sig_idx[sIdx] == 0)
        {
            sites_with_special_nodes[sIdx] = 1;
            site_det_score[sIdx] = 1000.0;
            site_det_siteId[sIdx] = siteId;

            site_det_sig_idx[sIdx] = 2*SLICE_CAPACITY;
            site_det_sig[sdtopId] = instId;
            site_det_impl_lut[sdlutId] = instId;

            inst_curr_detSite[instId] = siteId;
            inst_curr_bestSite[instId] = siteId;
            inst_curr_bestScoreImprov[instId] = 10000.0;

            inst_next_detSite[instId] = siteId;
            inst_next_bestSite[instId] = siteId;
            inst_next_bestScoreImprov[instId] = 10000.0;
        } 
        //DBG
        else {
            std::cout << "ERROR: Slice site not empty - MLAB " << instId << " not legalized at (" << xVal << ", " << yVal << ")" << std::endl;
        }
        //DBG
    }

    return 0;
}

// initSiteNeighbours
template <typename T>
int initSiteNeighbours(
        const T* pos_x,
        const T* pos_y,
        const T* wlPrecond,
        const T* site_xy,
        const T* site_det_score,
        const int* sorted_node_idx,
        const int* node2fence_region_map,
        const int* site_types,
        const int* spiral_accessor,
        const int* site2addr_map,
        const int* addr2site_map,
        const int* is_mlab_node,
        const int* is_mlab_site,
        const int* sites_with_special_nodes,
        const int* flat_node2precluster_map,
        const int* flat_node2prclstrCount,
        const T nbrDistEnd,
        const T nbrDistBeg,
        const T nbrDistIncr,
        const int lutId,
        const int ffId,
        const int sliceId,
        const int num_nodes,
        const int num_sites_x,
        const int num_sites_y,
        const int num_clb_sites,
        const int spiralBegin,
        const int spiralEnd,
        const int maxList,
        const int numGroups,
        const int SCL_IDX,
        const int SIG_IDX,
        const int SLICE_CAPACITY,
        T* site_curr_scl_score,
        int* site_nbrList,
        int* site_nbrRanges,
        int* site_nbrRanges_idx,
        int* site_nbr,
        int* site_nbr_idx,
        int* site_nbrGroup_idx,
        int* site_det_siteId,
        int* site_det_sig,
        int* site_det_sig_idx,
        int* site_det_impl_lut,
        int* site_curr_scl_siteId,
        int* site_curr_scl_validIdx,
        int* site_curr_scl_idx,
        int* site_curr_scl_sig,
        int* site_curr_scl_sig_idx,
        int* site_curr_scl_impl_lut,
        const int num_threads)
{
    std::vector<std::vector<std::pair<int, T> > > sites_nbrListMap(num_clb_sites);
    std::vector<int> site_nbrList_idx(num_clb_sites, 0);

    //Update sites_nbrListMap_instId and sites_nbrListMap_dist
    for (int i = 0; i < num_nodes; ++i)
    {
        const int instId = sorted_node_idx[i];
        int prIdx = instId*3;
        int preclusterNodeId = flat_node2precluster_map[prIdx];

        //Only consider LUTs & FFs AND first precluster is the same as InstID
        if ((node2fence_region_map[instId] != lutId && node2fence_region_map[instId] != ffId) ||
                preclusterNodeId != instId || is_mlab_node[instId] == 1)
        {
            continue;
        }

        //Centroid Calculation
        //First element in inst precluster is itself
        T cenX = pos_x[preclusterNodeId] * wlPrecond[preclusterNodeId];
        T cenY = pos_y[preclusterNodeId] * wlPrecond[preclusterNodeId];
        T totalWt = wlPrecond[preclusterNodeId];

        if (flat_node2prclstrCount[instId] > 1)
        {
            for (int pcl = 1; pcl < flat_node2prclstrCount[instId]; ++pcl)
            {
                int fdx = flat_node2precluster_map[prIdx + pcl];
                cenX += pos_x[fdx] * wlPrecond[fdx];
                cenY += pos_y[fdx] * wlPrecond[fdx];
                totalWt += wlPrecond[fdx];
            }
        }

        if (totalWt > 0)
        {
            cenX /= totalWt;
            cenY /= totalWt;
        }

        //Employ spiral accessor to update neighbour list
        for (int sIdx = spiralBegin; sIdx < spiralEnd; ++sIdx)
        {
            int saIdx = sIdx*2; //For x,y
            int xVal = cenX + spiral_accessor[saIdx]; 
            int yVal = cenY + spiral_accessor[saIdx + 1]; 

            //Check within bounds
            if (xVal < 0 || xVal >= num_sites_x || yVal < 0 || yVal >= num_sites_y)
            {
                continue;
            }

            int siteMapIdx = xVal * num_sites_y + yVal;
            int siteId = site2addr_map[siteMapIdx];
            int stMpId = siteMapIdx*2;

            //Check site type and Inst type (CLB) matches
            if ((node2fence_region_map[instId] == lutId || node2fence_region_map[instId] == ffId) &&
                 site_types[siteMapIdx] == sliceId && is_mlab_site[siteId] == 0)
            {
                T dist = DREAMPLACE_STD_NAMESPACE::abs(cenX - site_xy[stMpId]) + 
                         DREAMPLACE_STD_NAMESPACE::abs(cenY - site_xy[stMpId+1]);
                if (dist < nbrDistEnd)
                {
                    sites_nbrListMap[siteId].emplace_back(std::make_pair(instId, dist));
                }
            }
        }
    }

    //Update site information based on nbrListMap update
    for(int sIdx = 0; sIdx < num_clb_sites; ++sIdx)
    {
        // Sort neighbors by their distances
        auto &list = sites_nbrListMap[sIdx];
        std::sort(list.begin(), list.end(), [&](const std::pair<int, T> &l, const std::pair<int, T> &r){ return l.second < r.second; });

        int sRIdx = sIdx * (numGroups + 1);
        int sNbrIdx = sIdx*maxList;
        if (!list.empty())
        {
            site_nbrRanges[sRIdx] = 0;

            int grpIdx = 0;

            T maxD = nbrDistBeg;

            for (unsigned il = 0; il < list.size(); ++il)
            {
                site_nbrList[sNbrIdx + site_nbrList_idx[sIdx]] = list[il].first;
                ++site_nbrList_idx[sIdx];

                while (list[il].second >= maxD)
                {
                    site_nbrRanges[++grpIdx + sRIdx] = il;
                    maxD += nbrDistIncr;
                }
            }
            while(++grpIdx <= numGroups)
            {
                site_nbrRanges[sRIdx + grpIdx] = site_nbrList_idx[sIdx];
            }
            site_nbrRanges_idx[sIdx] = grpIdx;
        }
    }

    //runDLInit
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_clb_sites / num_threads / 16), 1);
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for(int sIdx = 0; sIdx < num_clb_sites; ++sIdx)
    {
        int siteId = addr2site_map[sIdx];
        int sRIdx = sIdx * (numGroups + 1);
        int sNbrIdx = sIdx*maxList;

        int numNbrGroups = (site_nbrRanges_idx[sIdx] == 0) ? 0 : site_nbrRanges_idx[sIdx]-1;
        ////Assign site_nbr
        if (numNbrGroups > 0)
        {
            for (int nIdx = site_nbrRanges[sRIdx]; nIdx < site_nbrRanges[sRIdx+1]; ++nIdx)
            {
                site_nbr[sNbrIdx + site_nbr_idx[sIdx]] = site_nbrList[sNbrIdx + nIdx];
                ++site_nbr_idx[sIdx];
            }
            site_nbrGroup_idx[sIdx] = 1;
        }

        int sSCL = sIdx*SCL_IDX;

        site_det_siteId[sIdx] = siteId;
        site_curr_scl_siteId[sSCL] = siteId;
        site_curr_scl_validIdx[sSCL] = 1;
        ++site_curr_scl_idx[sIdx];

        if (sites_with_special_nodes[sIdx] == 1)
        {
            int sdtopId = sIdx*SIG_IDX;
            int sdlutId = sIdx*SLICE_CAPACITY;
            int sclSigId = sSCL*SIG_IDX;
            int scllutIdx = sSCL*SLICE_CAPACITY;
            //Assign site_det to site_curr_scl
            site_curr_scl_sig_idx[sSCL] = site_det_sig_idx[sIdx];
            site_curr_scl_score[sSCL] = site_det_score[sIdx];

            for(int sg = 0; sg < site_det_sig_idx[sIdx]; ++sg)
            {
                site_curr_scl_sig[sclSigId + sg] = site_det_sig[sdtopId + sg];
            }
            for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
            {
                site_curr_scl_impl_lut[scllutIdx + sg] = site_det_impl_lut[sdlutId + sg];
            }
        }
    }
    return 0;
}

//run DL Iteration
template <typename T>
int runDLIteration(
        const T* pos_x,
        const T* pos_y,
        const T* pin_offset_x,
        const T* pin_offset_y,
        const T* net_bbox,
        const T* site_xy,
        const int* net_pinIdArrayX,
        const int* net_pinIdArrayY,
        const int* node2fence_region_map,
        const int* flop_ctrlSets,
        const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map,
        const int* flop2ctrlSetId_map,
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
        const int* sorted_node_map,
        const int* sorted_net_map,
        const int* flat_node2prclstrCount,
        const int* flat_node2precluster_map,
        const int* is_mlab_node,
        const int* is_mlab_site,
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
        const int numGroups,
        const int netShareScoreMaxNetDegree,
        const int wlScoreMaxNetDegree,
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
        const int num_threads,
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
        int* inst_next_bestSite
        )
{
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_clb_sites / num_threads / 16), 1);

#pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for(int sIdx = 0; sIdx < num_clb_sites; ++sIdx)
    {
        if (is_mlab_site[sIdx]) continue;

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

        ////DBG
        //if (site_curr_pq_idx[sIdx] > 0)
        //{
        //    std::cout << "For site: " << siteId << "(" << sIdx << "), there are " << site_curr_pq_idx[sIdx] << " elements in site_curr_pq " << std::endl;
        //    int tsPQ = sPQ + site_curr_pq_top_idx[sIdx];

        //    std::cout << "site curr pq top element has score: " <<  site_curr_pq_score[tsPQ] << std::endl;
        //    std::cout << "site curr pq top element has site: " <<  site_curr_pq_siteId[tsPQ] << std::endl;
        //    std::cout << "site curr pq top element has sig elements: " <<  site_curr_pq_sig_idx[tsPQ] << std::endl;
        //    std::cout << "site curr pq top element sig: ";
        //    for (int sg = 0; sg < site_curr_pq_sig_idx[tsPQ]; ++sg)
        //    {
        //        std::cout << site_curr_pq_sig[topIdx + sg] << " ";
        //    }
        //    std::cout << std::endl;
        //}
        ////DBG

        if (site_curr_pq_idx[sIdx] == 0 || site_curr_stable[sIdx] < minStableIter ||
                !candidate_validity_check(is_mlab_node, SLICE_CAPACITY, topIdx,
                    site_curr_pq_sig_idx[tsPQ], site_curr_pq_siteId[tsPQ],
                    site_curr_pq_sig, inst_curr_detSite))
        {
            commitTopCandidate = 0;
        } else if (site_curr_pq_idx[sIdx] > 0)
        {
            for (int pIdx = 0; pIdx < site_curr_pq_sig_idx[tsPQ]; ++pIdx)
            {
                int pqInst = site_curr_pq_sig[topIdx + pIdx];
                if (inst_curr_detSite[pqInst] != siteId && inst_curr_bestSite[pqInst] != siteId)
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
                    flat_node2pin_start_map, flat_node2pin_map, node2pincount, net2pincount,
                    pin2net_map, pin_typeIds, flat_node2prclstrCount, flat_node2precluster_map,
                    flop2ctrlSetId_map, flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map,
                    site_det_impl_lut, site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce,
                    site_det_sig, site_det_sig_idx, special_nodes, lutTypeInSliceUnit, lut_maxShared,
                    sIdx, sNbrIdx, half_ctrl_mode, SLICE_CAPACITY, HALF_SLICE_CAPACITY, BLE_CAPACITY,
                    NUM_BLE_PER_SLICE, SIG_IDX, CKSR_IN_CLB, CE_IN_CLB, lutId, ffId, site_nbr_idx, site_nbr);

            //Clear pq and make scl only contain the committed candidate
            //int sclCount(0);
            for (int vId = 0; vId < PQ_IDX; ++vId)
            {
                int nPQId = sPQ + vId;
                //if (site_next_pq_validIdx[nPQId] != INVALID)
                //{
                //Clear contents thoroughly
                clear_cand_contents(
                        nPQId, SIG_IDX, SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB,
                        site_next_pq_sig_idx, site_next_pq_sig,
                        site_next_pq_impl_lut, site_next_pq_impl_ff,
                        site_next_pq_impl_cksr, site_next_pq_impl_ce);

                site_next_pq_validIdx[nPQId] = INVALID;
                site_next_pq_siteId[nPQId] = INVALID;
                site_next_pq_score[nPQId] = 0.0;
                site_next_pq_sig_idx[nPQId] = 0;

                //++sclCount;
                //if (sclCount == site_next_pq_idx[sIdx])
                //{
                //    break;
                //}
                //}
            }
            site_next_pq_idx[sIdx] = 0;
            site_next_pq_top_idx[sIdx] = INVALID;
            site_next_stable[sIdx] = 0;

            int sclCount = 0;
            for (int vId = 0; vId < SCL_IDX; ++vId)
            {
                int cSclId = sSCL + vId;
                if (site_curr_scl_validIdx[cSclId] != INVALID)
                {
                    //Clear contents thoroughly
                    clear_cand_contents(
                            cSclId, SIG_IDX, SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB,
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

            //Assign site_det to site_curr_scl
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
                    int topIdx = ssPQ*SIG_IDX;

                    if (site_next_pq_validIdx[ssPQ] != INVALID)
                    {
                        if (!candidate_validity_check(is_mlab_node, SLICE_CAPACITY, topIdx,
                                    site_next_pq_sig_idx[ssPQ], site_next_pq_siteId[ssPQ],
                                    site_next_pq_sig, inst_curr_detSite))
                        {
                            //Clear contents thoroughly
                            clear_cand_contents(
                                    ssPQ, SIG_IDX, SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB,
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

                //Recompute top idx
                site_next_pq_top_idx[sIdx] = INVALID;
                if (site_next_pq_idx[sIdx] > 0)
                {
                    //snCnt = 0;
                    //maxEntries = site_next_pq_idx[sIdx];
                    T maxScore(-1000.0);
                    int maxScoreId(INVALID);
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
                            //++snCnt;
                            //if (snCnt == maxEntries)
                            //{
                            //    break;
                            //}
                        }
                    }
                    site_next_pq_top_idx[sIdx] = maxScoreId;
                }
            }

            //Remove invalid candidates from seed candidate list (scl)
            if (site_curr_scl_idx[sIdx] > 0)
            {
                int sclCount(0), maxEntries(site_curr_scl_idx[sIdx]);
                for (int nIdx = 0; nIdx < SCL_IDX; ++nIdx)
                {
                    int ssPQ = sSCL + nIdx;
                    int topIdx = ssPQ*SIG_IDX;

                    if (site_curr_scl_validIdx[ssPQ] != INVALID)
                    {
                        if(!candidate_validity_check(is_mlab_node, SLICE_CAPACITY, topIdx,
                                    site_curr_scl_sig_idx[ssPQ], site_curr_scl_siteId[ssPQ],
                                    site_curr_scl_sig, inst_curr_detSite))
                        {
                            //Clear contents thoroughly
                            clear_cand_contents(
                                    ssPQ, SIG_IDX, SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB,
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

            //If site.scl becomes empty, add site_det into it as the seed
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

        // (d) addNeighbors(site) - Original implementation without staggering
        ////DBG
        //std::cout << "For site: " << siteId << "(" << sIdx << "), there are " << site_nbr_idx[sIdx] << " site nbrs and nbrGroup_idx: " 
        //          << site_nbrGroup_idx[sIdx] << std::endl;
        ////DBG
        if (site_nbr_idx[sIdx] < minNeighbors && site_nbrGroup_idx[sIdx] < numNbrGroups)
        {
            int nbrRIdx = sIdx*(numGroups+1) + site_nbrGroup_idx[sIdx];
            int beg = site_nbrRanges[nbrRIdx];
            int end = site_nbrRanges[nbrRIdx+1];

            for (int aNIdx = beg; aNIdx < end; ++aNIdx)
            {
                int instId = site_nbrList[sNbrIdx + aNIdx];
                ////DBG
                //std::cout << "For site: " << siteId << "(" << sIdx << "), try to add inst " << instId << " of type " 
                //    << node2fence_region_map[instId] <<  "to site nbrs" << std::endl;
                ////DBG

                if (inst_curr_detSite[instId] == INVALID && 
                        is_inst_in_cand_feasible(node2outpinIdx_map, node2fence_region_map, lut_type,
                            flat_node2pin_start_map, flat_node2pin_map, node2pincount, net2pincount,
                            pin2net_map, pin_typeIds, flat_node2prclstrCount, flat_node2precluster_map,
                            flop2ctrlSetId_map, flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map,
                            site_det_impl_lut, site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce,
                            special_nodes, lutTypeInSliceUnit, lut_maxShared, sIdx, instId, SLICE_CAPACITY,
                            HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE, CKSR_IN_CLB, CE_IN_CLB,
                            lutId, ffId, half_ctrl_mode))
                {
                    ////DBG
                    //std::cout << "For site: " << siteId << "(" << sIdx << "), ADD inst " << instId << " of type " 
                    //    << node2fence_region_map[instId] <<  "to site nbrs" << std::endl;
                    ////DBG
                    site_nbr[sNbrIdx + site_nbr_idx[sIdx]] = instId; 
                    ++site_nbr_idx[sIdx];
                }
            }
            ++site_nbrGroup_idx[sIdx];
        }
        ////DBG
        //std::cout << "After (d) For site: " << siteId << "(" << sIdx << "), there are " << site_nbr_idx[sIdx] << " site nbrs and nbrGroup_idx: " 
        //          << site_nbrGroup_idx[sIdx] << std::endl;
        ////DBG

        // (e) createNewCandidates(site) - Original implementation without restricted candidate search space
        //Generate new candidates by merging site_nbr to site_curr_scl
        const int limit_x = site_curr_scl_idx[sIdx];
        const int limit_y = site_nbr_idx[sIdx];
        const int limit_cands = limit_x*limit_y;
        int limit_count(0);
        int sclCount(0);
        if (limit_cands > 0)
        {
            for (int scsIdx = 0; scsIdx < SCL_IDX; ++scsIdx)
            {
                int siteCurrIdx = sSCL + scsIdx;
                if (site_curr_scl_validIdx[siteCurrIdx] != INVALID)
                {
                    if (limit_count >= limit_cands) break;
                    //
                    for (int snIdx = 0; snIdx < site_nbr_idx[sIdx]; ++snIdx)
                    {
                        ++limit_count;

                        int instId = site_nbr[sNbrIdx + snIdx];
                        int instPcl = instId*3;

                        /////
                        //New candidate = site_curr_scl_validIdx[sSCL + scsIdx]
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

                        for (int sg = 0; sg < site_curr_scl_sig_idx[siteCurrIdx]; ++sg)
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
                        /////

                        if (add_inst_to_sig(flat_node2prclstrCount[instId], flat_node2precluster_map,
                                    instPcl, nwCand_sig, nwCand_sigIdx, SLICE_CAPACITY) && 
                                !check_sig_in_site_next_pq_sig(nwCand_sig, nwCand_sigIdx, sPQ, PQ_IDX,
                                    site_next_pq_validIdx, site_next_pq_sig, site_next_pq_sig_idx, SIG_IDX) && 
                                add_inst_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map, 
                                    flat_node2pin_map, node2pincount, net2pincount, pin2net_map, pin_typeIds,
                                    flat_node2prclstrCount, flat_node2precluster_map, flop2ctrlSetId_map,
                                    node2fence_region_map, flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map,
                                    special_nodes, lutTypeInSliceUnit, lut_maxShared, instId, lutId, ffId,
                                    half_ctrl_mode, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY, HALF_SLICE_CAPACITY,
                                    BLE_CAPACITY, NUM_BLE_PER_SLICE, nwCand_lut, nwCand_ff, nwCand_cksr, nwCand_ce))
                        {
                            compute_candidate_score(pos_x, pos_y, pin_offset_x, pin_offset_y,
                                net_bbox, net_weights, site_xy, net_pinIdArrayX, net_pinIdArrayY,
                                flat_net2pin_start_map, flat_node2pin_start_map, flat_node2pin_map,
                                sorted_net_map, pin2net_map, pin2node_map, net2pincount, lut_type,
                                xWirelenWt, yWirelenWt, extNetCountWt, wirelenImprovWt,
                                netShareScoreMaxNetDegree, wlScoreMaxNetDegree, half_ctrl_mode,
                                nwCand_sig, nwCand_siteId, nwCand_sigIdx, nwCand_score);

                            int nxtId(INVALID);
                            //find least score and replace if current score is greater
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

                                if (site_next_pq_idx[sIdx] == 1 || nwCand_score > site_next_pq_score[sPQ + site_next_pq_top_idx[sIdx]])
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
                    ++sclCount;
                    if (sclCount == site_curr_scl_idx[sIdx])
                    {
                        break;
                    }
                }
            }
        }

        //Remove all candidates in scl that is worse than the worst candidate in PQ
        if (site_next_pq_idx[sIdx] > 0)
        {
            //Find worst candidate in PQ
            T ckscore(site_next_pq_score[sPQ + site_next_pq_top_idx[sIdx]]);

            sclCount = 0;
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
            int maxEntries(site_next_scl_idx[sIdx]);
            for (int ckId = 0; ckId < SCL_IDX; ++ckId)
            {
                int vId = sSCL + ckId;
                if (site_next_scl_validIdx[vId] != INVALID)
                {
                    if (ckscore > site_next_scl_score[vId])
                    {
                        //Clear contents thoroughly
                        clear_cand_contents(
                                vId, SIG_IDX, SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB,
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
            //Check both sig
            site_next_stable[sIdx] = site_curr_stable[sIdx] + 1;
        } else
        {
            site_next_stable[sIdx] = 0;
        }

        // (f) broadcastTopCandidate(site) - Original implementation without updated sequential portion
        if (site_next_pq_idx[sIdx] > 0)
        {
            int topIdx = sPQ + site_next_pq_top_idx[sIdx];
            int topSigId = topIdx*SIG_IDX;

            T scoreImprov = site_next_pq_score[topIdx] - site_det_score[sIdx];
            for (int ssIdx = 0; ssIdx < site_next_pq_sig_idx[topIdx]; ++ssIdx)
            {
                int instId = site_next_pq_sig[topSigId + ssIdx];

                if (inst_curr_detSite[instId] == INVALID && scoreImprov >= inst_next_bestScoreImprov[instId])
                {
                    mtx.lock();
                    if (scoreImprov == inst_next_bestScoreImprov[instId])
                    {
                        if (siteId < inst_next_bestSite[instId])
                        {
                            inst_next_bestSite[instId] = siteId;
                        }
                    }
                    else if (scoreImprov > inst_next_bestScoreImprov[instId])
                    {
                        inst_next_bestSite[instId] = siteId;
                        inst_next_bestScoreImprov[instId] = scoreImprov;
                    }
                    mtx.unlock();
                }
            }
        }
    }
    return 0;
}

//run DL Sync 
template <typename T>
int runDLSynchronize(   
                      const int* node2fence_region_map,
                      const int* addr2site_map,
                      const int num_clb_sites,
                      const int SLICE_CAPACITY,
                      const int CKSR_IN_CLB,
                      const int CE_IN_CLB,
                      const int SCL_IDX,
                      const int PQ_IDX,
                      const int SIG_IDX,
                      const int lutId,
                      const int ffId,
                      const int num_nodes,
                      const int num_threads,
                      int* site_nbrGroup_idx,
                      int* site_nbrRanges_idx,
                      int* site_curr_pq_top_idx,
                      int* site_curr_pq_sig_idx,
                      int* site_curr_pq_sig,
                      int* site_curr_pq_idx,
                      int* site_curr_pq_validIdx,
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
                      int* inst_curr_detSite,
                      int* inst_curr_bestSite,
                      T* inst_curr_bestScoreImprov,
                      int* inst_next_detSite,
                      int* inst_next_bestSite,
                      T* inst_next_bestScoreImprov,
                      int* activeStatus,
                      int* illegalStatus
                      )
{
    //int numSites = num_sites_x * num_sites_y;
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_clb_sites / num_threads / 16), 1);

    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for(int sIdx = 0; sIdx < num_clb_sites; ++sIdx)
    {
        int numNbrGroups = (site_nbrRanges_idx[sIdx] == 0) ? 0 : site_nbrRanges_idx[sIdx]-1;
        int sPQ = sIdx*SCL_IDX;

        site_curr_stable[sIdx] = site_next_stable[sIdx];

        int curr_scl_size = site_curr_scl_idx[sIdx];
        site_curr_scl_idx[sIdx] = 0;

        int sclCount(0);
        //Include valid entries of site_next_scl to site_curr_scl
        if (site_next_scl_idx[sIdx] > 0)
        {
            for (int id = 0; id < SCL_IDX; ++id)
            {
                int vIdx = sPQ+id;
                if (site_next_scl_validIdx[vIdx] != INVALID)
                {
                    int currId(sPQ+site_curr_scl_idx[sIdx]);

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
                        site_curr_scl_impl_cksr[currCKId + sg] = site_next_scl_impl_cksr[nxtCKId + sg];
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

        //Invalidate the rest in site_curr_scl
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
                    site_curr_scl_score[vIdx] = 0.0;
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
        //Include valid entries of site_next_pq to site_curr_pq
        if (site_next_pq_idx[sIdx] > 0)
        {
            for (int id = 0; id < PQ_IDX; ++id)
            {
                int vIdx = sPQ+id;
                if (site_next_pq_validIdx[vIdx] != INVALID)
                {
                    int currId(sPQ+site_curr_pq_idx[sIdx]);

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

        //Invalidate the rest in site_curr_pq
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
                    site_curr_pq_score[vIdx] = 0.0;
                    ++sclCount;
                    if (sclCount == curr_pq_size)
                    {
                        break;
                    }
                }
            }
        }

        //clear site_next_scl
        sPQ = sIdx*SCL_IDX;
        //sclCount = 0;
        for (int ckId = 0; ckId < SCL_IDX; ++ckId)
        {
            int vIdx = sPQ+ckId;
            //if (site_next_scl_validIdx[vIdx] != INVALID)
            //{
            //Clear contents thoroughly
            clear_cand_contents(
                    vIdx, SIG_IDX, SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB,
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

        activeStatus[addr2site_map[sIdx]] = (site_curr_pq_idx[sIdx] > 0 || site_curr_scl_idx[sIdx] > 0 ||
                site_nbrGroup_idx[sIdx] < numNbrGroups) ? 1 : 0;
    }

    chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nodes / num_threads / 16), 1);
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for(int nIdx = 0; nIdx < num_nodes; ++nIdx)
    {
        if ((node2fence_region_map[nIdx] == lutId || node2fence_region_map[nIdx] == ffId) && inst_curr_detSite[nIdx] == INVALID) //Only LUT/FF
        {
            //inst.curr = inst.next
            inst_curr_detSite[nIdx] = inst_next_detSite[nIdx];
            inst_curr_bestSite[nIdx] = inst_next_bestSite[nIdx];
            inst_curr_bestScoreImprov[nIdx] = inst_next_bestScoreImprov[nIdx];

            inst_next_bestSite[nIdx] = INVALID;
            inst_next_bestScoreImprov[nIdx] = -10000.0;

            illegalStatus[nIdx] = (inst_curr_detSite[nIdx] == INVALID) ? 1 : 0;
        }
    }
    return 0;
}


//run ripup and greedy legalization
template <typename T>
int ripUp_Greedy_LG(
        const T* pos_x,
        const T* pos_y,
        const T* pin_offset_x,
        const T* pin_offset_y,
        const T* net_weights,
        const T* net_bbox,
        const T* inst_areas,
        const T* wlPrecond,
        const T* site_xy,
        const int* net_pinIdArrayX,
        const int* net_pinIdArrayY,
        const int* spiral_accessor,
        const int* node2fence_region_map,
        const int* lut_type,
        const int* site_types,
        const int* node2outpinIdx_map,
        const int* node2pincount,
        const int* net2pincount,
        const int* pin2net_map,
        const int* pin2node_map,
        const int* pin_typeIds,
        const int* flop2ctrlSetId_map,
        const int* flop_ctrlSets,
        const int* extended_ctrlSets,
        const int* ext_ctrlSet_start_map,
        const int* flat_node2pin_start_map,
        const int* flat_node2pin_map,
        const int* flat_net2pin_start_map,
        int* flat_node2prclstrCount,
        int* flat_node2precluster_map,
        const int* sorted_node_map,
        const int* sorted_node_idx,
        const int* sorted_net_map,
        const int* addr2site_map,
        const int* site2addr_map,
        const int* sites_with_special_nodes,
        const int* special_nodes,
        const T nbrDistEnd,
        const T xWirelenWt,
        const T yWirelenWt,
        const T extNetCountWt,
        const T wirelenImprovWt,
        const int lutTypeInSliceUnit,
        const int lut_maxShared,
        const int num_nodes,
        const int num_sites_x,
        const int num_sites_y,
        const int num_clb_sites,
        const int spiralBegin,
        const int spiralEnd,
        const int half_ctrl_mode,
        const int CKSR_IN_CLB,
        const int CE_IN_CLB,
        const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY,
        const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE,
        const int netShareScoreMaxNetDegree,
        const int wlScoreMaxNetDegree,
        const int ripupExpansion,
        const int greedyExpansion,
        const int SIG_IDX,
        const int lutId,
        const int ffId,
        const int sliceId,
        int* inst_curr_detSite,
        int* site_det_sig_idx,
        int* site_det_sig,
        int* site_det_impl_lut,
        int* site_det_impl_ff,
        int* site_det_impl_cksr,
        int* site_det_impl_ce,
        int* site_det_siteId,
        T* site_det_score
        )
{
    ////DBG
    //std::cout << "RipUP & Greedy LG for " << num_nodes << " nodes" << std::endl;
    //char collect_info = 0;
    ////DBG

    int maxRad = DREAMPLACE_STD_NAMESPACE::max(num_sites_x, num_sites_y);
    for (int i = 0; i < num_nodes; ++i)
    {
        ////DBG
        //std::chrono::steady_clock::time_point begin = std::chrono::steady_clock::now();
        ////DBG

        //////DBG
        //std::string dbgMsg = "";
        //////DBG

        const int instId = sorted_node_idx[i]; //Remaining insts sorted based on decreasing area
        if (inst_curr_detSite[instId] != INVALID) continue;
        int instPcl = instId*3;

        //RipUpCandidates
        std::vector<RipUpCand<T> > ripUpCandidates;

        int xLo = DREAMPLACE_STD_NAMESPACE::max(pos_x[instId] - nbrDistEnd, T(0));
        int yLo = DREAMPLACE_STD_NAMESPACE::max(pos_y[instId] - nbrDistEnd, T(0));
        int xHi = DREAMPLACE_STD_NAMESPACE::min(pos_x[instId] + nbrDistEnd, T(num_sites_x-1));
        int yHi = DREAMPLACE_STD_NAMESPACE::min(pos_y[instId] + nbrDistEnd, T(num_sites_y-1));

        for (int x = xLo; x <= xHi; ++x)
        {
            for (int y = yLo; y <= yHi; ++y)
            {
                int siteId = x*num_sites_y + y;
                int sIdx = site2addr_map[siteId];
                if ((node2fence_region_map[instId] == lutId ||
                            node2fence_region_map[instId] == ffId) &&
                        site_types[siteId] == sliceId && sites_with_special_nodes[sIdx] != 1)
                {
                    int slocId = siteId*2;
                    T dist = DREAMPLACE_STD_NAMESPACE::abs(pos_x[instId] - site_xy[slocId]) + DREAMPLACE_STD_NAMESPACE::abs(pos_y[instId] - site_xy[slocId+1]);
                    if (dist < nbrDistEnd)
                    {
                        RipUpCand<T> rpCand;
                        rpCand.reset();

                        rpCand.siteId = siteId;
                        rpCand.cand.score = site_det_score[sIdx];
                        rpCand.cand.siteId = site_det_siteId[sIdx];

                        rpCand.cand.sigIdx = site_det_sig_idx[sIdx];

                        ///
                        int sdSGId = sIdx*SIG_IDX;
                        int sdLutId = sIdx*SLICE_CAPACITY;
                        int sdCKId = sIdx*CKSR_IN_CLB;
                        int sdCEId = sIdx*CE_IN_CLB;

                        for (int sg = 0; sg < site_det_sig_idx[sIdx]; ++sg)
                        {
                            rpCand.cand.sig[sg] = site_det_sig[sdSGId + sg];
                        }
                        for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                        {
                            rpCand.cand.impl_lut[sg] = site_det_impl_lut[sdLutId + sg];
                            rpCand.cand.impl_ff[sg] = site_det_impl_ff[sdLutId + sg];
                        }
                        for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                        {
                            rpCand.cand.impl_cksr[sg] = site_det_impl_cksr[sdCKId + sg];
                        }
                        for (int sg = 0; sg < CE_IN_CLB; ++sg)
                        {
                            rpCand.cand.impl_ce[sg] = site_det_impl_ce[sdCEId + sg];
                        }
                        ///

                        rpCand.legal = add_inst_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map,
                                flat_node2pin_map, node2pincount, net2pincount, pin2net_map, pin_typeIds,
                                flat_node2prclstrCount, flat_node2precluster_map, flop2ctrlSetId_map,
                                node2fence_region_map, flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map,
                                special_nodes, lutTypeInSliceUnit, lut_maxShared, instId, lutId, ffId,
                                half_ctrl_mode, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY, HALF_SLICE_CAPACITY,
                                BLE_CAPACITY, NUM_BLE_PER_SLICE, rpCand.cand.impl_lut, rpCand.cand.impl_ff,
                                rpCand.cand.impl_cksr, rpCand.cand.impl_ce);

                        if (rpCand.legal)
                        {
                            ///
                            bool addInstToSig = add_inst_to_sig(flat_node2prclstrCount[instId],
                                    flat_node2precluster_map, instPcl,
                                    rpCand.cand.sig, rpCand.cand.sigIdx, SLICE_CAPACITY);
                            //DBG
                            if (!addInstToSig)
                            {
                                std::cout << "ERROR: Unable to add inst: " << instId << " to sig" << std::endl;
                            }
                            //DBG

                            compute_candidate_score(pos_x, pos_y, pin_offset_x, pin_offset_y,
                                net_bbox, net_weights, site_xy, net_pinIdArrayX, net_pinIdArrayY,
                                flat_net2pin_start_map, flat_node2pin_start_map, flat_node2pin_map,
                                sorted_net_map, pin2net_map, pin2node_map, net2pincount, lut_type,
                                xWirelenWt, yWirelenWt, extNetCountWt, wirelenImprovWt,
                                netShareScoreMaxNetDegree, wlScoreMaxNetDegree, half_ctrl_mode,
                                rpCand.cand.sig, rpCand.cand.siteId, rpCand.cand.sigIdx,
                                rpCand.cand.score);

                            rpCand.score = rpCand.cand.score - site_det_score[sIdx];

                        } else
                        {
                            T area = inst_areas[site_det_sig[sdSGId]];
                            for (int sInst = 1; sInst < site_det_sig_idx[sIdx]; ++sInst)
                            {
                                area += inst_areas[site_det_sig[sdSGId + sInst]];
                            }
                            T wirelenImprov(0.0);
                            int pStart = flat_node2pin_start_map[instId]; 
                            int pEnd =  flat_node2pin_start_map[instId+1];
                            for (int pId = pStart; pId < pEnd; ++pId)
                            {
                                int pinId = flat_node2pin_map[pId];
                                int netId = pin2net_map[pinId];
                                if (net2pincount[netId] <= wlScoreMaxNetDegree)
                                {
                                    compute_wirelength_improv(pos_x, pos_y, net_bbox, pin_offset_x, pin_offset_y, net_weights, net_pinIdArrayX, net_pinIdArrayY, flat_net2pin_start_map, pin2node_map, net2pincount, site_xy, xWirelenWt, yWirelenWt, netId, siteId, std::vector<int>{pinId}, wirelenImprov);
                                }
                            }
                            rpCand.score = wirelenImprovWt * wirelenImprov - site_det_score[sIdx] - area;
                        }
                        ripUpCandidates.emplace_back(rpCand);
                    }
                }
            }
        }

        //Sort ripup candidate indices based on legal and score
        if (ripUpCandidates.size() > 1)
        {
            std::sort(ripUpCandidates.begin(), ripUpCandidates.end());
        }

        //////DBG
        //if (collect_info)
        //{
        //    dbgMsg += "Created " + std::to_string(ripUpCandidates.size()) + " RipUPCandidates for Inst: ";
        //    dbgMsg += std::to_string(instId) + " of type: " + std::to_string(node2fence_region_map[instId]) + "\n";
        //    if (node2fence_region_map[instId] == ffId)
        //    {
        //        int clInstCKSR = flop2ctrlSetId_map[instId]*3 + 1;
        //        int clInstCE = flop2ctrlSetId_map[instId]*3 + 2;
        //        dbgMsg += "FF Node " + std::to_string(instId) + " has clk: " + std::to_string(flop_ctrlSets[clInstCKSR]);
        //        dbgMsg += " and ce: " + std::to_string(flop_ctrlSets[clInstCE]) + "\n";
        //    } else
        //    {
        //        dbgMsg += "LUT Node " + std::to_string(instId) + " is of type: " + std::to_string(lut_type[instId]) + "\n";
        //    }
        //}
        //////DBG

        int ripupLegalizeInst(INVALID);
        int greedyLegalizeInst(INVALID);

        for (const auto &ripUpCd : ripUpCandidates)
        {
            int stId = ripUpCd.siteId;
            int stAdId = site2addr_map[stId];

            int sdSGId = stAdId*SIG_IDX;
            int sdLutId = stAdId*SLICE_CAPACITY;
            int sdCKId = stAdId*CKSR_IN_CLB;
            int sdCEId = stAdId*CE_IN_CLB;

            if (ripUpCd.legal)
            {
                site_det_score[stAdId] = ripUpCd.cand.score;
                site_det_siteId[stAdId] = ripUpCd.cand.siteId;
                site_det_sig_idx[stAdId] = ripUpCd.cand.sigIdx;

                for (auto sg = 0; sg < ripUpCd.cand.sigIdx; ++sg)
                {
                    site_det_sig[sdSGId + sg] = ripUpCd.cand.sig[sg];
                }
                for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                {
                    site_det_impl_lut[sdLutId + sg] = ripUpCd.cand.impl_lut[sg];
                    site_det_impl_ff[sdLutId + sg] = ripUpCd.cand.impl_ff[sg];
                }
                for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                {
                    site_det_impl_cksr[sdCKId + sg] = ripUpCd.cand.impl_cksr[sg];
                }
                for (int sg = 0; sg < CE_IN_CLB; ++sg)
                {
                    site_det_impl_ce[sdCEId + sg] = ripUpCd.cand.impl_ce[sg];
                }
                ///
                for (int idx = 0; idx < flat_node2prclstrCount[instId]; ++idx)
                {
                    int clInstId = flat_node2precluster_map[instPcl + idx];
                    inst_curr_detSite[clInstId] = ripUpCd.siteId;
                }

                ripupLegalizeInst = 1;
                //////DBG
                //if (collect_info)
                //{
                //    dbgMsg += "Found legal RipUPCandidate for Inst: " + std::to_string(instId) + " at site: " + std::to_string(ripUpCd.siteId) +"\n";
                //}
                //////DBG
            } else
            {
                //////DBG
                //if (collect_info)
                //{
                //    dbgMsg += "RipUP Site " + std::to_string(site_det_siteId[stAdId]) + " for Inst: " + std::to_string(instId) + "\n";
                //}
                //////DBG
                int ripupSiteLegalizeInst(INVALID);

                std::vector<Candidate<T> > dets;
                dets.reserve(site_det_sig_idx[stAdId]);

                Candidate<T> tCand;
                tCand.reset();
                tCand.score = site_det_score[stAdId];
                tCand.siteId = site_det_siteId[stAdId];
                tCand.sigIdx = site_det_sig_idx[stAdId];

                for(int sg = 0; sg < tCand.sigIdx; ++sg)
                {
                    tCand.sig[sg] = site_det_sig[sdSGId + sg];
                }
                for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                {
                    tCand.impl_lut[sg] = site_det_impl_lut[sdLutId+ sg];
                    tCand.impl_ff[sg] = site_det_impl_ff[sdLutId+ sg];
                }
                for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                {
                    tCand.impl_cksr[sg] = site_det_impl_cksr[sdCKId+ sg];
                }
                for(int sg = 0; sg < CE_IN_CLB; ++sg)
                {
                    tCand.impl_ce[sg] = site_det_impl_ce[sdCEId+ sg];
                }
                dets.emplace_back(tCand);
                tCand.reset();

                //Rip Up site
                for(int sg = 0; sg < site_det_sig_idx[stAdId]; ++sg)
                {
                    inst_curr_detSite[site_det_sig[sdSGId + sg]] = INVALID;
                }

                //Clear contents of site_det_sig
                clear_cand_contents(stAdId, SIG_IDX, SLICE_CAPACITY, CKSR_IN_CLB,
                        CE_IN_CLB, site_det_sig_idx, site_det_sig, site_det_impl_lut,
                        site_det_impl_ff, site_det_impl_cksr, site_det_impl_ce);

                site_det_sig_idx[stAdId] = flat_node2prclstrCount[instId];
                tCand.sigIdx = flat_node2prclstrCount[instId];

                for (int idx = 0; idx < flat_node2prclstrCount[instId]; ++idx)
                {
                    int clInstId = flat_node2precluster_map[instPcl + idx];
                    site_det_sig[sdSGId + idx] = clInstId;
                    tCand.sig[idx] = clInstId;
                }
                ///

                if (add_inst_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map,
                            flat_node2pin_map, node2pincount, net2pincount, pin2net_map, pin_typeIds,
                            flat_node2prclstrCount, flat_node2precluster_map, flop2ctrlSetId_map,
                            node2fence_region_map, flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map,
                            special_nodes, lutTypeInSliceUnit, lut_maxShared, instId, lutId, ffId,
                            half_ctrl_mode, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY, HALF_SLICE_CAPACITY,
                            BLE_CAPACITY, NUM_BLE_PER_SLICE, tCand.impl_lut, tCand.impl_ff,
                            tCand.impl_cksr, tCand.impl_ce))
                {
                    ///
                    site_det_sig_idx[stAdId] = tCand.sigIdx;

                    for (int sg = 0; sg < tCand.sigIdx; ++sg)
                    {
                        site_det_sig[sdSGId + sg] = tCand.sig[sg];
                    }
                    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                    {
                        site_det_impl_lut[sdLutId+ sg] = tCand.impl_lut[sg];
                        site_det_impl_ff[sdLutId+ sg] = tCand.impl_ff[sg];
                    }
                    for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                    {
                        site_det_impl_cksr[sdCKId+ sg] = tCand.impl_cksr[sg];
                    }
                    for (int sg = 0; sg < CE_IN_CLB; ++sg)
                    {
                        site_det_impl_ce[sdCEId+ sg] = tCand.impl_ce[sg];
                    }
                    ///
                } else
                {
                    //Should not reach here
                    std::cout << "ERROR: Could not add " << instId << " (inst: " << instId << ") of type " << node2fence_region_map[instId] << " to site: " << stId << std::endl;
                }

                compute_candidate_score(pos_x, pos_y, pin_offset_x, pin_offset_y,
                    net_bbox, net_weights, site_xy, net_pinIdArrayX, net_pinIdArrayY,
                    flat_net2pin_start_map, flat_node2pin_start_map, flat_node2pin_map,
                    sorted_net_map, pin2net_map, pin2node_map, net2pincount, lut_type,
                    xWirelenWt, yWirelenWt, extNetCountWt, wirelenImprovWt,
                    netShareScoreMaxNetDegree, wlScoreMaxNetDegree, half_ctrl_mode,
                    tCand.sig, stId, tCand.sigIdx, site_det_score[stAdId]);

                for (int idx = 0; idx < flat_node2prclstrCount[instId]; ++idx)
                {
                    int clInst = flat_node2precluster_map[instPcl + idx];
                    inst_curr_detSite[clInst] = stId;
                }

                int sig[SIG_MAX_CAP];
                int tmp_sigIdx = dets[0].sigIdx;
                for (int sg = 0; sg < dets[0].sigIdx; ++sg)
                {
                    sig[sg] = dets[0].sig[sg];
                }

                for (int rIdx = 0; rIdx < tmp_sigIdx; ++rIdx)
                {
                    int ruInst = sig[rIdx];
                    if (inst_curr_detSite[ruInst] != INVALID)
                    {
                        continue;
                    }
                    int beg = spiralBegin;
                    int r = DREAMPLACE_STD_NAMESPACE::ceil(nbrDistEnd + 1.0);
                    int end = r ? 2 * (r + 1) * r + 1 : 1;

                    int ruInstPcl = flat_node2precluster_map[ruInst*3];
                    T cenX(pos_x[ruInstPcl]), cenY(pos_y[ruInstPcl]);

                    if (flat_node2prclstrCount[ruInst] > 1)
                    {
                        cenX *= wlPrecond[ruInstPcl];
                        cenY *= wlPrecond[ruInstPcl];
                        T totalWt = wlPrecond[ruInstPcl];

                        for (int idx = 1; idx < flat_node2prclstrCount[ruInst]; ++idx)
                        {
                            int clInst = flat_node2precluster_map[ruInst*3 + idx];
                            cenX += pos_x[clInst] * wlPrecond[clInst];
                            cenY += pos_y[clInst] * wlPrecond[clInst];
                            totalWt += wlPrecond[clInst];
                        }
                        if (totalWt > 0)
                        {
                            cenX /= totalWt;
                            cenY /= totalWt;
                        }
                    }

                    //BestCandidate
                    Candidate<T> bestCand;
                    bestCand.reset();
                    T bestScoreImprov(-10000.0);

                    for (int spId = beg; spId < end; ++spId)
                    {
                        int slocIdx = spId*2;
                        int xVal = cenX + spiral_accessor[slocIdx]; 
                        int yVal = cenY + spiral_accessor[slocIdx + 1]; 

                        int siteMapId = xVal * num_sites_y + yVal;

                        //Check within bounds
                        if (xVal < 0 || xVal >= num_sites_x || yVal < 0 || yVal >= num_sites_y)
                        {
                            continue;
                        }
                        if (site_types[siteMapId] == sliceId &&
                                (node2fence_region_map[ruInst] == lutId || 
                                 node2fence_region_map[ruInst] == ffId))
                        {
                            int siteMapAIdx = site2addr_map[siteMapId];

                            Candidate<T> cand;
                            cand.reset();
                            cand.score = site_det_score[siteMapAIdx];
                            cand.siteId = site_det_siteId[siteMapAIdx];
                            cand.sigIdx = site_det_sig_idx[siteMapAIdx];

                            //array instantiation
                            int sdId(siteMapAIdx*SIG_IDX), sdlutId(siteMapAIdx*SLICE_CAPACITY);
                            int sdckId(siteMapAIdx*CKSR_IN_CLB), sdceId(siteMapAIdx*CE_IN_CLB);

                            for(int sg = 0; sg < cand.sigIdx; ++sg)
                            {
                                cand.sig[sg] = site_det_sig[sdId + sg];
                            }
                            for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                            {
                                cand.impl_lut[sg] = site_det_impl_lut[sdlutId + sg];
                                cand.impl_ff[sg] = site_det_impl_ff[sdlutId + sg];
                            }
                            for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                            {
                                cand.impl_cksr[sg] = site_det_impl_cksr[sdckId + sg];
                            }
                            for(int sg = 0; sg < CE_IN_CLB; ++sg)
                            {
                                cand.impl_ce[sg] = site_det_impl_ce[sdceId + sg];
                            }
                            /////

                            if (add_inst_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map,
                                        flat_node2pin_map, node2pincount, net2pincount, pin2net_map, pin_typeIds,
                                        flat_node2prclstrCount, flat_node2precluster_map, flop2ctrlSetId_map,
                                        node2fence_region_map, flop_ctrlSets, extended_ctrlSets, ext_ctrlSet_start_map,
                                        special_nodes, lutTypeInSliceUnit, lut_maxShared, ruInst, lutId, ffId,
                                        half_ctrl_mode, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY, HALF_SLICE_CAPACITY,
                                        BLE_CAPACITY, NUM_BLE_PER_SLICE, cand.impl_lut, cand.impl_ff, cand.impl_cksr,
                                        cand.impl_ce) && 
                                    add_inst_to_sig(flat_node2prclstrCount[ruInst], flat_node2precluster_map,
                                        ruInst*3, cand.sig, cand.sigIdx, SLICE_CAPACITY))
                            {
                                // Adding the instance to the site is legal
                                // If this is the first legal position found, set the expansion search radius
                                if (bestScoreImprov == -10000.0)
                                {
                                    int r = DREAMPLACE_STD_NAMESPACE::abs(spiral_accessor[slocIdx]) + DREAMPLACE_STD_NAMESPACE::abs(spiral_accessor[slocIdx+ 1]); 
                                    r += ripupExpansion;

                                    int maxRad = DREAMPLACE_STD_NAMESPACE::max(num_sites_x, num_sites_y);
                                    int nwR = DREAMPLACE_STD_NAMESPACE::min(maxRad, r);
                                    end = nwR ? 2 * (nwR + 1) * nwR + 1 : 1;
                                }
                                compute_candidate_score(pos_x, pos_y, pin_offset_x, pin_offset_y,
                                    net_bbox, net_weights, site_xy, net_pinIdArrayX, net_pinIdArrayY,
                                    flat_net2pin_start_map, flat_node2pin_start_map, flat_node2pin_map,
                                    sorted_net_map, pin2net_map, pin2node_map, net2pincount, lut_type,
                                    xWirelenWt, yWirelenWt, extNetCountWt, wirelenImprovWt,
                                    netShareScoreMaxNetDegree, wlScoreMaxNetDegree, half_ctrl_mode,
                                    cand.sig, cand.siteId, cand.sigIdx, cand.score);

                                T scoreImprov = cand.score - site_det_score[siteMapAIdx];
                                if (scoreImprov > bestScoreImprov)
                                {
                                    bestCand = cand;
                                    bestScoreImprov = scoreImprov;
                                }
                            } 
                        } 

                    }
                    if (bestCand.siteId == INVALID)
                    {
                        // Cannot find a legal position for this rip-up instance, so moving the instance to the site is illegal
                        //
                        // Revert all affected sites' clusters
                        for (auto rit = dets.rbegin(); rit != dets.rend(); ++rit)
                        {
                            int sId = rit->siteId;
                            int sAId = site2addr_map[sId];
                            int sdId(sAId*SIG_IDX), sdlutId(sAId*SLICE_CAPACITY);
                            int sdckId(sAId*CKSR_IN_CLB), sdceId(sAId*CE_IN_CLB);

                            site_det_score[sAId] = rit->score;
                            site_det_siteId[sAId] = sId;
                            site_det_sig_idx[sAId] = rit->sigIdx;

                            for(int sg = 0; sg < site_det_sig_idx[sAId]; ++sg)
                            {
                                site_det_sig[sdId + sg] = rit->sig[sg];
                            }
                            for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                            {
                                site_det_impl_lut[sdlutId + sg] = rit->impl_lut[sg];
                                site_det_impl_ff[sdlutId + sg] = rit->impl_ff[sg];
                            }
                            for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                            {
                                site_det_impl_cksr[sdckId + sg] = rit->impl_cksr[sg];
                            }
                            for(int sg = 0; sg < CE_IN_CLB; ++sg)
                            {
                                site_det_impl_ce[sdceId + sg] = rit->impl_ce[sg];
                            }
                        }
                        // Move all ripped instances back to their original sites
                        int sdId(stAdId*SIG_IDX);
                        for (int sg = 0; sg < site_det_sig_idx[stAdId]; ++sg)
                        {
                            int sdInst = site_det_sig[sdId + sg];
                            inst_curr_detSite[sdInst] = stId;
                        }
                        // Set the instance as illegal
                        for (int idx = 0; idx < flat_node2prclstrCount[instId]; ++idx)
                        {
                            int prclInst = flat_node2precluster_map[instPcl + idx];
                            inst_curr_detSite[prclInst] = INVALID;
                        }

                        ripupSiteLegalizeInst = 0;
                        break;
                    } else
                    {
                        int sbId = bestCand.siteId;
                        int sbAId = site2addr_map[sbId];

                        Candidate<T> tCand;
                        tCand.reset();
                        ///
                        tCand.score = site_det_score[sbAId];
                        tCand.siteId = site_det_siteId[sbAId];
                        tCand.sigIdx = site_det_sig_idx[sbAId];

                        int sbSGId = sbAId*SIG_IDX;
                        int sbLutId = sbAId*SLICE_CAPACITY;
                        int sbCKId = sbAId*CKSR_IN_CLB;
                        int sbCEId = sbAId*CE_IN_CLB;

                        ///
                        for(int sg = 0; sg < tCand.sigIdx; ++sg)
                        {
                            tCand.sig[sg] = site_det_sig[sbSGId + sg];
                        }
                        for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                        {
                            tCand.impl_lut[sg] = site_det_impl_lut[sbLutId+ sg];
                            tCand.impl_ff[sg] = site_det_impl_ff[sbLutId+ sg];
                        }
                        for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                        {
                            tCand.impl_cksr[sg] = site_det_impl_cksr[sbCKId+ sg];
                        }
                        for(int sg = 0; sg < CE_IN_CLB; ++sg)
                        {
                            tCand.impl_ce[sg] = site_det_impl_ce[sbCEId+ sg];
                        }
                        dets.emplace_back(tCand);

                        //Move ripped instances to this site
                        site_det_score[sbAId] = bestCand.score;
                        site_det_siteId[sbAId] = bestCand.siteId;
                        site_det_sig_idx[sbAId] = bestCand.sigIdx;

                        for(auto sg = 0; sg < bestCand.sigIdx; ++sg)
                        {
                            site_det_sig[sbSGId + sg] = bestCand.sig[sg];
                        }
                        for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                        {
                            site_det_impl_lut[sbLutId+ sg] = bestCand.impl_lut[sg];
                            site_det_impl_ff[sbLutId+ sg] = bestCand.impl_ff[sg];
                        }
                        for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                        {
                            site_det_impl_cksr[sbCKId+ sg] = bestCand.impl_cksr[sg];
                        }
                        for(int sg = 0; sg < CE_IN_CLB; ++sg)
                        {
                            site_det_impl_ce[sbCEId+ sg] = bestCand.impl_ce[sg];
                        }
                        ///
                        for (int idx = 0; idx < flat_node2prclstrCount[ruInst]; ++idx)
                        {
                            int clInst = flat_node2precluster_map[ruInst*3 + idx];
                            inst_curr_detSite[clInst] = sbId;
                        }
                    }
                }
                //Ensure instance is legalized to a site for ripup LG to be successful
                if (ripupSiteLegalizeInst == INVALID && inst_curr_detSite[instId] != INVALID)
                {
                    ripupLegalizeInst = 1;
                }
            }
            if (ripupLegalizeInst == 1) break;
        }

        //Greedy Legalization if RipUP LG failed
        if (ripupLegalizeInst != 1)
        {
            //////DBG
            //if (collect_info)
            //{
            //    dbgMsg += "Starting greedy LG for Inst: " + std::to_string(instId) + " with spiralBegin: ";
            //    dbgMsg += std::to_string(spiralBegin) + " and end: " + std::to_string(spiralEnd) + "\n";
            //}
            //////DBG
            inst_curr_detSite[instId] = INVALID;

            int beg(spiralBegin), end(spiralEnd);

            T cenX(pos_x[flat_node2precluster_map[instPcl]] * wlPrecond[flat_node2precluster_map[instPcl]]);
            T cenY(pos_y[flat_node2precluster_map[instPcl]] * wlPrecond[flat_node2precluster_map[instPcl]]);
            T totalWt(wlPrecond[flat_node2precluster_map[instPcl]]);

            for (int cl = 1; cl < flat_node2prclstrCount[instId]; ++cl)
            {
                int pclInst = flat_node2precluster_map[instPcl + cl];
                cenX += pos_x[pclInst] * wlPrecond[pclInst];
                cenY += pos_y[pclInst] * wlPrecond[pclInst];
                totalWt += wlPrecond[pclInst];
            }

            if (totalWt > 0)
            {
                cenX /= totalWt;
                cenY /= totalWt;
            }

            //////DBG
            //if (collect_info)
            //{
            //    dbgMsg += "Greedy LG: Centroid of Inst: " + std::to_string(instId) + " = (" + std::to_string(cenX);
            //    dbgMsg += ", " + std::to_string(cenY) + ")" + "\n";
            //}
            //////DBG

            //BestCandidate
            Candidate<T> bestCand;
            bestCand.reset();
            T bestScoreImprov(-10000.0);

            for (int sIdx = beg; sIdx < end; ++sIdx)
            {
                //////DBG
                //if (collect_info)
                //{
                //    dbgMsg += "Consider " + std::to_string(sIdx) + " within [" + std::to_string(beg) + ", " + std::to_string(end);
                //    dbgMsg += ") \n";
                //}
                //////DBG

                int saIdx = sIdx*2;
                int xVal = cenX + spiral_accessor[saIdx]; 
                int yVal = cenY + spiral_accessor[saIdx + 1]; 
                int siteMapIdx = xVal * num_sites_y + yVal;
                int siteMapAIdx = site2addr_map[siteMapIdx];

                //Check within bounds
                if (xVal < 0 || xVal >= num_sites_x || yVal < 0 || yVal >= num_sites_y)
                {
                    continue;
                }

                if (site_types[siteMapIdx] == sliceId && (node2fence_region_map[instId] == lutId ||
                            node2fence_region_map[instId] == ffId) && site_det_sig_idx[siteMapAIdx] < 2*SLICE_CAPACITY)
                { 
                    //////DBG
                    //if (collect_info)
                    //{
                    //    dbgMsg += std::to_string(sIdx) + "- Greedy LG Inst: " + std::to_string(instId);
                    //    dbgMsg += " consider site at (" + std::to_string(xVal) + ", " + std::to_string(yVal) + ") ";
                    //    dbgMsg += std::to_string(siteMapIdx) + "\n";
                    //}
                    //////DBG

                    ////DBG
                    //std::cout << "Greedy LG: Inst: " << instId << " site addr map: " << siteMapAIdx << std::endl;
                    ////DBG
                    Candidate<T> cand;
                    cand.reset();
                    cand.score = site_det_score[siteMapAIdx];
                    cand.siteId = site_det_siteId[siteMapAIdx];
                    cand.sigIdx = site_det_sig_idx[siteMapAIdx];

                    int sdId(siteMapAIdx*SIG_IDX), sdlutId(siteMapAIdx*SLICE_CAPACITY);
                    int sdckId(siteMapAIdx*CKSR_IN_CLB), sdceId(siteMapAIdx*CE_IN_CLB);

                    //////DBG
                    //if (collect_info)
                    //{
                    //    dbgMsg += "Greedy LG: Inst: " + std::to_string(instId) + " site det sig element count: " + std::to_string(site_det_sig_idx[siteMapAIdx]) + "\n";
                    //    dbgMsg += "site det sig contains: "; 
                    //    for(int sg = 0; sg < site_det_sig_idx[siteMapAIdx]; ++sg)
                    //    {
                    //        dbgMsg += std::to_string(site_det_sig[sdId + sg]) + " ";
                    //    }
                    //    dbgMsg += "\nsite det impl lut contains: ";
                    //    for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                    //    {
                    //        dbgMsg += std::to_string(site_det_impl_lut[sdlutId + sg]) + " ";
                    //    }
                    //    dbgMsg += "\nsite det impl ff contains: ";
                    //    for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                    //    {
                    //        dbgMsg += std::to_string(site_det_impl_ff[sdlutId + sg]) + " ";
                    //    }
                    //    dbgMsg += "\n";
                    //    dbgMsg += "\nsite det impl cksr contains: ";
                    //    for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                    //    {
                    //        dbgMsg += std::to_string(site_det_impl_cksr[sdckId + sg]) + " ";
                    //    }
                    //    dbgMsg += "\n";
                    //    dbgMsg += "\nsite det impl ce contains: ";
                    //    for(int sg = 0; sg < CE_IN_CLB; ++sg)
                    //    {
                    //        dbgMsg += std::to_string(site_det_impl_ce[sdceId + sg]) + " ";
                    //    }
                    //    dbgMsg += "\n";
                    //}
                    //////DBG

                    for(int sg = 0; sg < site_det_sig_idx[siteMapAIdx]; ++sg)
                    {
                        cand.sig[sg] = site_det_sig[sdId + sg];
                    }
                    for(int sg = 0; sg < SLICE_CAPACITY; ++sg)
                    {
                        cand.impl_lut[sg] = site_det_impl_lut[sdlutId + sg];
                        cand.impl_ff[sg] = site_det_impl_ff[sdlutId + sg];
                    }
                    for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                    {
                        cand.impl_cksr[sg] = site_det_impl_cksr[sdckId + sg];
                    }
                    for(int sg = 0; sg < CE_IN_CLB; ++sg)
                    {
                        cand.impl_ce[sg] = site_det_impl_ce[sdceId + sg];
                    }
                    /////

                    //////DBG
                    //if (collect_info)
                    //{
                    //    dbgMsg += "Greedy LG: Inst: " + std::to_string(instId) + " consider siteID:  " + std::to_string(siteMapIdx) + " - created candidate" + "\n";
                    //}
                    //////DBG

                    if (add_inst_to_cand_impl(node2outpinIdx_map, lut_type, flat_node2pin_start_map, flat_node2pin_map,
                                node2pincount, net2pincount, pin2net_map, pin_typeIds, flat_node2prclstrCount,
                                flat_node2precluster_map, flop2ctrlSetId_map, node2fence_region_map, flop_ctrlSets,
                                extended_ctrlSets, ext_ctrlSet_start_map, special_nodes, lutTypeInSliceUnit, lut_maxShared,
                                instId, lutId, ffId, half_ctrl_mode, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY, HALF_SLICE_CAPACITY,
                                BLE_CAPACITY, NUM_BLE_PER_SLICE, cand.impl_lut, cand.impl_ff, cand.impl_cksr, cand.impl_ce) && 
                            add_inst_to_sig(flat_node2prclstrCount[instId], flat_node2precluster_map,
                                instPcl, cand.sig, cand.sigIdx, SLICE_CAPACITY))
                    {
                        //////DBG
                        //if (collect_info)
                        //{
                        //    dbgMsg += std::to_string(sIdx) + "- Greedy LG Inst: " + std::to_string(instId) + " - possible location at (" + std::to_string(xVal) + ", " + std::to_string(yVal) + ") " + std::to_string(siteMapIdx) + "\n";
                        //}
                        //////DBG

                        // Adding the instance to the site is legal
                        // If this is the first legal position found, set the expansion search radius
                        if (bestScoreImprov == -10000.0)
                        {
                            int r = DREAMPLACE_STD_NAMESPACE::abs(spiral_accessor[saIdx]) + DREAMPLACE_STD_NAMESPACE::abs(spiral_accessor[saIdx + 1]); 
                            r += greedyExpansion;

                            int maxRad = DREAMPLACE_STD_NAMESPACE::max(num_sites_x, num_sites_y);
                            int nwR = DREAMPLACE_STD_NAMESPACE::min(maxRad, r);
                            end = nwR ? 2 * (nwR + 1) * nwR + 1 : 1;
                        }
                        //cand_score = computeCandidateScore(cand);
                        compute_candidate_score(pos_x, pos_y, pin_offset_x, pin_offset_y,
                                net_bbox, net_weights, site_xy, net_pinIdArrayX, net_pinIdArrayY, 
                                flat_net2pin_start_map, flat_node2pin_start_map, flat_node2pin_map,
                                sorted_net_map, pin2net_map, pin2node_map, net2pincount, lut_type,
                                xWirelenWt, yWirelenWt, extNetCountWt, wirelenImprovWt,
                                netShareScoreMaxNetDegree, wlScoreMaxNetDegree, half_ctrl_mode,
                                cand.sig, cand.siteId, cand.sigIdx, cand.score);

                        T scoreImprov = cand.score - site_det_score[siteMapAIdx];
                        //////DBG
                        //if (collect_info)
                        //{
                        //    dbgMsg += "Cand site Id: " + std::to_string(cand.siteId) + " and cand sig Idx: " + std::to_string(cand.sigIdx) + "\n";
                        //    dbgMsg +=  std::to_string(sIdx) + "- Greedy LG Inst: " + std::to_string(instId) + " cand score: " + std::to_string(cand.score) + ", site_det_score: " + std::to_string(site_det_score[siteMapAIdx]) + " and scoreImprov: ";
                        //    dbgMsg += std::to_string(scoreImprov) + " with bestScoreImprov " + std::to_string(bestScoreImprov) + "\n";
                        //}
                        //////DBG

                        if (scoreImprov > bestScoreImprov)
                        {
                            //std::cout << "Found best candidate for " << idx << std::endl;
                            bestCand = cand;
                            bestScoreImprov = scoreImprov;
                        }
                    }

                    //////DBG
                    //if (collect_info)
                    //{
                    //    dbgMsg += "Greedy LG Inst of " + std::to_string(instId) + " has bestCand site: " + std::to_string(bestCand.siteId) + " with bestScoreImprov " + std::to_string(bestScoreImprov) + "\n";
                    //}
                    //////DBG
                }
            }

            // Commit the found best legal solution
            if (bestCand.siteId != INVALID)
            {
                int stId = bestCand.siteId;
                int stAId = site2addr_map[stId];

                site_det_score[stAId] = bestCand.score;
                site_det_siteId[stAId] = bestCand.siteId;
                site_det_sig_idx[stAId] = bestCand.sigIdx;

                int sdId(stAId*SIG_IDX), sdlutId(stAId*SLICE_CAPACITY);
                int sdckId(stAId*CKSR_IN_CLB), sdceId(stAId*CE_IN_CLB);

                for (auto sg = 0; sg < bestCand.sigIdx; ++sg)
                {
                    site_det_sig[sdId + sg] = bestCand.sig[sg];
                }        
                for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                {
                    site_det_impl_lut[sdlutId + sg] = bestCand.impl_lut[sg];
                    site_det_impl_ff[sdlutId + sg] = bestCand.impl_ff[sg];
                }
                for (int sg = 0; sg < CKSR_IN_CLB; ++sg)
                {
                    site_det_impl_cksr[sdckId + sg] = bestCand.impl_cksr[sg];
                }
                for (int sg = 0; sg < CE_IN_CLB; ++sg)
                {
                    site_det_impl_ce[sdceId + sg] = bestCand.impl_ce[sg];
                }
                /////

                for (int cl = 0; cl < flat_node2prclstrCount[instId]; ++cl)
                {
                    int prclInst = flat_node2precluster_map[instPcl + cl];
                    inst_curr_detSite[prclInst] = stId;
                }
                greedyLegalizeInst = 1;

            } else
            {
                greedyLegalizeInst = 0;
            }
        }

        if (ripupLegalizeInst != 1 && greedyLegalizeInst != 1)
        {

            if (node2fence_region_map[instId] == ffId)
            {
                dreamplacePrint(kERROR, "unable to legalize FF inst: %u \n", instId);
            } else
            {
                dreamplacePrint(kERROR, "unable to legalize LUT%s inst: %u \n", lut_type[instId], instId);
            }

            //DBG
            //if (collect_info)
            //{
            //std::cout << dbgMsg << std::endl;
            //}
            //DBG
            break;
        }
        ////DBG
        //std::chrono::steady_clock::time_point pt4= std::chrono::steady_clock::now();
        //std::cout << i << ": inst " << instId << " of type "
        //    << node2fence_region_map[instId] << " RipUP&Greedy LG takes " 
        //    << std::chrono::duration_cast<std::chrono::microseconds>(pt4-begin).count()/1000000.0 
        //    << " (s)" << std::endl;
        ////DBG
    }

    return 0;
}

// slot assignment
template <typename T>
int slotAssign(
        const T* pos_x,
        const T* pos_y,
        const T* wlPrecond,
        const T* site_xy,
        const int* flop_ctrlSets,
        const int* flop2ctrlSetId_map,
        const int* flat_node2pin_start_map,
        const int* flat_node2pin_map,
        const int* flat_net2pin_start_map,
        const int* flat_net2pin_map,
        const int* pin2net_map,
        const int* pin2node_map,
        const int* node2pincount,
        const int* net2pincount,
        const int* node2outpinIdx_map,
        const int* node2fence_region_map,
        const int* pin_typeIds,
        const int* lut_type,
        const int* site_types,
        const int* sorted_net_map,
        const int* addr2site_map,
        const int* sites_with_special_nodes,
        const T slotAssignFlowWeightScale,
        const T slotAssignFlowWeightIncr,
        const int num_sites_x,
        const int num_sites_y,
        const int num_clb_sites,
        const int lutTypeInSliceUnit,
        const int lut_maxShared,
        const int CKSR_IN_CLB,
        const int CE_IN_CLB,
        const int SLICE_CAPACITY,
        const int HALF_SLICE_CAPACITY,
        const int BLE_CAPACITY,
        const int NUM_BLE_PER_SLICE,
        const int NUM_BLE_PER_HALF_SLICE,
        const int half_ctrl_mode,
        const int lutId,
        const int num_threads,
        int* site_det_sig_idx,
        int* site_det_impl_lut,
        int* site_det_impl_ff,
        int* site_det_impl_cksr,
        int* site_det_impl_ce,
        int* site_det_siteId
        )
{
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_clb_sites / num_threads / 16), 1);

#pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for(int sIdx = 0; sIdx < num_clb_sites; ++sIdx)
    {
        if (site_det_sig_idx[sIdx] > 0)
        {
            int siteId = addr2site_map[sIdx];

            //initSlotAssign
            int sdlutId(sIdx*SLICE_CAPACITY);
            int sdckId(sIdx*CKSR_IN_CLB), sdceId(sIdx*CE_IN_CLB);

            //Fixed FF ctrls
            if (half_ctrl_mode == 1)
            {
                std::vector<int> lut, ff;

                for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                {
                    if (site_det_impl_lut[sdlutId + sg] != INVALID)
                    {
                        lut.push_back(site_det_impl_lut[sdlutId + sg]);
                    }
                    if (site_det_impl_ff[sdlutId + sg] != INVALID)
                    {
                        ff.push_back(site_det_impl_ff[sdlutId + sg]);
                    }
                }

                // Pre-assign control sets
                // Note that the original impl FF assignment is feasible but it is optimized for minimum resource usage
                // Therefore, to enlarge the solution space exploration, we do following modifications based on the original control set assignment:
                //     (1) if ce[1] (ce[3]) is empty, we set it to ce[0] (ce[2]),
                //     (2) if (cksr[1], ce[2], ce[3]) are empty, we set them to (cksr[0], ce[0], ce[1])
                int cksr[CKSR_MAX_CAP];
                int ce[CE_MAX_CAP];

                for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                {
                    cksr[sg] = site_det_impl_cksr[sdckId + sg];
                }
                for(int sg = 0; sg < CE_IN_CLB; ++sg)
                {
                    ce[sg] = site_det_impl_ce[sdceId + sg];
                }

                if (ce[1] == INVALID)
                {
                    ce[1] = ce[0];
                }
                if (ce[3] == INVALID)
                {
                    ce[3] = ce[2];
                }
                if (cksr[1] == INVALID)
                {
                    cksr[1] = cksr[0];
                    ce[2] = ce[0];
                    ce[3] = ce[1];
                }

                //computeLUTScoreAndScoreImprov
                std::vector<subSlice<T> > bleS(lut.size()), bleP, bleLP;

                for (unsigned int i = 0; i < lut.size(); ++i)
                {
                    auto &ble = bleS[i];
                    ble.lut[0] = lut[i];
                    ble.lut[1] = INVALID;

                    subSlice<T> tempBLE(ble);
                    findBestFFs(flop_ctrlSets, flop2ctrlSetId_map, flat_node2pin_start_map, flat_node2pin_map,
                            flat_net2pin_start_map, flat_net2pin_map, pin2net_map, node2pincount, pin_typeIds,
                            net2pincount, node2outpinIdx_map, pin2node_map, sorted_net_map, lut_type, ff,
                            half_ctrl_mode, cksr[0], ce[0], ce[1], ble);

                    findBestFFs(flop_ctrlSets, flop2ctrlSetId_map, flat_node2pin_start_map, flat_node2pin_map,
                            flat_net2pin_start_map, flat_net2pin_map, pin2net_map, node2pincount, pin_typeIds,
                            net2pincount, node2outpinIdx_map, pin2node_map, sorted_net_map, lut_type, ff,
                            half_ctrl_mode, cksr[1], ce[2], ce[3], tempBLE);

                    if (tempBLE.score > ble.score)
                    {
                        ble = tempBLE;
                    }
                }

                bleP.clear();
                // Collect all feasible LUT pairs and compute their best scores and score improvement
                for(unsigned int aIdx = 0; aIdx < lut.size(); ++aIdx)
                {
                    const int lutA = lut[aIdx];
                    for(unsigned int bIdx = aIdx + 1; bIdx < lut.size(); ++bIdx)
                    {
                        const int lutB = lut[bIdx];
                        if (two_lut_compatibility_check(lut_type, flat_node2pin_start_map, flat_node2pin_map,
                                    pin2net_map, pin_typeIds, lutTypeInSliceUnit, lut_maxShared, lutA, lutB))
                        {
                            bleP.emplace_back();

                            auto &ble = bleP.back();
                            ble.lut[0] = lutA;
                            ble.lut[1] = lutB;

                            subSlice<T> tempBLE(ble);

                            findBestFFs(flop_ctrlSets, flop2ctrlSetId_map, flat_node2pin_start_map,
                                    flat_node2pin_map, flat_net2pin_start_map, flat_net2pin_map, pin2net_map,
                                    node2pincount, pin_typeIds, net2pincount, node2outpinIdx_map, pin2node_map,
                                    sorted_net_map, lut_type, ff, half_ctrl_mode, cksr[0], ce[0], ce[1], ble);

                            findBestFFs(flop_ctrlSets, flop2ctrlSetId_map, flat_node2pin_start_map,
                                    flat_node2pin_map, flat_net2pin_start_map, flat_net2pin_map, pin2net_map,
                                    node2pincount, pin_typeIds, net2pincount, node2outpinIdx_map, pin2node_map,
                                    sorted_net_map, lut_type, ff, half_ctrl_mode, cksr[1], ce[2], ce[3], tempBLE);

                            if (tempBLE.score > ble.score)
                            {
                                ble = tempBLE;
                            }
                            // We define the score improvement of a compatible LUT pair (a, b) as
                            //     improv(a, b) = max(BLEScore(a, b, *, *)) - max(BLEScore(a, -, *, *)) - max(BLEScore(b, -, *, *))
                            ble.improv = ble.score - bleS[aIdx].score - bleS[bIdx].score;
                        }
                    }
                }

                //pairLUTs
                pairLUTs(lut, bleP, bleS, slotAssignFlowWeightScale, slotAssignFlowWeightIncr, NUM_BLE_PER_SLICE, bleLP);

                //assignLUTsandFFs
                // Reset the existing slot assignment in site.det
                for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                {
                    site_det_impl_lut[sdlutId + sg] = INVALID;
                    site_det_impl_ff[sdlutId + sg] = INVALID;
                }
                for(int sg = 0; sg < CKSR_IN_CLB; ++sg)
                {
                    site_det_impl_cksr[sdckId + sg] = INVALID;
                }
                for(int sg = 0; sg < CE_IN_CLB; ++sg)
                {
                    site_det_impl_ce[sdceId + sg] = INVALID;
                }

                std::vector<T> scores;
                scores.assign(NUM_BLE_PER_SLICE, 0.0);

                // Sort legal LUT/LUT pairs by their score from high to low
                std::sort(bleLP.begin(), bleLP.end(), [&](const subSlice<T> &a, const subSlice<T> &b){ return a.score > b.score; });

                // Record the number of available LUT pair slots in low/high half of the slice
                int availLo = NUM_BLE_PER_HALF_SLICE;
                int availHi = NUM_BLE_PER_HALF_SLICE;

                // Assign LUTs one by one and determine thier best FFs at the same time
                for(const auto &estBLE : bleLP)
                {
                    subSlice<T> bleLo(estBLE);
                    subSlice<T> bleHi(estBLE);

                    findBestFFs(flop_ctrlSets, flop2ctrlSetId_map, flat_node2pin_start_map, flat_node2pin_map,
                            flat_net2pin_start_map, flat_net2pin_map, pin2net_map, node2pincount, pin_typeIds,
                            net2pincount, node2outpinIdx_map, pin2node_map, sorted_net_map, lut_type, ff,
                            half_ctrl_mode, cksr[0], ce[0], ce[1], bleLo);

                    findBestFFs(flop_ctrlSets, flop2ctrlSetId_map, flat_node2pin_start_map, flat_node2pin_map,
                            flat_net2pin_start_map, flat_net2pin_map, pin2net_map, node2pincount, pin_typeIds,
                            net2pincount, node2outpinIdx_map, pin2node_map, sorted_net_map, lut_type, ff,
                            half_ctrl_mode, cksr[1], ce[2], ce[3], bleHi);

                    // Try to fit the found BLE in the preferred feasible half slice
                    int lh = ((availLo && bleLo.score > bleHi.score) || !availHi ? 0 : 1);
                    const auto &ble = (lh ? bleHi : bleLo);
                    (lh ? availHi : availLo) -= 1;

                    int beg = lh * HALF_SLICE_CAPACITY;
                    int end = beg + HALF_SLICE_CAPACITY;

                    for (int idx = beg; idx < end; idx += BLE_CAPACITY)
                    {
                        int tpos = idx/SLICE_CAPACITY;
                        int pos = idx - int(tpos * SLICE_CAPACITY);
                        if (site_det_impl_lut[sdlutId + pos] == INVALID && site_det_impl_lut[sdlutId + pos + 1] == INVALID)
                        {

                            // Realize LUT assignment
                            // Assign LUTs with more inputs at odd slots
                            // In this way we can also make sure that all LUT6 are assigned at odd positions
                            int demA = (ble.lut[0] == INVALID ? 0 : lut_type[ble.lut[0]]);
                            int demB = (ble.lut[1] == INVALID ? 0 : lut_type[ble.lut[1]]);
                            int flip = (demA > demB ? 1 : 0);
                            site_det_impl_lut[sdlutId + pos] = ble.lut[flip];
                            site_det_impl_lut[sdlutId + pos + 1] = ble.lut[1 - flip];

                            // Realize FF assignment
                            for (int k : {0, 1})
                            {
                                site_det_impl_ff[sdlutId + pos + k] = ble.ff[k];
                                if (ble.ff[k] != INVALID)
                                {
                                    const int ffId = ble.ff[k];
                                    site_det_impl_cksr[sdckId + lh]= flop_ctrlSets[flop2ctrlSetId_map[ffId]*3 + 1];
                                    site_det_impl_ce[sdceId + 2*lh + k]= flop_ctrlSets[flop2ctrlSetId_map[ffId]*3 + 2];
                                    // Remove the FF assigned from the active list
                                    ff.erase(std::find(ff.begin(), ff.end(), ble.ff[k]));

                                }
                            }
                            scores[pos / BLE_CAPACITY] = ble.score;
                            break;
                        }
                    }
                }

                // Assign the rest of unassigned FFs
                //
                // We iteratively add one FF at a time
                // Each time, we add the FF gives the best score improvement
                while (!ff.empty())
                {
                    // Find the FF gives the best score improvement
                    int bestFFIdx(INVALID), bestPos(INVALID);
                    T bestImprov(-10000.0);
                    for(unsigned int ffIdx = 0; ffIdx < ff.size(); ++ffIdx)
                    {
                        int ffI = ff[ffIdx];
                        int ffcksr = flop_ctrlSets[flop2ctrlSetId_map[ffI]*3 + 1];
                        int ffce = flop_ctrlSets[flop2ctrlSetId_map[ffI]*3 + 2];

                        for (int pos = 0; pos < SLICE_CAPACITY; ++pos)
                        {
                            int lh = pos / HALF_SLICE_CAPACITY;
                            int toe = pos/BLE_CAPACITY;
                            int oe = pos - int(toe * BLE_CAPACITY);

                            if (site_det_impl_ff[sdlutId + pos] == INVALID && ffcksr == cksr[lh] && ffce == ce[2 * lh + oe])
                            {
                                int k = pos / BLE_CAPACITY * BLE_CAPACITY;
                                site_det_impl_ff[sdlutId + pos] = ffI;
                                T improv(0.0);
                                computeBLEScore(flat_node2pin_start_map, flat_node2pin_map, flat_net2pin_start_map,
                                        flat_net2pin_map, pin2net_map, pin2node_map, node2outpinIdx_map, pin_typeIds,
                                        lut_type, half_ctrl_mode, site_det_impl_lut[sdlutId + k], 
                                        site_det_impl_lut[sdlutId + k + 1], site_det_impl_ff[sdlutId + k],
                                        site_det_impl_ff[sdlutId + k+1], improv);

                                improv -= scores[k / BLE_CAPACITY];
                                site_det_impl_ff[sdlutId + pos] = INVALID;

                                if (improv > bestImprov)
                                {
                                    bestFFIdx = ffIdx;
                                    bestPos = pos;
                                    bestImprov = improv;
                                }
                            }
                        }
                    }

                    // Realize the best FF assignment found
                    int bestFF = ff[bestFFIdx];
                    int lh = bestPos / HALF_SLICE_CAPACITY;
                    int toe = bestPos/BLE_CAPACITY;
                    int oe = bestPos - int(toe * BLE_CAPACITY);
                    site_det_impl_ff[sdlutId + bestPos] = bestFF;
                    site_det_impl_cksr[sdckId + lh] = flop_ctrlSets[flop2ctrlSetId_map[bestFF]*3 + 1];
                    site_det_impl_ce[sdceId + 2 * lh + oe] = flop_ctrlSets[flop2ctrlSetId_map[bestFF]*3 + 2];

                    // Remove the best FF found from the active list
                    ff.erase(ff.begin() + bestFFIdx);

                    // Update the BLE slot score
                    scores[bestPos/BLE_CAPACITY] += bestImprov;
                }

                //order BLEs
                // Sort BLEs in each half slice by their Y centroid coordinates (cen.y - site.y)
                T siteY = site_xy[2*site_det_siteId[sIdx] + 1];
                for (int lh : {0, 1})
                {
                    bleLP.clear();

                    int beg = lh * HALF_SLICE_CAPACITY;
                    int end = beg + HALF_SLICE_CAPACITY;
                    for (int offset = beg; offset < end; offset += BLE_CAPACITY)
                    {
                        bleLP.emplace_back();
                        auto &ble = bleLP.back();
                        std::vector<int> insts;

                        for (int k : {0, 1})
                        {
                            if (site_det_impl_lut[sdlutId + offset + k] != INVALID)
                            {
                                insts.push_back(site_det_impl_lut[sdlutId + offset + k]);
                                ble.lut[k] = site_det_impl_lut[sdlutId + offset + k];
                            }
                            if (site_det_impl_ff[sdlutId + offset + k] != INVALID)
                            {
                                insts.push_back(site_det_impl_ff[sdlutId + offset + k]);
                                ble.ff[k] = site_det_impl_ff[sdlutId + offset + k];
                            }
                        }

                        // We use ble.score to store centroid.y - site.y of this BLE
                        if (insts.empty())
                        {
                            ble.score = 0.0;
                        } else
                        {
                            //Centroid of insts
                            T cenY(pos_y[insts[0]]*wlPrecond[insts[0]]), totalWt(wlPrecond[insts[0]]);
                            for(unsigned int el = 1; el < insts.size(); ++el)
                            {
                                cenY += pos_y[insts[el]] * wlPrecond[insts[el]]; 
                                totalWt += wlPrecond[insts[el]];
                            }
                            if (totalWt > 0)
                            {
                                cenY /= totalWt;
                            }

                            ble.score = cenY - siteY;
                        }
                    }

                    // Sort BLEs in this half slice by their centroid.y - site.y from low to high
                    // Put them back to the implementation
                    std::sort(bleLP.begin(), bleLP.end(), [&](const subSlice<T> &a, const subSlice<T> &b){ return a.score < b.score; });

                    for(unsigned int i = 0; i < bleLP.size(); ++i)
                    {
                        const auto &ble = bleLP[i];
                        int offset = lh * HALF_SLICE_CAPACITY + i * BLE_CAPACITY;
                        for (int k : {0, 1})
                        {
                            site_det_impl_lut[sdlutId + offset + k] = ble.lut[k];
                            site_det_impl_ff[sdlutId + offset + k] = ble.ff[k];
                        }
                    }
                }
            } else
            {
                ////DBG
                //char printMsg = 0;
                //std::string dbgMsg = "";
                //dbgMsg += std::to_string(sIdx) + " consider site: " + std::to_string(siteId) + "\n";
                ////DBG

                int res_lut[SLICE_MAX_CAP];
                int res_ff[SLICE_MAX_CAP];

                for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
                {
                    res_lut[sg] = site_det_impl_lut[sdlutId + sg];
                    res_ff[sg] = site_det_impl_ff[sdlutId + sg];
                }

                for (int sg = 0; sg < HALF_SLICE_CAPACITY; ++sg)
                {
                    int ssIdx = 2*sg;
                    subSlice<T> ble;

                    ble.lut[0] = res_lut[ssIdx];
                    ble.lut[1] = res_lut[ssIdx + 1];
                    ble.ff[0] = res_ff[ssIdx];
                    ble.ff[1] = res_ff[ssIdx + 1];


                    //DBG
                    //printMsg = 1;
                    //DBG

                    ////DBG
                    //dbgMsg += "Initial ALM" + std::to_string(sg) + " contains: ";
                    //dbgMsg += "lut0: " + std::to_string(ble.lut[0]) + ", ";
                    //dbgMsg += "lut1: " + std::to_string(ble.lut[1]) + ", ";
                    //dbgMsg += "ff0: " + std::to_string(ble.ff[0]) + ", ";
                    //dbgMsg += "ff1: " + std::to_string(ble.ff[1]) + "\n";
                    ////DBG

                    // Assign LUTs with more inputs at odd slots
                    if (sites_with_special_nodes[sIdx] != 1)
                    {
                        int demA = (ble.lut[0] == INVALID ? 0 : lut_type[ble.lut[0]]);
                        int demB = (ble.lut[1] == INVALID ? 0 : lut_type[ble.lut[1]]);
                        int flip = (demA > demB ? 1 : 0);
                        site_det_impl_lut[sdlutId + ssIdx] = ble.lut[flip];
                        site_det_impl_lut[sdlutId + ssIdx + 1] = ble.lut[1 - flip];
                    }

                    //Given LUT locations, ensure LUT driving FF are in same z
                    if ((ble.ff[0] != INVALID || ble.ff[1] != INVALID) &&
                            (ble.lut[0] != INVALID || ble.lut[1] != INVALID))
                    {
                        std::vector<std::vector<int> > lutOuts(2), ffIns(2);

                        for (int k : {0, 1})
                        {
                            if (ble.lut[k] == INVALID) continue;

                            int ndOutId = 4*ble.lut[k];
                            int ndOutPins = ndOutId + 4;
                            for (int nodeOutId = ndOutId; nodeOutId < ndOutPins; ++nodeOutId)
                            {
                                int outPinId = node2outpinIdx_map[nodeOutId];
                                if (outPinId == INVALID) continue;

                                int outNetId = pin2net_map[outPinId];
                                lutOuts[k].emplace_back(outNetId);
                            }
                        }

                        for (int k : {0, 1})
                        {
                            if (ble.ff[k] == INVALID) continue;

                            int elIt = flat_node2pin_start_map[ble.ff[k]];
                            int elEnd = flat_node2pin_start_map[ble.ff[k]+1];

                            for (int el = elIt; el < elEnd; ++el)
                            {
                                //Skip if not an input or output pin
                                int pinType = pin_typeIds[flat_node2pin_map[el]];
                                if (pinType != 1) continue;

                                int netId = pin2net_map[flat_node2pin_map[el]];
                                ffIns[k].emplace_back(netId);
                            }
                        }

                        for (int idx : {0, 1})
                        {
                            if (lutOuts[idx].size() == 0) continue;

                            for (int idy : {0, 1})
                            {
                                if (ffIns[idy].size() == 0) continue;

                                std::sort(lutOuts[idx].begin(), lutOuts[idx].end());
                                std::sort(ffIns[idy].begin(), ffIns[idy].end());

                                //Check for matching nets
                                int lId = 0, fId = 0;
                                int netlId = lutOuts[idx][lId];
                                int netfId = ffIns[idy][fId];

                                while(lId < lutOuts[idx].size() && fId < ffIns[idy].size())
                                {
                                    if (netlId < netfId)
                                    {
                                        ++lId;
                                        if (lId < lutOuts[idx].size())
                                        {
                                            netlId = lutOuts[idx][lId];
                                        } else
                                        {
                                            break;
                                        }
                                    } else if (netlId > netfId)
                                    {
                                        ++fId;
                                        if (fId < ffIns[idy].size())
                                        {
                                            netfId = ffIns[idy][fId];
                                        } else
                                        {
                                            break;
                                        }
                                    } else
                                    {
                                        //Move ff to same z as lut - Flip ffs
                                        if (idx != idy)
                                        {
                                            int ff0 = ble.ff[0];
                                            int ff1 = ble.ff[1];

                                            //Flip flop location
                                            ble.ff[0] = ff1;
                                            ble.ff[1] = ff0;
                                        }
                                        break;
                                    }
                                }
                            }
                        }
                    }

                    ////DBG
                    //dbgMsg += "Final ALM" + std::to_string(sg) + " contains: ";
                    //dbgMsg += "lut0: " + std::to_string(ble.lut[0]) + ", ";
                    //dbgMsg += "lut1: " + std::to_string(ble.lut[1]) + ", ";
                    //dbgMsg += "ff0: " + std::to_string(ble.ff[0]) + ", ";
                    //dbgMsg += "ff1: " + std::to_string(ble.ff[1]) + "\n";
                    ////DBG
                }

                ////DBG
                //if (printMsg == 1)
                //{
                //    std::cout << dbgMsg << std::endl;
                //}
                ////DBG

                //order subSlices if site does not contain special nodes like carry chains
                if (sites_with_special_nodes[sIdx] != 1)
                {
                    // Sort subSlices by their Y centroid coordinates (cen.y - site.y)
                    std::vector<subSlice<T> > bleLP;

                    T siteY = site_xy[2*site_det_siteId[sIdx] + 1];

                    for (int offset = 0; offset < SLICE_CAPACITY; offset += BLE_CAPACITY)
                    {
                        bleLP.emplace_back();
                        auto &ble = bleLP.back();
                        std::vector<int> insts;

                        for (int k : {0, 1})
                        {
                            if (site_det_impl_lut[sdlutId + offset + k] != INVALID)
                            {
                                insts.push_back(site_det_impl_lut[sdlutId + offset + k]);
                            }
                            ble.lut[k] = site_det_impl_lut[sdlutId + offset + k];
                            if (site_det_impl_ff[sdlutId + offset + k] != INVALID)
                            {
                                insts.push_back(site_det_impl_ff[sdlutId + offset + k]);
                            }
                            ble.ff[k] = site_det_impl_ff[sdlutId + offset + k];
                        }

                        // We use ble.score to store centroid.y - site.y of this BLE
                        if (insts.empty())
                        {
                            ble.score = 0.0;
                        } else
                        {
                            //Centroid of insts
                            T cenY(pos_y[insts[0]]*wlPrecond[insts[0]]), totalWt(wlPrecond[insts[0]]);
                            for(unsigned int el = 1; el < insts.size(); ++el)
                            {
                                cenY += pos_y[insts[el]] * wlPrecond[insts[el]]; 
                                totalWt += wlPrecond[insts[el]];
                            }
                            if (totalWt > 0)
                            {
                                cenY /= totalWt;
                            }

                            ble.score = cenY - siteY;
                        }
                    }
                    //std::cout << "siteId: " << siteId << " get scores for all BLEs"<< std::endl;

                    // Sort BLEs in slice by their centroid.y - site.y from low to high
                    // Put them back to the implementation
                    std::sort(bleLP.begin(), bleLP.end(), [&](const subSlice<T> &a, const subSlice<T> &b){ return a.score < b.score; });

                    for(unsigned int i = 0; i < bleLP.size(); ++i)
                    {
                        const auto &ble = bleLP[i];
                        int offset = i * BLE_CAPACITY;
                        for (int k : {0, 1})
                        {
                            site_det_impl_lut[sdlutId + offset + k] = ble.lut[k];
                            site_det_impl_ff[sdlutId + offset + k] = ble.ff[k];
                        }
                    }
                    //std::cout << "siteId: " << siteId << " complete sort all subSlices"<< std::endl;
                }
            }
        }
    }

    //std::cout << "Slot assignment done" << std::endl;
    return 0;
}

// Cache the solution
template <typename T>
int cacheSolution(
        const int* site_det_impl_lut,
        const int* site_det_impl_ff,
        const int* inst_curr_detSite,
        const int* addr2site_map,
        const int num_sites_y,
        const int num_clb_sites,
        const int SLICE_CAPACITY,
        T* node_x,
        T* node_y,
        int* node_z
        )
{
    for(int sIdx = 0; sIdx < num_clb_sites; ++sIdx)
    {
        int siteIdX = addr2site_map[sIdx] / num_sites_y;
        int siteIdY = addr2site_map[sIdx] - int(siteIdX*num_sites_y);
        int sdlutId(sIdx*SLICE_CAPACITY);
        for (int z = 0; z < SLICE_CAPACITY; ++z)
        {
            for (int id : {site_det_impl_lut[sdlutId + z], site_det_impl_ff[sdlutId + z]})
            {
                if (id != INVALID)
                {
                    node_x[id] = siteIdX;
                    node_y[id] = siteIdY;
                    node_z[id] = z;
                }
            }
        }
    }
    return 0;
}

////////////////////////////////////////////////////////////////////////////

//Initialize site neighbors
void initSiteNbrs(
              at::Tensor pos,
              at::Tensor wlPrecond,
              at::Tensor site_xy,
              at::Tensor site_det_score,
              at::Tensor sorted_node_idx,
              at::Tensor node2fence_region_map,
              at::Tensor site_types,
              at::Tensor spiral_accessor,
              at::Tensor site2addr_map,
              at::Tensor addr2site_map,
              at::Tensor flat_node2precluster_map,
              at::Tensor flat_node2prclstrCount,
              at::Tensor is_mlab_node,
              at::Tensor is_mlab_site,
              at::Tensor sites_with_special_nodes,
              double nbrDistEnd,
              double nbrDistBeg,
              double nbrDistIncr,
              int lutId,
              int ffId,
              int sliceId,
              int num_nodes,
              int num_sites_x,
              int num_sites_y,
              int num_clb_sites,
              int SCL_IDX,
              int SIG_IDX,
              int SLICE_CAPACITY,
              int numGroups,
              int maxList,
              int spiralBegin,
              int spiralEnd,
              at::Tensor site_curr_scl_score,
              at::Tensor site_curr_scl_siteId,
              at::Tensor site_curr_scl_validIdx,
              at::Tensor site_curr_scl_idx,
              at::Tensor site_curr_scl_sig,
              at::Tensor site_curr_scl_sig_idx,
              at::Tensor site_curr_scl_impl_lut,
              at::Tensor site_nbrRanges,
              at::Tensor site_nbrRanges_idx,
              at::Tensor site_nbrList,
              at::Tensor site_nbr,
              at::Tensor site_nbr_idx,
              at::Tensor site_nbrGroup_idx,
              at::Tensor site_det_siteId,
              at::Tensor site_det_sig,
              at::Tensor site_det_sig_idx,
              at::Tensor site_det_impl_lut,
              int num_threads)
{
    CHECK_FLAT(pos);
    CHECK_EVEN(pos);
    CHECK_CONTIGUOUS(pos);

    CHECK_FLAT(wlPrecond);
    CHECK_CONTIGUOUS(wlPrecond);

    CHECK_FLAT(site_xy);
    CHECK_CONTIGUOUS(site_xy);

    CHECK_FLAT(sorted_node_idx);
    CHECK_CONTIGUOUS(sorted_node_idx);

    CHECK_FLAT(node2fence_region_map);
    CHECK_CONTIGUOUS(node2fence_region_map);

    CHECK_FLAT(site_types);
    CHECK_CONTIGUOUS(site_types);

    CHECK_FLAT(spiral_accessor);
    CHECK_CONTIGUOUS(spiral_accessor);

    CHECK_FLAT(site2addr_map);
    CHECK_CONTIGUOUS(site2addr_map);

    CHECK_FLAT(addr2site_map);
    CHECK_CONTIGUOUS(addr2site_map);

    CHECK_FLAT(flat_node2precluster_map);
    CHECK_CONTIGUOUS(flat_node2precluster_map);

    CHECK_FLAT(flat_node2prclstrCount);
    CHECK_CONTIGUOUS(flat_node2prclstrCount);

    int numNodes = pos.numel() / 2;

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "initSiteNeighbours", [&] {
            initSiteNeighbours<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(wlPrecond, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_node_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2fence_region_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_types, int),
                    DREAMPLACE_TENSOR_DATA_PTR(spiral_accessor, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site2addr_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(addr2site_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(is_mlab_node, int),
                    DREAMPLACE_TENSOR_DATA_PTR(is_mlab_site, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sites_with_special_nodes, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2precluster_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2prclstrCount, int),
                    nbrDistEnd, nbrDistBeg, nbrDistIncr,
                    lutId, ffId, sliceId, num_nodes, num_sites_x, num_sites_y, 
                    num_clb_sites, spiralBegin, spiralEnd, maxList,
                    numGroups, SCL_IDX, SIG_IDX, SLICE_CAPACITY,
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrList, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrRanges, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrRanges_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbr_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrGroup_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_validIdx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_impl_lut, int),
                    num_threads);
    });
    //std::cout << "Completed initSiteNeighbours" << std::endl;

}

//Initialize and handle carry chains and mlabs
void initializeLG(
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
        int lutId,
        int ffId,
        int num_nets,
        int num_nodes,
        int num_threads,
        int WLscoreMaxNetDegree,
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

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "initializeNets", [&] {
            initializeNets<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_x, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_y, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_net_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net2pincount, int),
                    num_nets,
                    DREAMPLACE_TENSOR_DATA_PTR(net_bbox, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayX, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayY, int),
                    WLscoreMaxNetDegree, num_threads);
            });

    //std::cout << "Completed initializeNets " << std::endl;

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "preClusteringUpd", [&] {
            preClusteringUpd<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_x, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_y, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_node_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop2ctrlSetId_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop_ctrlSets, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2fence_region_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2outpinIdx_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2net_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_typeIds, int),
                    DREAMPLACE_TENSOR_DATA_PTR(is_mlab_node, int),
                    preClusteringMaxDist, lutId, ffId, num_nodes,
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2precluster_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2prclstrCount, int),
                    num_threads);
            });
    //std::cout << "Completed preclusteringUpd" << std::endl;
}

//Legalize carry-chains
void legalizeCarryChain(
        at::Tensor pos,
        at::Tensor site_xy,
        at::Tensor wlPrecond,
        at::Tensor spiral_accessor,
        at::Tensor site_types,
        at::Tensor site2addr_map,
        at::Tensor flat_cc2node_start_map,
        at::Tensor flat_cc2node_map,
        int spiralBegin,
        int spiralEnd,
        int num_sites_x,
        int num_sites_y,
        int sliceId,
        int SIG_IDX,
        int SLICE_CAPACITY,
        int num_carry_chains,
        int num_carryInstsInSlice,
        int slice_minX,
        int slice_maxX,
        int slice_minY,
        int slice_maxY,
        at::Tensor carry_chain_displacements,
        at::Tensor site_det_score,
        at::Tensor inst_curr_bestScoreImprov,
        at::Tensor inst_next_bestScoreImprov,
        at::Tensor sites_with_special_nodes,
        at::Tensor inst_curr_detSite,
        at::Tensor inst_curr_bestSite,
        at::Tensor inst_next_detSite,
        at::Tensor inst_next_bestSite,
        at::Tensor site_det_siteId,
        at::Tensor site_det_sig,
        at::Tensor site_det_sig_idx,
        at::Tensor site_det_impl_lut,
        int num_threads)
{
    CHECK_FLAT(pos);
    CHECK_EVEN(pos);
    CHECK_CONTIGUOUS(pos);

    CHECK_FLAT(site_xy);
    CHECK_CONTIGUOUS(site_xy);

    CHECK_FLAT(wlPrecond);
    CHECK_CONTIGUOUS(wlPrecond);

    CHECK_FLAT(site2addr_map);
    CHECK_CONTIGUOUS(site2addr_map);

    CHECK_FLAT(flat_cc2node_start_map);
    CHECK_CONTIGUOUS(flat_cc2node_start_map);
    CHECK_FLAT(flat_cc2node_map);
    CHECK_CONTIGUOUS(flat_cc2node_map);

    CHECK_FLAT(spiral_accessor);
    CHECK_CONTIGUOUS(spiral_accessor);

    CHECK_FLAT(site_types);
    CHECK_CONTIGUOUS(site_types);

    int numNodes = pos.numel() / 2;

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "legalizeCarryChainsLauncher", [&] {
            legalizeCarryChainsLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(wlPrecond, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site2addr_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_cc2node_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_cc2node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(spiral_accessor, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_types, int),
                    spiralBegin, spiralEnd, num_carry_chains, num_sites_x, num_sites_y,
                    sliceId, SIG_IDX, SLICE_CAPACITY, num_carryInstsInSlice, 
                    slice_minX, slice_maxX, slice_minY, slice_maxY,
                    DREAMPLACE_TENSOR_DATA_PTR(carry_chain_displacements, scalar_t),
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
                    DREAMPLACE_TENSOR_DATA_PTR(sites_with_special_nodes, int),
                    num_threads);
    });

}

//MinCost to find sites
void minCostFlow(
    pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& locX,
    pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& locY,
    int const num_sites, int const num_nodes,
    pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& sites,
    pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& precond,
    double const &lg_max_dist_init, double const &lg_max_dist_incr,
    double const &lg_flow_cost_scale, pybind11::list &movVal, pybind11::list &out)
{
    typedef lemon::ListDigraph graphType;
    graphType graph; 
    graphType::ArcMap<double> capLo(graph);
    graphType::ArcMap<double> capHi(graph);
    graphType::ArcMap<double> cost(graph);
    std::vector<graphType::Node> lNodes, rNodes;
    std::vector<graphType::Arc> lArcs, rArcs, mArcs;
    std::vector<std::pair<int, int> > mArcPairs;

    //Source and target Nodes
    graphType::Node s = graph.addNode(), t = graph.addNode();

    //Add left nodes (blocks) and arcs between source node and left nodes
    for (int i = 0; i < num_nodes; ++i)
    {
        lNodes.emplace_back(graph.addNode());
        lArcs.emplace_back(graph.addArc(s, lNodes.back()));
        cost[lArcs.back()] = 0.0;
        capLo[lArcs.back()] = 0.0;
        capHi[lArcs.back()] = 1.0;
    }

    //Add right nodes (sites) and arc between right nodes and target node
    for (int j=0; j < num_sites; ++j)
    {
        rNodes.emplace_back(graph.addNode());
        rArcs.emplace_back(graph.addArc(rNodes.back(), t));
        cost[rArcs.back()] = 0.0;
        capLo[rArcs.back()] = 0.0;
        capHi[rArcs.back()] = 1.0;
    }

    //To improve efficiency, we do not run matching for complete bipartite graph but incrementally add arcs when needed
    double distMin = 0.0;
    double distMax = lg_max_dist_init;

    while (true)
    {
        //Generate arcs between left (blocks) and right (sites) nodes, pruning based on distance
        for (int blk = 0; blk < num_nodes; ++blk)
        {
            for (int st = 0; st < num_sites; ++st)
            {
                double dist = std::abs(locX.at(blk) - sites.at(st*2)) + std::abs(locY.at(blk) - sites.at(st*2+1));
                if (dist >= distMin && dist < distMax)
                {
                    mArcs.emplace_back(graph.addArc(lNodes[blk], rNodes[st]));
                    mArcPairs.emplace_back(blk, st);
                    double mArcCost = dist * precond.at(blk) * lg_flow_cost_scale;
                    cost[mArcs.back()] = mArcCost;
                    capLo[mArcs.back()] = 0.0;
                    capHi[mArcs.back()] = 1.0;
                }
            }
        }

        //Run min-cost flow
        lemon::NetworkSimplex<graphType, double> mcf(graph);
        mcf.stSupply(s, t, num_nodes);
        mcf.lowerMap(capLo).upperMap(capHi).costMap(cost);
        mcf.run();

        //A feasible solution must have flow size equal to the no of blocks
        //If not, we need to increase the max distance constraint
        double flowSize = 0.0;
        for (const auto &arc : rArcs)
        {
            flowSize += mcf.flow(arc);
        }
        if (flowSize != num_nodes)
        {
            //Increase searching range
            distMin = distMax;
            distMax += lg_max_dist_incr;
            continue;
        }

        double maxMov = 0;
        double avgMov = 0;
        //If the execution hits here, we found a feasible solution
        for (int i = 0; i < mArcs.size(); ++i)
        {
            if (mcf.flow(mArcs[i]))
            {
                const auto &p = mArcPairs[i];
                double mov = std::abs(locX.at(p.first) - sites.at(p.second*2)) + std::abs(locY.at(p.first) - sites.at(p.second*2+1));
                avgMov += mov;
                maxMov = std::max(maxMov, mov);
                out[p.first] = sites.at(p.second*2);
                out[num_nodes+p.first] = sites.at(p.second*2+1);
            }
        }
        if (num_nodes)
        {
            avgMov /= num_nodes;
        }
        movVal[0] = maxMov;
        movVal[1] = avgMov;
        return;
    }
}

//Legalize Macro
void legalizeMacro(
        at::Tensor pos,
        at::Tensor site_xy,
        at::Tensor macro2node_map,
        at::Tensor macro_site_height,
        at::Tensor macro_element_count,
        at::Tensor spiral_accessor,
        at::Tensor site2addr_map,
        at::Tensor site_types,
        int spiralBegin,
        int spiralEnd,
        int num_macros,
        int num_sites_x,
        int num_sites_y,
        int slice_minX,
        int slice_maxX,
        int slice_minY,
        int slice_maxY,
        int sliceId,
        int SIG_IDX,
        int SLICE_CAPACITY,
        at::Tensor dist_moved,
        at::Tensor site_det_score,
        at::Tensor inst_curr_bestScoreImprov,
        at::Tensor inst_next_bestScoreImprov,
        at::Tensor site_det_siteId,
        at::Tensor site_det_sig,
        at::Tensor site_det_sig_idx,
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

    CHECK_FLAT(site2addr_map);
    CHECK_CONTIGUOUS(site2addr_map);

    CHECK_FLAT(spiral_accessor);
    CHECK_CONTIGUOUS(spiral_accessor);

    CHECK_FLAT(site_types);
    CHECK_CONTIGUOUS(site_types);

    CHECK_FLAT(macro2node_map);
    CHECK_CONTIGUOUS(macro2node_map);

    int numNodes = pos.numel() / 2;

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "legalizeMacrosLauncher", [&] {
            legalizeMacrosLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(macro2node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(macro_site_height, int),
                    DREAMPLACE_TENSOR_DATA_PTR(macro_element_count, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site2addr_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(spiral_accessor, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_types, int),
                    spiralBegin, spiralEnd, num_macros, num_sites_x,
                    num_sites_y, slice_minX, slice_maxX, slice_minY,
                    slice_maxY, sliceId, SIG_IDX, SLICE_CAPACITY,
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
                    DREAMPLACE_TENSOR_DATA_PTR(sites_with_special_nodes, int));
    });
    //std::cout << "Completed legalizeMacro" << std::endl;
}

//Legalize Mlab 
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
        at::Tensor sites_with_special_nodes,
        at::Tensor inst_curr_detSite,
        at::Tensor inst_curr_bestSite,
        at::Tensor inst_next_detSite,
        at::Tensor inst_next_bestSite,
        at::Tensor site_det_siteId,
        at::Tensor site_det_sig,
        at::Tensor site_det_sig_idx,
        at::Tensor site_det_impl_lut,
        int num_threads)
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

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "legalizeMlabsLauncher", [&] {
            legalizeMlabsLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(mlab_locX, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(mlab_locY, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(mlab_indices, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site2addr_map, int),
                    num_mlab_nodes, num_sites_y, 
                    SIG_IDX, SLICE_CAPACITY,
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
                    DREAMPLACE_TENSOR_DATA_PTR(sites_with_special_nodes, int),
                    num_threads);
    });
    //std::cout << "Completed legalizeMlab" << std::endl;
}

//runDLIteration
void runDLIter(
        at::Tensor pos,
        at::Tensor pin_offset_x,
        at::Tensor pin_offset_y,
        at::Tensor net_bbox,
        at::Tensor net_pinIdArrayX,
        at::Tensor net_pinIdArrayY,
        at::Tensor site_xy,
        at::Tensor node2fence_region_map,
        at::Tensor flop_ctrlSets,
        at::Tensor extended_ctrlSets,
        at::Tensor ext_ctrlSet_start_map,
        at::Tensor flop2ctrlSetId_map,
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
        at::Tensor flat_node2prclstrCount,
        at::Tensor flat_node2precluster_map,
        at::Tensor is_mlab_node,
        at::Tensor is_mlab_site,
        at::Tensor site_nbrList,
        at::Tensor site_nbrRanges,
        at::Tensor site_nbrRanges_idx,
        at::Tensor sorted_node_map,
        at::Tensor sorted_net_map,
        at::Tensor net_weights,
        at::Tensor addr2site_map,
        at::Tensor special_nodes,
        int num_sites_x,
        int num_sites_y,
        int num_clb_sites,
        int minStableIter,
        int maxList,
        int half_ctrl_mode,
        int SLICE_CAPACITY,
        int HALF_SLICE_CAPACITY,
        int BLE_CAPACITY,
        int NUM_BLE_PER_SLICE,
        int minNeighbors,
        int numGroups,
        int netShareScoreMaxNetDegree,
        int wlScoreMaxNetDegree,
        int lutTypeInSliceUnit,
        int lut_maxShared,
        double xWirelenWt,
        double yWirelenWt,
        double wirelenImprovWt,
        double extNetCountWt,
        int CKSR_IN_CLB,
        int CE_IN_CLB,
        int SCL_IDX,
        int PQ_IDX,
        int SIG_IDX,
        int lutId,
        int ffId,
        int num_nodes,
        int num_threads,
        at::Tensor site_nbr_idx,
        at::Tensor site_nbr,
        at::Tensor site_nbrGroup_idx,
        at::Tensor site_curr_pq_top_idx,
        at::Tensor site_curr_pq_sig_idx,
        at::Tensor site_curr_pq_sig,
        at::Tensor site_curr_pq_idx,
        at::Tensor site_curr_pq_validIdx,
        at::Tensor site_curr_stable,
        at::Tensor site_curr_pq_siteId,
        at::Tensor site_curr_pq_score,
        at::Tensor site_curr_pq_impl_lut,
        at::Tensor site_curr_pq_impl_ff,
        at::Tensor site_curr_pq_impl_cksr,
        at::Tensor site_curr_pq_impl_ce,
        at::Tensor site_curr_scl_score,
        at::Tensor site_curr_scl_siteId,
        at::Tensor site_curr_scl_idx,
        at::Tensor site_curr_scl_validIdx,
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
        at::Tensor illegalStatus
        )
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

    CHECK_FLAT(node2fence_region_map);
    CHECK_CONTIGUOUS(node2fence_region_map);

    CHECK_FLAT(flop_ctrlSets);
    CHECK_CONTIGUOUS(flop_ctrlSets);
    CHECK_FLAT(flop2ctrlSetId_map);
    CHECK_CONTIGUOUS(flop2ctrlSetId_map);

    CHECK_FLAT(lut_type);
    CHECK_CONTIGUOUS(lut_type);

    CHECK_FLAT(flat_node2pin_map);
    CHECK_CONTIGUOUS(flat_node2pin_map);
    CHECK_FLAT(flat_node2pin_start_map);
    CHECK_CONTIGUOUS(flat_node2pin_start_map);

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

    CHECK_FLAT(net_weights);
    CHECK_CONTIGUOUS(net_weights);

    int numNodes = pos.numel() / 2;

    //Run DL Iteration
    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "runDLIteration", [&] {
            runDLIteration<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_x, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_y, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_bbox, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayX, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayY, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2fence_region_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop_ctrlSets, int),
                    DREAMPLACE_TENSOR_DATA_PTR(extended_ctrlSets, int),
                    DREAMPLACE_TENSOR_DATA_PTR(ext_ctrlSet_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop2ctrlSetId_map, int),
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
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_net_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2prclstrCount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2precluster_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(is_mlab_node, int),
                    DREAMPLACE_TENSOR_DATA_PTR(is_mlab_site, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrList, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrRanges, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrRanges_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net_weights, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(addr2site_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(special_nodes, int),
                    num_clb_sites, minStableIter, maxList, half_ctrl_mode, SLICE_CAPACITY,
                    HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE,
                    minNeighbors, numGroups, netShareScoreMaxNetDegree,
                    wlScoreMaxNetDegree, lutTypeInSliceUnit, lut_maxShared,
                    xWirelenWt, yWirelenWt, wirelenImprovWt, extNetCountWt, 
                    CKSR_IN_CLB, CE_IN_CLB, SCL_IDX, PQ_IDX, SIG_IDX,
                    lutId, ffId, num_threads,
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbr_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_nbrGroup_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_top_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_validIdx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_stable, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_cksr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_ce, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_score, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_validIdx, int),
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
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_bestSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_detSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_bestScoreImprov, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_next_bestSite, int));
                });

    //std::cout << "Run DL Iter "<< std::endl;

    //Run DL Sync 
    DREAMPLACE_DISPATCH_FLOATING_TYPES(site_curr_pq_score, "runDLSynchronize", [&] {
                        runDLSynchronize<scalar_t>(
                                DREAMPLACE_TENSOR_DATA_PTR(node2fence_region_map, int),
                                DREAMPLACE_TENSOR_DATA_PTR(addr2site_map, int),
                                num_clb_sites, SLICE_CAPACITY, CKSR_IN_CLB, CE_IN_CLB, 
                                SCL_IDX, PQ_IDX, SIG_IDX, lutId, ffId, num_nodes, num_threads,
                                DREAMPLACE_TENSOR_DATA_PTR(site_nbrGroup_idx, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_nbrRanges_idx, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_top_idx, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_sig_idx, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_sig, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_idx, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_validIdx, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_stable, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_siteId, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_score, scalar_t),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_lut, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_ff, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_cksr, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_pq_impl_ce, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_score, scalar_t),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_siteId, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_idx, int),
                                DREAMPLACE_TENSOR_DATA_PTR(site_curr_scl_validIdx, int),
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
                                DREAMPLACE_TENSOR_DATA_PTR(inst_curr_detSite, int),
                                DREAMPLACE_TENSOR_DATA_PTR(inst_curr_bestSite, int),
                                DREAMPLACE_TENSOR_DATA_PTR(inst_curr_bestScoreImprov, scalar_t),
                                DREAMPLACE_TENSOR_DATA_PTR(inst_next_detSite, int),
                                DREAMPLACE_TENSOR_DATA_PTR(inst_next_bestSite, int),
                                DREAMPLACE_TENSOR_DATA_PTR(inst_next_bestScoreImprov, scalar_t),
                                DREAMPLACE_TENSOR_DATA_PTR(activeStatus, int),
                                DREAMPLACE_TENSOR_DATA_PTR(illegalStatus, int));
                    });

    //std::cout << "Run DL Sync: " << DLStatus << std::endl;
}

//RipUp & Greedy Legalization
void ripUp_SlotAssign(
        at::Tensor pos,
        at::Tensor pin_offset_x,
        at::Tensor pin_offset_y,
        at::Tensor net_weights,
        at::Tensor net_bbox,
        at::Tensor inst_areas,
        at::Tensor wlPrecond,
        at::Tensor site_xy,
        at::Tensor net_pinIdArrayX,
        at::Tensor net_pinIdArrayY,
        at::Tensor spiral_accessor,
        at::Tensor node2fence_region_map,
        at::Tensor lut_type,
        at::Tensor site_types,
        at::Tensor node2pincount,
        at::Tensor net2pincount,
        at::Tensor pin2net_map,
        at::Tensor pin2node_map,
        at::Tensor pin_typeIds,
        at::Tensor flop2ctrlSetId_map,
        at::Tensor flop_ctrlSets,
        at::Tensor extended_ctrlSets,
        at::Tensor ext_ctrlSet_start_map,
        at::Tensor flat_node2pin_start_map,
        at::Tensor flat_node2pin_map,
        at::Tensor flat_net2pin_start_map,
        at::Tensor flat_node2prclstrCount,
        at::Tensor flat_node2precluster_map,
        at::Tensor sorted_node_map,
        at::Tensor sorted_node_idx,
        at::Tensor sorted_net_map,
        at::Tensor node2outpinIdx_map,
        at::Tensor flat_net2pin_map,
        at::Tensor addr2site_map,
        at::Tensor site2addr_map,
        at::Tensor sites_with_special_nodes,
        at::Tensor special_nodes,
        double nbrDistEnd,
        double xWirelenWt,
        double yWirelenWt,
        double extNetCountWt,
        double wirelenImprovWt,
        double slotAssignFlowWeightScale,
        double slotAssignFlowWeightIncr,
        int lutTypeInSliceUnit,
        int lut_maxShared,
        int num_nodes,
        int num_sites_x,
        int num_sites_y,
        int num_clb_sites,
        int spiralBegin,
        int spiralEnd,
        int half_ctrl_mode,
        int CKSR_IN_CLB,
        int CE_IN_CLB,
        int SLICE_CAPACITY,
        int HALF_SLICE_CAPACITY,
        int BLE_CAPACITY,
        int NUM_BLE_PER_SLICE,
        int NUM_BLE_PER_HALF_SLICE,
        int netShareScoreMaxNetDegree,
        int wlScoreMaxNetDegree,
        int ripupExpansion,
        int greedyExpansion,
        int SIG_IDX,
        int lutId,
        int ffId,
        int sliceId,
        int num_threads,
        at::Tensor inst_curr_detSite,
        at::Tensor site_det_sig_idx,
        at::Tensor site_det_sig,
        at::Tensor site_det_impl_lut,
        at::Tensor site_det_impl_ff,
        at::Tensor site_det_impl_cksr,
        at::Tensor site_det_impl_ce,
        at::Tensor site_det_siteId,
        at::Tensor site_det_score,
        at::Tensor node_x,
        at::Tensor node_y,
        at::Tensor node_z
        )
{
    CHECK_FLAT(pos);
    CHECK_EVEN(pos);
    CHECK_CONTIGUOUS(pos);

    CHECK_FLAT(pin_offset_x);
    CHECK_CONTIGUOUS(pin_offset_x);
    CHECK_FLAT(pin_offset_y);
    CHECK_CONTIGUOUS(pin_offset_y);

    CHECK_FLAT(net_weights);
    CHECK_CONTIGUOUS(net_weights);

    CHECK_FLAT(net_bbox);
    CHECK_CONTIGUOUS(net_bbox);

    CHECK_FLAT(inst_areas);
    CHECK_CONTIGUOUS(inst_areas);

    CHECK_FLAT(wlPrecond);
    CHECK_CONTIGUOUS(wlPrecond);

    CHECK_FLAT(site_xy);
    CHECK_CONTIGUOUS(site_xy);

    CHECK_FLAT(net_pinIdArrayX);
    CHECK_CONTIGUOUS(net_pinIdArrayX);
    CHECK_FLAT(net_pinIdArrayY);
    CHECK_CONTIGUOUS(net_pinIdArrayY);

    CHECK_FLAT(spiral_accessor);
    CHECK_CONTIGUOUS(spiral_accessor);

    CHECK_FLAT(node2fence_region_map);
    CHECK_CONTIGUOUS(node2fence_region_map);

    CHECK_FLAT(lut_type);
    CHECK_CONTIGUOUS(lut_type);

    CHECK_FLAT(site_types);
    CHECK_CONTIGUOUS(site_types);

    CHECK_FLAT(node2pincount);
    CHECK_CONTIGUOUS(node2pincount);

    CHECK_FLAT(net2pincount);
    CHECK_CONTIGUOUS(net2pincount);

    CHECK_FLAT(pin2net_map);
    CHECK_CONTIGUOUS(pin2net_map);

    CHECK_FLAT(pin2node_map);
    CHECK_CONTIGUOUS(pin2node_map);

    CHECK_FLAT(pin_typeIds);
    CHECK_CONTIGUOUS(pin_typeIds);

    CHECK_FLAT(flop2ctrlSetId_map);
    CHECK_CONTIGUOUS(flop2ctrlSetId_map);
    CHECK_FLAT(flop_ctrlSets);
    CHECK_CONTIGUOUS(flop_ctrlSets);

    CHECK_FLAT(flat_node2pin_start_map);
    CHECK_CONTIGUOUS(flat_node2pin_start_map);
    CHECK_FLAT(flat_node2pin_map);
    CHECK_CONTIGUOUS(flat_node2pin_map);

    CHECK_FLAT(flat_net2pin_start_map);
    CHECK_CONTIGUOUS(flat_net2pin_start_map);
    CHECK_FLAT(flat_net2pin_map);
    CHECK_CONTIGUOUS(flat_net2pin_map);

    CHECK_FLAT(flat_node2prclstrCount);
    CHECK_CONTIGUOUS(flat_node2prclstrCount);
    CHECK_FLAT(flat_node2precluster_map);
    CHECK_CONTIGUOUS(flat_node2precluster_map);

    CHECK_FLAT(sorted_node_map);
    CHECK_CONTIGUOUS(sorted_node_map);
    CHECK_FLAT(sorted_node_idx);
    CHECK_CONTIGUOUS(sorted_node_idx);

    CHECK_FLAT(sorted_net_map);
    CHECK_CONTIGUOUS(sorted_net_map);

    int numNodes = pos.numel() / 2;

    ////DBG
    //CPUTimer::hr_clock_rep timer_start, timer_stop;
    //timer_start = CPUTimer::getGlobaltime();
    ////DBG

    //RipUp & Greedy Legalization
    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "ripUp_Greedy_LG", [&] {
            ripUp_Greedy_LG<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_x, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_offset_y, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_weights, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_bbox, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_areas, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(wlPrecond, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayX, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net_pinIdArrayY, int),
                    DREAMPLACE_TENSOR_DATA_PTR(spiral_accessor, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2fence_region_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(lut_type, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_types, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2outpinIdx_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2pincount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net2pincount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2net_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_typeIds, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop2ctrlSetId_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop_ctrlSets, int),
                    DREAMPLACE_TENSOR_DATA_PTR(extended_ctrlSets, int),
                    DREAMPLACE_TENSOR_DATA_PTR(ext_ctrlSet_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2prclstrCount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2precluster_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_node_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_net_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(addr2site_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site2addr_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sites_with_special_nodes, int),
                    DREAMPLACE_TENSOR_DATA_PTR(special_nodes, int),
                    nbrDistEnd, xWirelenWt, yWirelenWt, extNetCountWt,
                    wirelenImprovWt, lutTypeInSliceUnit, lut_maxShared,
                    num_nodes, num_sites_x, num_sites_y, num_clb_sites,
                    spiralBegin, spiralEnd, half_ctrl_mode, CKSR_IN_CLB, CE_IN_CLB,
                    SLICE_CAPACITY, HALF_SLICE_CAPACITY, BLE_CAPACITY,
                    NUM_BLE_PER_SLICE, netShareScoreMaxNetDegree,
                    wlScoreMaxNetDegree, ripupExpansion, greedyExpansion,
                    SIG_IDX, lutId, ffId, sliceId,
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_detSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_cksr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_ce, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_siteId, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_score, scalar_t));
    });

    ////DBG
    //timer_stop = CPUTimer::getGlobaltime();
    //dreamplacePrint(kINFO, "RipUp & Greedy LG takes %.4f s\n",
    //        (timer_stop - timer_start) * CPUTimer::getTimerPeriod()/1000.0);
    //timer_start = CPUTimer::getGlobaltime();
    ////DBG

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "slotAssign", [&] {
            slotAssign<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + numNodes,
                    DREAMPLACE_TENSOR_DATA_PTR(wlPrecond, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(site_xy, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(flop_ctrlSets, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flop2ctrlSetId_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2net_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin2node_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2pincount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(net2pincount, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2outpinIdx_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(node2fence_region_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(pin_typeIds, int),
                    DREAMPLACE_TENSOR_DATA_PTR(lut_type, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_types, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_net_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(addr2site_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sites_with_special_nodes, int),
                    slotAssignFlowWeightScale, slotAssignFlowWeightIncr,
                    num_sites_x, num_sites_y, num_clb_sites, lutTypeInSliceUnit,
                    lut_maxShared, CKSR_IN_CLB, CE_IN_CLB, SLICE_CAPACITY,
                    HALF_SLICE_CAPACITY, BLE_CAPACITY, NUM_BLE_PER_SLICE,
                    NUM_BLE_PER_HALF_SLICE, half_ctrl_mode, lutId, num_threads, 
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_sig_idx, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_cksr, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_ce, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_siteId, int));
    });

    ////DBG
    //timer_stop = CPUTimer::getGlobaltime();
    //dreamplacePrint(kINFO, "Slot Assign takes %g ms\n",
    //        (timer_stop - timer_start) * CPUTimer::getTimerPeriod());
    //timer_start = CPUTimer::getGlobaltime();
    ////DBG

    //Cache Solution
    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "cacheSolution", [&] {
            cacheSolution<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_lut, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_det_impl_ff, int),
                    DREAMPLACE_TENSOR_DATA_PTR(inst_curr_detSite, int),
                    DREAMPLACE_TENSOR_DATA_PTR(addr2site_map, int),
                    num_sites_y, num_clb_sites, SLICE_CAPACITY,
                    DREAMPLACE_TENSOR_DATA_PTR(node_x, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(node_y, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(node_z, int));
            });

    ////DBG
    //timer_stop = CPUTimer::getGlobaltime();
    //dreamplacePrint(kINFO, "Cache Solution takes %g ms\n",
    //        (timer_stop - timer_start) * CPUTimer::getTimerPeriod());
    ////DBG
}

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("initializeLG", &DREAMPLACE_NAMESPACE::initializeLG, "Initialize LUT/FF legalization to handle carry-chains and mlabs");
  m.def("minCostFlow", &DREAMPLACE_NAMESPACE::minCostFlow, "Min Cost flow to get site locations");
  m.def("legalizeCarryChain", &DREAMPLACE_NAMESPACE::legalizeCarryChain, "Legalize carry-chains");
  m.def("legalizeMacro", &DREAMPLACE_NAMESPACE::legalizeMacro, "Legalize Slice Macros");
  m.def("legalizeMlab", &DREAMPLACE_NAMESPACE::legalizeMlab, "Legalize Mlabs");
  m.def("initSiteNbrs", &DREAMPLACE_NAMESPACE::initSiteNbrs, "Initialize site neighbors");
  m.def("runDLIter", &DREAMPLACE_NAMESPACE::runDLIter, "Run DL Iteration");
  m.def("ripUp_SlotAssign", &DREAMPLACE_NAMESPACE::ripUp_SlotAssign, "Run RipUp and Greedy Legalization and Slot Assign");
}

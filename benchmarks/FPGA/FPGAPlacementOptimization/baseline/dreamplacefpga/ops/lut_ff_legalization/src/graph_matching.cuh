/**
 * @file   graph_matching.cuh
 * @author Rachel Selina Rajarathnam, Zixuan Jiang (DREAMPlaceFPGA-PL)
 * @date   Oct 2022
 */
#include "utility/src/utils.cuh"

DREAMPLACE_BEGIN_NAMESPACE

#define INVALID -1
#define INPUT_PIN 1
#define MAX_SLICE_INPUTS 100
//Reset below values if required:
//Below values are for max vertex count of N=20
#define SLICE_MAX_CAP 20
#define N 20
#define N2 400
#define NN 40
#define M 30
#define M2 900

///helper functions for Edmonds Blossom Implementation based on https://codeforces.com/blog/entry/92339
inline __device__ void queue_insert(
        const int Q_size, int &Q_front, int &Q_back, int* Q, const int element)
{
    if (Q_back == Q_size-1)
    {
        printf("ERROR: QUEUE OVERFLOW - INCREASE SIZE\n");
    } else
    {
        if (Q_front == INVALID)
        {
            Q_front = 0;
        }
        if (Q_back == INVALID)
        {
            Q_back = 0;
        } else
        {
            Q_back += 1;
        }
        Q[Q_back] = element;
    }
}

inline __device__ void queue_pop(
        int &Q_front, const int Q_back)
{
    if (Q_front == INVALID || Q_front > Q_back)
    {
        printf("WARN: QUEUE UNDERFLOW\n");
    } else
    {
        ++Q_front;
    }

}

inline __device__ void add_edge(
        const int u, const int v, int* g)
{
    g[u*M+v] = u;
    g[v*M+u] = v;
}

inline __device__ void match(
        const int u, const int v, int* g, int* mate)
{
    g[u*M+v] = INVALID;
    g[v*M+u] = INVALID;
    mate[u] = v;
    mate[v] = u;
}

//Note: x should not be changed outside the function!
inline __device__ void trace(
        int x, const int* bl, const int* p, int* vx, int &vx_length)
{
    while(true)
    {
        while(bl[x] != x) x = bl[x];
        if(vx_length > 0 && vx[vx_length - 1] == x) break;
        vx[vx_length] = x;
        ++vx_length;
        x = p[x];
    }
}

__device__ void contract(
        const int c, int x, int y, int* vx, int &vx_length, int* vy,
        int &vy_length, int* b, int* bIndex, int* bl, int* g)
{
    bIndex[c] = 0;
    int r = vx[vx_length - 1];
    while(vx_length > 0 && vy_length > 0 && vx[vx_length - 1] == vy[vy_length - 1])
    {
        r = vx[vx_length - 1];
        --vx_length;
        --vy_length;
    }
    // b[c].push_back(r);
    b[c * M + bIndex[c]] = r;
    ++bIndex[c];
    
    // b[c].insert(b[c].end(), vx.rbegin(), vx.rend());
    for (int i = vx_length - 1; i >= 0; --i) {
        b[c * M + bIndex[c]] = vx[i];
        ++bIndex[c]; 
    }
    
    // b[c].insert(b[c].end(), vy.begin(), vy.end());
    for (int i = 0; i < vy_length; ++i)
    {
        b[c * M + bIndex[c]] = vy[i];
        ++bIndex[c];
    }

    for(int i = 0; i <= c; ++i)
    {
        g[c*M+i] = INVALID;
        g[i*M+c] = INVALID;
    }

    for (int j = 0; j < bIndex[c]; ++j)
    {
        int z = b[c * M + j];
        bl[z] = c;
        for(int i = 0; i < c; ++i)
        {
            if(g[z*M+i] != INVALID) 
            {
                g[c*M+i] = z;
                g[i*M+c] = g[i*M+z];
            }
        }
    }
}

__device__ void lift(
        const int n, const int* g, const int* b, const int* bIndex, int* vx,
        int &vx_length, int* A, int &A_length)
{
    while (vx_length >= 2)
    {
        int z = vx[vx_length-1];
        --vx_length;
        if (z < n)
        {
            A[A_length] = z;
            ++A_length;
            continue;
        }
        int w = vx[vx_length-1];
        int i = 0;
        if (A_length % 2 == 0)
        {
            //Find index of g[z][w] within b[z]
            int val = g[z*M+w];
            for (int bId = 0; bId < bIndex[z]; ++bId)
            {
                if (b[z*M+bId] == val)
                {
                    i = bId;
                    break;
                }
            }
        }
        int j = 0;
        if (A_length % 2 == 1)
        {
            //Find index of g[z][A.back()] within b[z]
            int val = g[z*M+A[A_length-1]];
            for (int bId = 0; bId < bIndex[z]; ++bId)
            {
                if (b[z*M+bId] == val)
                {
                    j = bId;
                    break;
                }
            }
        }
        int k = bIndex[z];
        int dif = (A_length % 2 == 0 ? i%2 == 1 : j%2 == 0) ? 1 : k-1;

        while(i != j)
        {
            vx[vx_length] = b[z*M+i];
            ++vx_length;
            i = (i + dif) % k;
        }
        vx[vx_length] = b[z*M+i];
        ++vx_length;
    }
}

///End of helper functions for Edmonds Blossom Implementation based on https://codeforces.com/blog/entry/92339

//Sort 
inline __device__ void sort_array(int* input_array, int& num_elements)
{
    if (num_elements > 1)
    {
        for (int ix = 1; ix < num_elements; ++ix)
        {
            for (int jx = 0; jx < num_elements-1; ++jx)
            {
                if (input_array[jx] > input_array[jx+1])
                {
                    int val = input_array[jx];
                    input_array[jx] = input_array[jx+1];
                    input_array[jx+1] = val;
                }
            }
        }
    }
}

//remove duplicates from a sorted array
inline __device__ void remove_duplicates(int* input_array, int& num_elements)
{
    if (num_elements > 1)
    {
        for (int i = 0; i < num_elements; ++i)
        {
            for (int j=0; j < i; ++j)
            {
                if (input_array[i] == input_array[j])
                {
                    --num_elements;
                    for (int k=i; k < num_elements; ++k)
                    {
                        input_array[k] = input_array[k+1];
                    }
                    --i;
                }
            }
        }
    }
}

//Ensure flops in subSlice share the same set of ctrl signals
inline __device__ bool ffs_ctrl_match(
    const int* flat_node2pin_start_map, const int* flat_node2pin_map, 
    const int* pin_typeIds, const int* pin2net_map,
    const int ffInst, const int offInst)
{
    if (ffInst == INVALID || offInst == INVALID)
    {
        return true;
    }

    int ff_ctrl[10], off_ctrl[10];
    //Initialize ctrls to INVALID
    for (int sg = 0; sg < 10; ++sg)
    {
        ff_ctrl[sg] = INVALID;
        off_ctrl[sg] = INVALID;
    }

    int ff_pins[10], off_pins[10];
    int ffpIdx(0), offpIdx(0);

    int elIt = flat_node2pin_start_map[ffInst];
    int elEnd = flat_node2pin_start_map[ffInst+1];

    for (int el = elIt; el < elEnd; ++el)
    {
        //Skip if not an input or output pin
        int pinType = pin_typeIds[flat_node2pin_map[el]];
        if (pinType < 3 || pinType > 9) continue;

        int netId = pin2net_map[flat_node2pin_map[el]];
        ff_ctrl[pinType] = netId;
        ff_pins[ffpIdx] = pinType;
        ++ffpIdx;
    }

    if (ffpIdx == 0)
    {
        return true;
    }
    
    elIt = flat_node2pin_start_map[offInst];
    elEnd = flat_node2pin_start_map[offInst+1];

    for (int el = elIt; el < elEnd; ++el)
    {
        //Skip if not an input or output pin
        int pinType = pin_typeIds[flat_node2pin_map[el]];
        if (pinType < 3 || pinType > 9) continue;

        int netId = pin2net_map[flat_node2pin_map[el]];
        off_ctrl[pinType] = netId;
        off_pins[offpIdx] = pinType;
        ++offpIdx;
    }

    if (offpIdx == 0)
    {
        return true;
    }
    
    //Sort contents
    sort_array(ff_pins, ffpIdx);
    sort_array(off_pins, offpIdx);

    int idxA = 0, idxB = 0;
    int pinTypeA = ff_pins[idxA];
    int pinTypeB = off_pins[idxB];

    //Only compare if pinType matches
    while (idxA < ffpIdx && idxB < offpIdx)
    {
        if (pinTypeA < pinTypeB)
        {
            ++idxA;

            if (idxA < ffpIdx)
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

            if (idxB < offpIdx)
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

            if (idxA < ffpIdx && idxB < offpIdx)
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
inline __device__ bool subSlice_compatibility(
        const int* node2outpinIdx_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map,
        const int* pin_typeIds, const int* node2fence_region_map,
        const int* res_ff, const int* res_lut, const int lutId,
        const int SLICE_CAPACITY, const int BLE_CAPACITY,
        const int MAX_INPUTS_IN_SUBSLICE, const int MAX_LOOPBACK_IN_SUBSLICE,
        const int k, const int ssInstId)
{
    ////DBG
    //char printMsg = 0;    
    ////DBG

    int ssId = int(k/2)*2;
    int subSliceElements[8];
    int numSSEls = 0;

    if (res_lut[ssId] != INVALID)
    {
        subSliceElements[numSSEls] = res_lut[ssId];
        ++numSSEls;

        ////DBG
        //if (printMsg == 0 && (res_lut[ssId] == 11846 || res_lut[ssId] == 11848))
        //{
        //    printMsg = 1;
        //}
        ////DBG
    }

    if (res_ff[ssId] != INVALID)
    {
        subSliceElements[numSSEls] = res_ff[ssId];
        ++numSSEls;

        ////DBG
        //if (res_ff[ssId] == 73994 || res_ff[ssId] == 73995)
        //{
        //    printMsg = 1;
        //}
        ////DBG
    }

    if (res_lut[ssId+1] != INVALID)
    {
        subSliceElements[numSSEls] = res_lut[ssId+1];
        ++numSSEls;

        ////DBG
        //if (printMsg == 0 && (res_lut[ssId+1] == 11846 || res_lut[ssId+1] == 11848))
        //{
        //    printMsg = 1;
        //}
        ////DBG
    }

    if (res_ff[ssId+1] != INVALID)
    {
        subSliceElements[numSSEls] = res_ff[ssId+1];
        ++numSSEls;

        ////DBG
        //if (printMsg == 0 && (res_ff[ssId+1] == 73994 || res_ff[ssId+1] == 73995))
        //{
        //    printMsg = 1;
        //}
        ////DBG
    }

    //Check the new inst for compatibility
    if (ssInstId != INVALID)
    {
        subSliceElements[numSSEls] = ssInstId;
        ++numSSEls;

        int lut_type = (node2fence_region_map[ssInstId] == lutId);
        int loc_avail = lut_type ? res_lut[k] == INVALID : res_ff[k] == INVALID;
        if (loc_avail == 0)
        {
            return false;
        }

        if (lut_type == 0 && 
                (res_ff[ssId] != INVALID || res_ff[ssId+1] != INVALID))
        {
            int ffA = (res_ff[ssId] != INVALID) ? res_ff[ssId] : res_ff[ssId + 1];
            if(!ffs_ctrl_match(flat_node2pin_start_map, flat_node2pin_map, 
                        pin_typeIds, pin2net_map, ffA, ssInstId))
            {
                return false;
            }
        }
    }

    if (numSSEls > 2*BLE_CAPACITY)
    {
        return false;
    }

    ////DBG
    //if (printMsg == 0 && (ssInstId == 73994 || ssInstId == 73995 ||
    //    ssInstId == 11846 || ssInstId == 11848))
    //{
    //    printMsg = 1;
    //}
    ////DBG

    int all_inNets[MAX_SLICE_INPUTS];
    int num_all_inNets(0);
    //Check if LUT is driving FF in same subSlice
    int lut_ff_conns = 0;
    int lut_outNets[4];
    int num_lut_outNets = 0;
    int ff_inNets[8];
    int num_ff_inNets = 0;

    for (int elId = 0; elId < numSSEls; ++elId)
    {
        int instId = subSliceElements[elId];

        int lut_inst = (node2fence_region_map[instId] == lutId);

        int elIt = flat_node2pin_start_map[instId];
        int elEnd = flat_node2pin_start_map[instId+1];

        for (int el = elIt; el < elEnd; ++el)
        {
            //Skip if not an input pin
            int pinType = pin_typeIds[flat_node2pin_map[el]];

            if (lut_inst == 1 && pinType == 0)
            {
                lut_outNets[num_lut_outNets] = pin2net_map[flat_node2pin_map[el]];
                ++num_lut_outNets;
            }
            if (pinType != INPUT_PIN) continue;

            int netId = pin2net_map[flat_node2pin_map[el]];

            all_inNets[num_all_inNets] = netId;
            ++num_all_inNets;

            if (lut_inst == 0)
            {
                ff_inNets[num_ff_inNets] = netId;
                ++num_ff_inNets;
            }
        }
    }

    if (num_lut_outNets > 0 && num_ff_inNets > 0)
    {
        sort_array(lut_outNets, num_lut_outNets);
        remove_duplicates(lut_outNets, num_lut_outNets);

        sort_array(ff_inNets, num_ff_inNets);
        remove_duplicates(ff_inNets, num_ff_inNets);

        int idxIn = 0, idxOut = 0;
        int netIn = ff_inNets[idxIn];
        int netOut = lut_outNets[idxOut];

        while (true)
        {
            if (netIn < netOut)
            {
                ++idxIn;
                if (idxIn < num_ff_inNets)
                {
                    netIn = ff_inNets[idxIn];
                } else
                {
                    break;
                }
            } else if (netIn > netOut)
            {
                ++idxOut;
                if (idxOut < num_lut_outNets)
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

    sort_array(all_inNets, num_all_inNets);
    remove_duplicates(all_inNets, num_all_inNets);

    ////DBG
    //if (printMsg == 1)
    //{
    //    printf("%d insts in ALM: ", numSSEls);
    //    for (int elId = 0; elId < numSSEls; ++elId)
    //    {
    //        printf("%d ",subSliceElements[elId]);
    //    }

    //    printf(" have %d unique inputs\n", num_all_inNets);
    //}
    ////DBG

    if (num_all_inNets > MAX_INPUTS_IN_SUBSLICE)
    {
        return false;
    }

    //Loopbacks from subSlice driving Slice instances
    //Get input nets from other subSlices
    for (int sg = 0; sg < SLICE_CAPACITY; sg += BLE_CAPACITY)
    {
        //Skip already visited subSlice
        if (sg == ssId) continue;

        int subSlice_insts[8];
        int num_subSlice_insts = 0;

        //FFs
        if (res_ff[sg] != INVALID)
        {
            subSlice_insts[num_subSlice_insts] = res_ff[sg];
            ++num_subSlice_insts;
        }
        if (res_ff[sg+1] != INVALID)
        {
            subSlice_insts[num_subSlice_insts] = res_ff[sg+1];
            ++num_subSlice_insts;
        }

        //LUTs
        if (res_lut[sg] != INVALID)
        {
            subSlice_insts[num_subSlice_insts] = res_lut[sg];
            ++num_subSlice_insts;
        }
        if (res_lut[sg+1] != INVALID)
        {
            subSlice_insts[num_subSlice_insts] = res_lut[sg+1];
            ++num_subSlice_insts;
        }

        //Get input nets
        for (int el = 0; el < num_subSlice_insts; ++el)
        {
            int instId = subSlice_insts[el];
            int pStart = flat_node2pin_start_map[instId];
            int pEnd = flat_node2pin_start_map[instId+1];

            for (int pId = pStart; pId < pEnd; ++pId)
            {
                //Skip if not an input pin
                int pinType = pin_typeIds[flat_node2pin_map[pId]];
                if (pinType != INPUT_PIN) continue;

                all_inNets[num_all_inNets] = pin2net_map[flat_node2pin_map[pId]];
                ++num_all_inNets;
            }
        }
    }

    sort_array(all_inNets, num_all_inNets);
    remove_duplicates(all_inNets, num_all_inNets);

    if (num_all_inNets == 0)
    {
        return true;
    }

    //Get nets from all subSlices
    for (int sg = 0; sg < SLICE_CAPACITY; sg += BLE_CAPACITY)
    {
        int subSlice_insts[8];
        int num_subSlice_insts(0);

        int subSlice_outNets[8];
        int num_subSlice_outNets(0);

        if (sg == ssId)
        {
            for (int elId = 0; elId < numSSEls; ++elId)
            {
                subSlice_insts[num_subSlice_insts] = subSliceElements[elId];
                ++num_subSlice_insts;
            }
        } else
        {
            //FFs
            if (res_ff[sg] != INVALID)
            {
                subSlice_insts[num_subSlice_insts] = res_ff[sg];
                ++num_subSlice_insts;
            }
            if (res_ff[sg+1] != INVALID)
            {
                subSlice_insts[num_subSlice_insts] = res_ff[sg+1];
                ++num_subSlice_insts;
            }

            //LUTs
            if (res_lut[sg] != INVALID)
            {
                subSlice_insts[num_subSlice_insts] = res_lut[sg];
                ++num_subSlice_insts;
            }
            if (res_lut[sg+1] != INVALID)
            {
                subSlice_insts[num_subSlice_insts] = res_lut[sg+1];
                ++num_subSlice_insts;
            }
        }

        for (int idx = 0; idx < num_subSlice_insts; ++idx)
        {
            int instId = subSlice_insts[idx];

            int ndOutId = 4*instId;
            int ndOutPins = ndOutId + 4;
            for (int nodeOutId = ndOutId; nodeOutId < ndOutPins; ++nodeOutId)
            {
                int outPinId = node2outpinIdx_map[nodeOutId];
                if (outPinId == INVALID) continue;

                int outNetId = pin2net_map[outPinId];
                subSlice_outNets[num_subSlice_outNets] = outNetId;
                ++num_subSlice_outNets;
            }
        }
        if (num_subSlice_outNets <= MAX_LOOPBACK_IN_SUBSLICE) continue;

        sort_array(subSlice_outNets, num_subSlice_outNets);
        remove_duplicates(subSlice_outNets, num_subSlice_outNets);

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
                if (idxIn < num_all_inNets)
                {
                    netIn = all_inNets[idxIn];
                } else
                {
                    break;
                }
            } else if (netIn > netOut)
            {
                ++idxOut;
                if (idxOut < num_subSlice_outNets)
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
                if (idxIn < num_all_inNets &&
                        idxOut < num_subSlice_outNets)
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

//two lut compatibility
inline __device__ bool two_lut_compatibility_check(
        const int* lut_type, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map, const int* pin_typeIds,
        const int lutTypeInSliceUnit, const int lut_maxShared, const int lutAId,
        const int lutBId)
{
    if (lut_type[lutAId] == lutTypeInSliceUnit || 
            lut_type[lutBId] == lutTypeInSliceUnit)
    {
        return false;
    }

    int numInputs = lut_type[lutAId] + lut_type[lutBId];

    if (numInputs <= lut_maxShared)
    {
        return true;
    }

    //Include condition for LUT0
    if (lut_type[lutAId] == 0 || lut_type[lutBId] == 0)
    {
        return false;
    }

    int lutANets[SLICE_MAX_CAP], lutBNets[SLICE_MAX_CAP];
    int lutAIdx(0), lutBIdx(0);

    int lutAIt = flat_node2pin_start_map[lutAId];
    int lutBIt = flat_node2pin_start_map[lutBId];
    int lutAEnd = flat_node2pin_start_map[lutAId+1];
    int lutBEnd = flat_node2pin_start_map[lutBId+1];

    for (int el = lutAIt; el < lutAEnd; ++el)
    {
        //Skip if not an input pin
        if (pin_typeIds[flat_node2pin_map[el]] != INPUT_PIN) continue;

        int netId = pin2net_map[flat_node2pin_map[el]];
        lutANets[lutAIdx] = netId;
        ++lutAIdx;
    }

    if (lutAIdx > 1)
    {
        //Sort contents of lutANets
        for (int ix = 1; ix < lutAIdx; ++ix)
        {
            for (int jx = 0; jx < lutAIdx-1; ++jx)
            {
                if (lutANets[jx] > lutANets[jx+1])
                {
                    int val = lutANets[jx];
                    lutANets[jx] = lutANets[jx+1];
                    lutANets[jx+1] = val;
                }
            }
        }
    }

    for (int el = lutBIt; el < lutBEnd; ++el)
    {
        //Skip if not an input pin
        if (pin_typeIds[flat_node2pin_map[el]] != INPUT_PIN) continue;

        int netId = pin2net_map[flat_node2pin_map[el]];
        lutBNets[lutBIdx] = netId;
        ++lutBIdx;
    }

    if (lutBIdx > 1)
    {
        //Sort contents of lutBNets
        for (int ix = 1; ix < lutBIdx; ++ix)
        {
            for (int jx = 0; jx < lutBIdx-1; ++jx)
            {
                if (lutBNets[jx] > lutBNets[jx+1])
                {
                    int val = lutBNets[jx];
                    lutBNets[jx] = lutBNets[jx+1];
                    lutBNets[jx+1] = val;
                }
            }
        }
    }

    int idxA = 0, idxB = 0;
    int netIdA = lutANets[idxA];
    int netIdB = lutBNets[idxB];

    while(numInputs > lut_maxShared)
    {
        if (netIdA < netIdB)
        {
            ++idxA;
            if (idxA < lutAIdx)
            {
                netIdA = lutANets[idxA];
            } else
            {
                break;
            }
        } else if (netIdA > netIdB)
        {
            ++idxB;
            if (idxB < lutBIdx)
            {
                netIdB = lutBNets[idxB];
            } else
            {
                break;
            }

        } else
        {
            --numInputs;
            ++idxA;
            ++idxB;

            if (idxA < lutAIdx && idxB < lutBIdx)
            {
                netIdA = lutANets[idxA];
                netIdB = lutBNets[idxB];
            } else
            {
                break;
            }
        }
    }

    return numInputs <= lut_maxShared;
}

//Given lut arrangement, fit FFs
inline __device__ bool fit_ffs(
        const int* node2outpinIdx_map, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* pin2net_map,
        const int* pin_typeIds, const int* node2fence_region_map,
        const int* res_lut, const int lutId, const int lut_maxShared,
        const int SLICE_CAPACITY, const int BLE_CAPACITY, int* res_ff)
{
    //Rearrange all FFs based on compatibility
    int temp_ff[SLICE_MAX_CAP];
    int rem_ffs[SLICE_MAX_CAP];
    int num_rem_ffs(0);

    for (int sg = 0; sg < SLICE_CAPACITY; sg += BLE_CAPACITY)
    {
        temp_ff[sg] = res_ff[sg];
        temp_ff[sg+1] = res_ff[sg+1];

        if (res_ff[sg] != INVALID || res_ff[sg+1] != INVALID)
        {
            if (!subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map,
                        flat_node2pin_map, pin2net_map, pin_typeIds,
                        node2fence_region_map, res_ff, res_lut, lutId,
                        SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared,
                        BLE_CAPACITY, sg, INVALID))
            {
                if (res_ff[sg] != INVALID)
                {
                    rem_ffs[num_rem_ffs] = res_ff[sg];
                    ++num_rem_ffs;
                    res_ff[sg] = INVALID;
                }
                if (res_ff[sg+1] != INVALID)
                {
                    rem_ffs[num_rem_ffs] = res_ff[sg+1];
                    ++num_rem_ffs;
                    res_ff[sg+1] = INVALID;
                }
            }
        }
    }

    if (num_rem_ffs == 0) return true;

    //Greedily assign remaining FFs
    char ffLocFound = 0;
    for (int el = 0; el < num_rem_ffs; ++el)
    {
        int ffId = rem_ffs[el];
        for (int sg = 0; sg < SLICE_CAPACITY; sg += BLE_CAPACITY)
        {
            if (res_ff[sg] == INVALID)
            {
                if (subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map,
                            flat_node2pin_map, pin2net_map, pin_typeIds,
                            node2fence_region_map, res_ff, res_lut, lutId,
                            SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared,
                            BLE_CAPACITY, sg, ffId))
                {
                    res_ff[sg] = ffId;
                    ++ffLocFound;
                    break;
                }
            } else if (res_ff[sg+1] == INVALID)
            {
                if (subSlice_compatibility(node2outpinIdx_map, flat_node2pin_start_map,
                            flat_node2pin_map, pin2net_map, pin_typeIds,
                            node2fence_region_map, res_ff, res_lut, lutId,
                            SLICE_CAPACITY, BLE_CAPACITY, lut_maxShared,
                            BLE_CAPACITY, sg+1, ffId))
                {
                    res_ff[sg+1] = ffId;
                    ++ffLocFound;
                    break;
                }
            }
        }
    }

    if (ffLocFound == num_rem_ffs)
    {
        return true;
    }

    //Revert
    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
    {
        res_ff[sg] = temp_ff[sg];
    }

    return false;
}

//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

inline __device__ bool fit_luts_to_candidate_impl(
        const int* node2outpinIdx_map, const int* lut_type, const int* pin2net_map,
        const int* pin_typeIds, const int* flat_node2pin_start_map,
        const int* flat_node2pin_map, const int* flat_node2precluster_map,
        const int* node2fence_region_map, const int* special_nodes,
        const int half_ctrl_mode, const int lutTypeInSliceUnit, const int lut_maxShared,
        const int instPcl, const int node2prclstrCount, const int NUM_BLE_PER_SLICE,
        const int SLICE_CAPACITY, const int BLE_CAPACITY, const int lutId,
        int* res_lut, int* res_ff)
{
    int luts[N], lut6s[N], splNodes[N];
    int lutIdx(0), lut6Idx(0), splIdx(0);

    //Ensure subSlice-level shared input count is met
    int temp_lut[SLICE_MAX_CAP];
    for (int sg = 0; sg < SLICE_CAPACITY; ++sg)
    {
        if (res_lut[sg] != INVALID)
        {
            if (special_nodes[res_lut[sg]] == 1)
            {
                splNodes[splIdx] = res_lut[sg];
                ++splIdx;
            } else
            {
                if (lut_type[res_lut[sg]] < lutTypeInSliceUnit)
                {
                    luts[lutIdx] = res_lut[sg];
                    ++lutIdx;
                } else
                {
                    lut6s[lut6Idx] = res_lut[sg];
                    ++lut6Idx;
                }
            }
        }
        if (half_ctrl_mode == 0)
        {
            temp_lut[sg] = res_lut[sg];
        }
    }

    //int lutSize = lutIdx + lut6Idx;
    for (int idx = 0; idx < node2prclstrCount; ++idx)
    {
        int clInstId = flat_node2precluster_map[instPcl + idx];
        if (node2fence_region_map[clInstId] == lutId)
        {
            if (lut_type[clInstId] < lutTypeInSliceUnit)
            {
                luts[lutIdx] = clInstId;
                ++lutIdx;

                sort_array(luts, lutIdx);
                remove_duplicates(luts, lutIdx);
            } else
            {
                lut6s[lut6Idx] = clInstId;
                ++lut6Idx;

                sort_array(lut6s, lut6Idx);
                remove_duplicates(lut6s, lut6Idx);
            }
        }
    }

    int splNodeSpace = splIdx;
    splNodeSpace += (splIdx & 1) ? 1 : 0;

    //graph matching can be called even if res_lut if full!
    //Guard band for graph matching implementation with fixed memory
    if (lutIdx + 2*lut6Idx + splNodeSpace > SLICE_CAPACITY)
    {
        return false;
    }

    ///Edmonds Blossom Implementation based on https://codeforces.com/blog/entry/92339
    int n = lutIdx; //n - #vertices
    //int m = (n%2 == 0) ? 3*n/2: 3*(n+1)/2; //m = 3n/2

    int mate[N]; //array of length n; For each vertex u, if exposed mate[u] = -1 or mate[u] = u
    int b[M2]; //For each blossom u, b[u] is list of all vertices contracted from u
    int bIndex[M];
    int p[M]; //array of length m; For each vertex/blossom u, p[u] is parent in the search forest
    int d[M]; //array of length m; For each vertex u, d[u] is status in search forest. d[u] = 0 if unvisited, d[u] = 1 is even depth from root and d[u] = 2 is odd depth from root
    int bl[M]; //array of length m; For each vertex/blossom u, bl[u] is the blossom containing u. If not contracted, bl[u] = u. 
    int g[M2]; //table of size mxm with information of unmatched edges.g[u][v] = -1 if no unmatched vertices; g[u][v] = u, if u is a vertex.

    //Initialize mate
    for (int mId = 0; mId < n; ++mId)
    {
        mate[mId] = INVALID;
    }
    for (int gId = 0; gId < M2; ++gId)
    {
        g[gId] = INVALID;
    }

    //Create graph with luts
    for(int ll = 0; ll < lutIdx; ++ll)
    {
        for(int rl = ll+1; rl < lutIdx; ++rl)
        {
            if (two_lut_compatibility_check(lut_type, flat_node2pin_start_map,
                        flat_node2pin_map, pin2net_map, pin_typeIds,
                        lutTypeInSliceUnit, lut_maxShared, luts[ll], luts[rl]))
            {
                add_edge(ll, rl, g);
            }
        }
    }

    int totalPairs(0);

    for (int ans = 0; ; ++ans)
    {
        for (int dId = 0; dId < M; ++dId)
        {
            d[dId] = 0;
        }

        int Q[NN];
        int Q_size(NN);
        int Q_front(INVALID), Q_back(INVALID);

        for (int i = 0; i < M; ++i)
        {
            bl[i] = i;
        }
        for (int i = 0; i < n; ++i)
        {
            if (mate[i] == INVALID)
            {
                queue_insert(Q_size, Q_front, Q_back, Q, i);
                p[i] = i;
                d[i] = 1;
            }
        }

        int c = N;
        bool aug(false);

        while ((Q_front != INVALID && Q_front <= Q_back) && !aug)
        {
            int x = Q[Q_front];
            //queue_pop(Q_front, Q_back, Q);
            queue_pop(Q_front, Q_back);

            if (bl[x] != x) continue;

            for (int y = 0; y < c; ++y)
            {
                if (bl[y] == y && g[x*M+y] != INVALID)
                {
                    if (d[y] == 0)
                    {
                        p[y] = x;
                        d[y] = 2;
                        p[mate[y]] = y;
                        d[mate[y]] = 1;
                        queue_insert(Q_size, Q_front, Q_back, Q, mate[y]);
                    } else if (d[y] == 1)
                    {
                        int vx[2*M], vy[2*M];
                        int vx_length = 0, vy_length = 0;
                        trace(x, bl, p, vx, vx_length);
                        trace(y, bl, p, vy, vy_length);

                        if (vx[vx_length-1] == vy[vy_length-1])
                        {
                            contract(c, x, y, vx, vx_length, vy, vy_length, b, bIndex, bl, g);
                            queue_insert(Q_size, Q_front, Q_back, Q, c);
                            p[c] = p[b[c*M]];
                            d[c] = 1;
                            ++c;
                        } else
                        {
                            aug = true;
                            int new_vx[2*M], new_vy[2*M];
                            new_vx[0] = y;
                            for (int idx = 0; idx < vx_length; ++idx)
                            {
                                new_vx[idx+1] = vx[idx];
                            }
                            ++vx_length;
                            new_vy[0] = x;
                            for (int idx = 0; idx < vy_length; ++idx)
                            {
                                new_vy[idx+1] = vy[idx];
                            }
                            ++vy_length;

                            int A[4*M], B[2*M];
                            int A_length = 0, B_length = 0;

                            lift(n, g, b, bIndex, new_vx, vx_length, A, A_length);
                            lift(n, g, b, bIndex, new_vy, vy_length, B, B_length);

                            for (int idx = B_length-1; idx >= 0; --idx)
                            {
                                A[A_length] = B[idx];
                                ++A_length;
                            }

                            for (int i = 0; i < A_length; i += 2)
                            {
                                match(A[i], A[i+1], g, mate);
                                if (i + 2 < A_length)
                                {
                                    add_edge(A[i+1], A[i + 2], g);
                                }
                            }
                        }
                        break;
                    }
                }
            }
        }
        if (!aug)
        {
            totalPairs = ans;
            break;
        }
    }

    int otherNodePairs = lut6Idx + splNodeSpace/2;

    if ((lutIdx - totalPairs + otherNodePairs) > NUM_BLE_PER_SLICE)
    {
        return false;
    }

    int idxL = 0;

    if (splIdx > 0)
    {
        for (int spId = 0; spId < splIdx; ++spId)
        {
            res_lut[idxL] = splNodes[spId];
            ++idxL;
        }
        if (splNodeSpace > splIdx)
        {
            res_lut[idxL] = INVALID;
            ++idxL;
        }
    }

    for (int iil = 0; iil < lut6Idx; ++iil)
    {
        res_lut[idxL] = lut6s[iil];
        res_lut[idxL + 1] = INVALID;
        idxL += BLE_CAPACITY;
    }

    for (int mId = 0; mId < n; ++mId)
    {
        if (mate[mId] == INVALID)
        {
            res_lut[idxL] = luts[mId];
            res_lut[idxL + 1] = INVALID;
            idxL += BLE_CAPACITY;
        }
    }

    int ck[N] = {0};
    for (int mId = 0; mId < n; ++mId)
    {
        if (mate[mId] != INVALID && ck[mId] == 0 && ck[mate[mId]] == 0)
        {
            ++ck[mId];
            ++ck[mate[mId]];

            res_lut[idxL] = luts[mId];
            res_lut[idxL + 1] = luts[mate[mId]];
            idxL += BLE_CAPACITY;
        }
    }
    for (int lIdx = idxL; lIdx < SLICE_CAPACITY; ++lIdx)
    {
        res_lut[lIdx] = INVALID;
    }

    //Ensure subSlice-level shared input count is met
    if (half_ctrl_mode == 0)
    {
        //Try to rearrange ffs to avoid compatibility issues
        if (fit_ffs(node2outpinIdx_map, flat_node2pin_start_map,
                flat_node2pin_map, pin2net_map, pin_typeIds,
                node2fence_region_map, res_lut, lutId, lut_maxShared,
                SLICE_CAPACITY, BLE_CAPACITY, res_ff))
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

DREAMPLACE_END_NAMESPACE

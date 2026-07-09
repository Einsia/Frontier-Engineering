/**
 * @file   sortNode2Pin.cpp
 * @author Rachel Selina (DREAMPlaceFPGA-PL)
 * @date   Nov 2021
 * @brief  sort node2pin
 */

#include <stdlib.h>
#include <stdio.h>
#include <time.h>
#include <random>
#include <assert.h>
#include <chrono>
#include <cmath>
#include <thrust/sort.h>

#include "utility/src/utils.cuh"
#include "utility/src/limits.h"

DREAMPLACE_BEGIN_NAMESPACE

__global__ void computeSortNode2Pin(
        const int *flat_node2pin_start_map,
        int *flat_node2pin_map, 
        const int *sorted_pin_map, 
        const int num_nodes, 
        int *out 
        )
{
    const int i = threadIdx.x + blockDim.x * blockIdx.x;
    if (i < num_nodes)
    {
        int beg = flat_node2pin_start_map[i];
        int end = flat_node2pin_start_map[i+1];

        //Sort
        for (int ix = beg+1; ix < end; ++ix)
        {
            for (int jx = beg; jx < end-1; ++jx)
            {
                if (sorted_pin_map[flat_node2pin_map[jx]] > sorted_pin_map[flat_node2pin_map[jx+1]])
                {
                    int val = flat_node2pin_map[jx];
                    flat_node2pin_map[jx] = flat_node2pin_map[jx+1];
                    flat_node2pin_map[jx+1] = val;
                }
            }
        }
        //Sort

        out[i] = sorted_pin_map[flat_node2pin_map[beg]];
    }
}

int computeSortNode2PinCudaLauncher(
        const int *flat_node2pin_start_map,
        int *flat_node2pin_map, 
        const int *sorted_pin_map, 
        const int num_nodes, 
        int *out 
        )
{
    int thread_count = 512;
    int block_count = ceilDiv(num_nodes, thread_count);

    computeSortNode2Pin<<<block_count, thread_count>>>(
            flat_node2pin_start_map,
            flat_node2pin_map,
            sorted_pin_map,
            num_nodes,
            out 
            );

    return 0;
}

// manually instantiate the template function
#define REGISTER_KERNEL_LAUNCHER()                                              \
    template int computeSortNode2PinCudaLauncher()                              \
        (const int *flat_node2pin_start_map, int *flat_node2pin_map,            \
        const int *sorted_pin_map, const int num_nodes, int *out );

DREAMPLACE_END_NAMESPACE

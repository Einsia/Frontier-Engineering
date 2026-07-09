/**
 * @file   integrate_net_weights_cuda_kernel.cu
 * @author Yibo Lin (DREAMPlace)
 * @date   Jul 2019
 */

#include <cfloat>
#include <stdio.h>
#include "assert.h"
#include "cuda_runtime.h"
#include "utility/src/utils.cuh"
#include "weighted_average_wirelength/src/functional_cuda.h"

DREAMPLACE_BEGIN_NAMESPACE

template <typename T>
__global__ void integrateNetWeights(
        const int* pin2net_map, 
        const unsigned char* net_mask, 
        const T* net_weights, 
        const T* net_weights_x, 
        T* grad_x_tensor, T* grad_y_tensor, 
        int num_pins
        )
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < num_pins)
    {
        int net_id = pin2net_map[i]; 
        T weight = net_weights[net_id]; 
        T weight_x = net_weights_x[net_id]; 
        if (net_id >= 0 && net_mask[net_id])
        {
            grad_x_tensor[i] *= weight_x; 
            grad_y_tensor[i] *= weight; 
        }
    }
}

template <typename T>
void integrateNetWeightsCudaLauncher(
        const int* pin2net_map, 
        const unsigned char* net_mask, 
        const T* net_weights, 
        const T* net_weights_x, 
        T* grad_x_tensor, T* grad_y_tensor, 
        int num_pins
        )
{
    integrateNetWeights<<<ceilDiv(num_pins, 256), 256>>>(pin2net_map, net_mask, net_weights, net_weights_x, grad_x_tensor, grad_y_tensor, num_pins); 
}

#define REGISTER_KERNEL_LAUNCHER(T) \
    template void integrateNetWeightsCudaLauncher<T>(\
            const int* pin2net_map, \
            const unsigned char* net_mask, \
            const T* net_weights, \
            const T* net_weights_x, \
            T* grad_x_tensor, T* grad_y_tensor, \
            int num_pins\
            );

REGISTER_KERNEL_LAUNCHER(float);
REGISTER_KERNEL_LAUNCHER(double);

DREAMPLACE_END_NAMESPACE

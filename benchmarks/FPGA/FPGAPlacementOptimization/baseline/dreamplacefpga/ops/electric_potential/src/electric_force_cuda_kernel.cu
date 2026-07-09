/**
 * @file   electric_force_cuda_kernel.cu
 * @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
 * @date   Oct 2020
 */
#include <float.h>
#include <math.h>
#include <stdio.h>
#include "cuda_runtime.h"
#include "utility/src/utils.cuh"
// local dependency
#include "electric_potential/src/density_function.h"

DREAMPLACE_BEGIN_NAMESPACE

/// define fpga_density_function
template <typename T>
inline __device__ DEFINE_FPGA_DENSITY_FUNCTION(T);

template <typename T>
__global__ void __launch_bounds__(1024, 8) computeElectricForceFPGA(
    int num_bins_x, int num_bins_y, const T *field_map_x_tensor,
    const T *field_map_y_tensor, const T *x_tensor, const T *y_tensor,
    const T *node_size_x_clamped_tensor, const T *node_size_y_clamped_tensor,
    const T bin_size_x, const T bin_size_y, const T inv_bin_size_x,
    const T inv_bin_size_y, int num_nodes, T *grad_x_tensor, T *grad_y_tensor,
    const int *sorted_node_map  ///< can be NULL if not sorted
) {
  int index = blockIdx.x * blockDim.z + threadIdx.z;
  if (index < num_nodes) {
    int i = (sorted_node_map) ? sorted_node_map[index] : index;

    // use stretched node size
    T node_size_x = node_size_x_clamped_tensor[i];
    T node_size_y = node_size_y_clamped_tensor[i];
    T node_x = x_tensor[i];
    T node_y = y_tensor[i];

    T bXLo = node_x;
    T bXHi = node_x + node_size_x;
    
    int bin_index_xl = int(bXLo * inv_bin_size_x);
    int bin_index_xh = int((bXHi * inv_bin_size_x));  // exclusive
    bin_index_xl = DREAMPLACE_STD_NAMESPACE::max(bin_index_xl, 0);
    bin_index_xh = DREAMPLACE_STD_NAMESPACE::min(bin_index_xh, num_bins_x -1);

    T bYLo = node_y;
    T bYHi = node_y + node_size_y;

    int bin_index_yl = int(bYLo * inv_bin_size_y);
    int bin_index_yh = int((bYHi * inv_bin_size_y));  // exclusive
    bin_index_yl = DREAMPLACE_STD_NAMESPACE::max(bin_index_yl, 0);
    bin_index_yh = DREAMPLACE_STD_NAMESPACE::min(bin_index_yh, num_bins_y-1);

    // blockDim.x * blockDim.y threads will be used to update one node
    // shared memory is used to privatize the atomic memory access to thread
    // block
    extern __shared__ unsigned char s_xy[];
    T *s_x = (T *)s_xy;
    T *s_y = s_x + blockDim.z;
    if (threadIdx.x == 0 && threadIdx.y == 0) {
      s_x[threadIdx.z] = s_y[threadIdx.z] = 0;
    }
    __syncthreads();

    T tmp_x, tmp_y;
    tmp_x = 0;
    tmp_y = 0;

    // update density potential map
    for (int k = bin_index_xl + threadIdx.y; k <= bin_index_xh;
         k += blockDim.y) {
      T px = fpga_density_function(bXHi, bXLo, k, bin_size_x);

      for (int h = bin_index_yl + threadIdx.x; h <= bin_index_yh;
           h += blockDim.x) {
        T py =
            fpga_density_function(bYHi, bYLo, h, bin_size_y);
        T area = px * py;

        int idx = k * num_bins_y + h;
        tmp_x += area * field_map_x_tensor[idx];
        tmp_y += area * field_map_y_tensor[idx];
      }
    }

    atomicAdd(&s_x[threadIdx.z], tmp_x);
    atomicAdd(&s_y[threadIdx.z], tmp_y);
    __syncthreads();

    if (threadIdx.x == 0 && threadIdx.y == 0) {
      grad_x_tensor[i] = s_x[threadIdx.z];
      grad_y_tensor[i] = s_y[threadIdx.z];
    }
  }
}

template <typename T>
int computeElectricForceFPGACudaLauncher(
    int num_bins_x, int num_bins_y,
    const T *field_map_x_tensor,
    const T *field_map_y_tensor, const T *x_tensor, const T *y_tensor,
    const T *node_size_x_clamped_tensor, const T *node_size_y_clamped_tensor,
    T bin_size_x, T bin_size_y, int num_nodes, T *grad_x_tensor,
    T *grad_y_tensor, const int *sorted_node_map) {
  int thread_count = 64;
  dim3 blockSize(2, 2, thread_count);
  size_t shared_mem_size = sizeof(T) * thread_count * 2;

  int block_count_nodes = (num_nodes + thread_count - 1) / thread_count;
  computeElectricForceFPGA<<<block_count_nodes, blockSize, shared_mem_size>>>(
      num_bins_x, num_bins_y, field_map_x_tensor, field_map_y_tensor, x_tensor,
      y_tensor, node_size_x_clamped_tensor, node_size_y_clamped_tensor,
      bin_size_x, bin_size_y, 1 / bin_size_x, 1 / bin_size_y, num_nodes,
      grad_x_tensor, grad_y_tensor, sorted_node_map);

  return 0;
}

#define REGISTER_KERNEL_LAUNCHER(T)                                             \
  template int computeElectricForceFPGACudaLauncher<T>(                             \
      int num_bins_x, int num_bins_y, const T *field_map_x_tensor,              \
      const T *field_map_y_tensor, const T *x_tensor, const T *y_tensor,        \
      const T *node_size_x_clamped_tensor, const T *node_size_y_clamped_tensor, \
      T bin_size_x, T bin_size_y, int num_nodes, T *grad_x_tensor,              \
       T *grad_y_tensor, const int *sorted_node_map); 

REGISTER_KERNEL_LAUNCHER(float);
REGISTER_KERNEL_LAUNCHER(double);

DREAMPLACE_END_NAMESPACE

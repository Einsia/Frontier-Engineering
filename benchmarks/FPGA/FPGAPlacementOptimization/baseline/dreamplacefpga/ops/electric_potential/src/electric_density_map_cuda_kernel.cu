/**
 * @file   electric_density_map_cuda_kernel.cu
 * @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
 * @date   Oct 2020
 */
#include <float.h>
#include <cstdint>
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

//Added by Rachel
template <typename T, typename AtomicOp>
__global__ void __launch_bounds__(1024, 8) computeFPGADensityMap(
    const T *x_tensor, const T *y_tensor, const T *node_size_x_clamped_tensor,
    const T *node_size_y_clamped_tensor, const T *offset_x_tensor,
    const T *offset_y_tensor, const T *ratio_tensor,
    const int num_nodes, const int num_bins_x, const int num_bins_y, const T xl,
    const T yl, const T xh, const T yh, const T bin_size_x, const T bin_size_y,
    const T inv_bin_size_x, const T inv_bin_size_y, AtomicOp atomicAddOp,
    typename AtomicOp::type *density_map_tensor,
    const int *sorted_node_map,  ///< can be NULL if not sorted
    const T targetHalfSizeX, const T targetHalfSizeY
) {
  int index = blockIdx.x * blockDim.z + threadIdx.z;
  if (index < num_nodes) {
    int i = (sorted_node_map) ? sorted_node_map[index] : index;

    // use stretched node size
    T node_size_x = node_size_x_clamped_tensor[i];
    T node_size_y = node_size_y_clamped_tensor[i];
    T node_x = x_tensor[i] + offset_x_tensor[i];
    T node_y = y_tensor[i] + offset_y_tensor[i];
    T offset_x = offset_x_tensor[i];
    T offset_y = offset_y_tensor[i];
    T ratio = ratio_tensor[i];

    T regValX = DREAMPLACE_STD_NAMESPACE::min(node_x - xl, xh - node_x);
    T halfSizeX = DREAMPLACE_STD_NAMESPACE::max(offset_x, DREAMPLACE_STD_NAMESPACE::min(targetHalfSizeX, regValX));

    T bXLo = node_x - halfSizeX;
    T bXHi = node_x + halfSizeX;

    int bin_index_xl = int(bXLo * inv_bin_size_x);
    int bin_index_xh = int((bXHi * inv_bin_size_x)) + 1;  // exclusive
    bin_index_xl = DREAMPLACE_STD_NAMESPACE::max(bin_index_xl, 0);
    bin_index_xh = DREAMPLACE_STD_NAMESPACE::min(bin_index_xh, num_bins_x);

    T regValY = DREAMPLACE_STD_NAMESPACE::min(node_y - yl, yh - node_y);
    T halfSizeY = DREAMPLACE_STD_NAMESPACE::max(offset_y, DREAMPLACE_STD_NAMESPACE::min(targetHalfSizeY, regValY));

    T bYLo = node_y - halfSizeY;
    T bYHi = node_y + halfSizeY;

    int bin_index_yl = int(bYLo * inv_bin_size_y);
    int bin_index_yh = int((bYHi * inv_bin_size_y)) + 1;  // exclusive
    bin_index_yl = DREAMPLACE_STD_NAMESPACE::max(bin_index_yl, 0);
    bin_index_yh = DREAMPLACE_STD_NAMESPACE::min(bin_index_yh + 1, num_bins_y);

    T inv_halfSizes = 1.0 / (halfSizeX * halfSizeY);
    T instDensity = ratio * inv_halfSizes;

    // update density potential map
    for (int k = bin_index_xl + threadIdx.y; k < bin_index_xh;
         k += blockDim.y) {
      T px = fpga_density_function(bXHi, bXLo, k, bin_size_x);
      T px_by_ratio = px * instDensity;

      for (int h = bin_index_yl + threadIdx.x; h < bin_index_yh;
           h += blockDim.x) {
        T py = fpga_density_function(bYHi, bYLo, h, bin_size_y);
        T area = px_by_ratio * py;
        atomicAddOp(&density_map_tensor[k * num_bins_y + h], area);

      }
    }
  }
}


template <typename T, typename AtomicOp>
int computeFPGADensityMapCallKernel(
    const T *x_tensor, const T *y_tensor, const T *node_size_x_clamped_tensor,
    const T *node_size_y_clamped_tensor, const T *offset_x_tensor,
    const T *offset_y_tensor, const T *ratio_tensor, int num_nodes,
    const int num_bins_x, const int num_bins_y, 
    const T xl, const T yl, const T xh, const T yh,
    const T bin_size_x, const T bin_size_y, AtomicOp atomicAddOp,
    typename AtomicOp::type *density_map_tensor, const int *sorted_node_map,
    const T targetHalfSizeX, const T targetHalfSizeY) {
  int thread_count = 64;
  dim3 blockSize(2, 2, thread_count);

  int block_count = (num_nodes - 1 + thread_count) / thread_count;
  computeFPGADensityMap<<<block_count, blockSize>>>(
      x_tensor, y_tensor, node_size_x_clamped_tensor,
      node_size_y_clamped_tensor, offset_x_tensor, offset_y_tensor,
      ratio_tensor, num_nodes, num_bins_x, num_bins_y, xl, yl, xh, yh,
      bin_size_x, bin_size_y, 1 / bin_size_x, 1 / bin_size_y, atomicAddOp,
      density_map_tensor, sorted_node_map, targetHalfSizeX, targetHalfSizeY);

  return 0;
}

template <typename T>
int computeFPGADensityMapCudaLauncher(
    const T *x_tensor, const T *y_tensor, const T *node_size_x_clamped_tensor,
    const T *node_size_y_clamped_tensor, const T *offset_x_tensor,
    const T *offset_y_tensor, const T *ratio_tensor, int num_nodes,
    const int num_bins_x, const int num_bins_y, const T xl, const T yl,
    const T xh, const T yh, const T bin_size_x, const T bin_size_y, 
    bool deterministic_flag, T *density_map_tensor, const int *sorted_node_map, 
    const T targetHalfSizeX, const T targetHalfSizeY) {
  if (deterministic_flag)  // deterministic implementation using unsigned long
                           // as fixed point number
  {
    // total die area
    double diearea = (xh - xl) * (yh - yl);
    int integer_bits = max((int)ceil(log2(diearea)) + 1, 32);
    int fraction_bits = max(64 - integer_bits, 0);
    unsigned long long int scale_factor = (1UL << fraction_bits);
    int num_bins = num_bins_x * num_bins_y;
    unsigned long long int *scaled_density_map_tensor = NULL;
    allocateCUDA(scaled_density_map_tensor, num_bins, unsigned long long int);

    AtomicAddCUDA<unsigned long long int> atomicAddOp(scale_factor);

    int thread_count = 512;
    copyScaleArray<<<(num_bins + thread_count - 1) / thread_count,
                     thread_count>>>(
        scaled_density_map_tensor, density_map_tensor, scale_factor, num_bins);
    computeFPGADensityMapCallKernel<T, decltype(atomicAddOp)>(
        x_tensor, y_tensor, node_size_x_clamped_tensor,
        node_size_y_clamped_tensor, offset_x_tensor, offset_y_tensor,
        ratio_tensor, num_nodes, num_bins_x, num_bins_y, xl,
        yl, xh, yh, bin_size_x, bin_size_y, atomicAddOp,
        scaled_density_map_tensor, sorted_node_map, targetHalfSizeX, targetHalfSizeY);
    copyScaleArray<<<(num_bins + thread_count - 1) / thread_count,
                     thread_count>>>(density_map_tensor,
                                     scaled_density_map_tensor,
                                     T(1.0 / scale_factor), num_bins);

    destroyCUDA(scaled_density_map_tensor);
  } else {
    AtomicAddCUDA<T> atomicAddOp;

    computeFPGADensityMapCallKernel<T, decltype(atomicAddOp)>(
        x_tensor, y_tensor, node_size_x_clamped_tensor,
        node_size_y_clamped_tensor, offset_x_tensor, offset_y_tensor,
        ratio_tensor, num_nodes, num_bins_x, num_bins_y, xl,
        yl, xh, yh, bin_size_x, bin_size_y, atomicAddOp, density_map_tensor,
        sorted_node_map, targetHalfSizeX, targetHalfSizeY);
  }

  return 0;
}

#define REGISTER_KERNEL_LAUNCHER(T)                                            \
  template int computeFPGADensityMapCudaLauncher<T>(                       \
      const T *x_tensor, const T *y_tensor,                                    \
      const T *node_size_x_clamped_tensor,                                     \
      const T *node_size_y_clamped_tensor, const T *offset_x_tensor,           \
      const T *offset_y_tensor, const T *ratio_tensor,                         \
      const int num_nodes, const int num_bins_x, const int num_bins_y,         \
      const T xl, const T yl, const T xh, const T yh, const T bin_size_x,      \
      const T bin_size_y, bool deterministic_flag, T *density_map_tensor,      \
      const int *sorted_node_map, const T targetHalfSizeX,                     \
      const T targetHalfSizeY);

REGISTER_KERNEL_LAUNCHER(float);
REGISTER_KERNEL_LAUNCHER(double);

DREAMPLACE_END_NAMESPACE

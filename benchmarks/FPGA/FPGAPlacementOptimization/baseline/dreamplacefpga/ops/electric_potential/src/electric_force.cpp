/**
 * @file   electric_force.cpp
 * @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
 * @date   Oct 2020
 * @brief  Compute electric force according to e-place
 */
#include "utility/src/torch.h"
#include "utility/src/utils.h"
// local dependency
#include "electric_potential/src/density_function.h"

DREAMPLACE_BEGIN_NAMESPACE

/// define fpga_density_function
template <typename T>
DEFINE_FPGA_DENSITY_FUNCTION(T);

#define CHECK_FLAT_CPU(x) AT_ASSERTM(!x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on CPU")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel()&1) == 0, #x "must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

template <typename T>
int computeElectricForceFPGALauncher(
    int num_bins_x, int num_bins_y, 
    const T* field_map_x_tensor, const T* field_map_y_tensor,
    const T* x_tensor, const T* y_tensor,
    const T* node_size_x_clamped_tensor, const T* node_size_y_clamped_tensor,
    const T* ratio_tensor,
    T bin_size_x, T bin_size_y, int num_nodes, int num_threads,
    T* grad_x_tensor, T* grad_y_tensor);

#define CALL_FPGA_LAUNCHER(begin, end)                                    \
  computeElectricForceFPGALauncher<scalar_t>(                             \
      num_bins_x, num_bins_y,                                             \
      DREAMPLACE_TENSOR_DATA_PTR(field_map_x, scalar_t),                  \
      DREAMPLACE_TENSOR_DATA_PTR(field_map_y, scalar_t),                  \
      DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + begin,                  \
      DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes + begin,      \
      DREAMPLACE_TENSOR_DATA_PTR(node_size_x_clamped, scalar_t) + begin,  \
      DREAMPLACE_TENSOR_DATA_PTR(node_size_y_clamped, scalar_t) + begin,  \
      DREAMPLACE_TENSOR_DATA_PTR(ratio, scalar_t) + begin,                \
      bin_size_x, bin_size_y, end - (begin), at::get_num_threads(),       \
      DREAMPLACE_TENSOR_DATA_PTR(grad_out, scalar_t) + begin,             \
      DREAMPLACE_TENSOR_DATA_PTR(grad_out, scalar_t) + num_nodes + begin)


/// @brief compute electric force for movable and filler cells
/// @param grad_pos input gradient from backward propagation
/// @param num_bins_x number of bins in horizontal bins
/// @param num_bins_y number of bins in vertical bins
/// @param num_movable_impacted_bins_x number of impacted bins for any movable
/// cell in x direction
/// @param num_movable_impacted_bins_y number of impacted bins for any movable
/// cell in y direction
/// @param num_filler_impacted_bins_x number of impacted bins for any filler
/// cell in x direction
/// @param num_filler_impacted_bins_y number of impacted bins for any filler
/// cell in y direction
/// @param field_map_x electric field map in x direction
/// @param field_map_y electric field map in y direction
/// @param pos cell locations. The array consists of all x locations and then y
/// locations.
/// @param node_size_x cell width array
/// @param node_size_y cell height array
/// @param bin_center_x bin center x locations
/// @param bin_center_y bin center y locations
/// @param xl left boundary
/// @param yl bottom boundary
/// @param xh right boundary
/// @param yh top boundary
/// @param bin_size_x bin width
/// @param bin_size_y bin height
/// @param num_movable_nodes number of movable cells
/// @param num_filler_nodes number of filler cells
at::Tensor electric_force_fpga(
    at::Tensor grad_pos, int num_bins_x, int num_bins_y,
    at::Tensor field_map_x, at::Tensor field_map_y, at::Tensor pos,
    at::Tensor node_size_x_clamped, at::Tensor node_size_y_clamped, at::Tensor ratio,
    double bin_size_x, double bin_size_y,
    int num_movable_nodes, int num_filler_nodes) {
  CHECK_FLAT_CPU(pos);
  CHECK_EVEN(pos);
  CHECK_CONTIGUOUS(pos);

  at::Tensor grad_out = at::zeros_like(pos);
  int num_nodes = pos.numel() / 2;

  DREAMPLACE_DISPATCH_FLOATING_TYPES(
      pos, "computeElectricForceFPGALauncher", [&] {
        CALL_FPGA_LAUNCHER(0, num_movable_nodes);
        if (num_filler_nodes) {
          int num_physical_nodes = num_nodes - num_filler_nodes;
          CALL_FPGA_LAUNCHER(num_physical_nodes, num_nodes);
        }
      });

  return grad_out.mul_(grad_pos);
}

template <typename T>
int computeElectricForceFPGALauncher(
    int num_bins_x, int num_bins_y, 
    const T* field_map_x_tensor, const T* field_map_y_tensor,
    const T* x_tensor, const T* y_tensor,
    const T* node_size_x_clamped_tensor, const T* node_size_y_clamped_tensor,
    const T* ratio_tensor,
    T bin_size_x, T bin_size_y, int num_nodes, int num_threads,
    T* grad_x_tensor, T* grad_y_tensor) {
  // density_map_tensor should be initialized outside

  T inv_bin_size_x = 1.0 / bin_size_x;
  T inv_bin_size_y = 1.0 / bin_size_y;
  int chunk_size =
      DREAMPLACE_STD_NAMESPACE::max(int(num_nodes / num_threads / 16), 1);
#pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
  for (int i = 0; i < num_nodes; ++i) {
    // use stretched node size
    T node_size_x = node_size_x_clamped_tensor[i];
    T node_size_y = node_size_y_clamped_tensor[i];
    T node_x = x_tensor[i];
    T node_y = y_tensor[i];
    T ratio = ratio_tensor[i];

    T bXLo = node_x;
    T bXHi = node_x + node_size_x;

    // Yibo: looks very weird implementation, but this is how RePlAce implements
    // it the common practice should be floor Zixuan and Jiaqi: use the common
    // practice of floor
    int bin_index_xl = int(bXLo * inv_bin_size_x);
    int bin_index_xh = int(bXHi * inv_bin_size_x);  // exclusive
    bin_index_xl = DREAMPLACE_STD_NAMESPACE::max(bin_index_xl, 0);
    bin_index_xh = DREAMPLACE_STD_NAMESPACE::min(bin_index_xh, num_bins_x - 1);

    T bYLo = node_y;
    T bYHi = node_y + node_size_y;

    // Yibo: looks very weird implementation, but this is how RePlAce implements
    // it the common practice should be floor Zixuan and Jiaqi: use the common
    // practice of floor
    int bin_index_yl = int(bYLo * inv_bin_size_y);
    int bin_index_yh = int(bYHi * inv_bin_size_y);  // exclusive
    bin_index_yl = DREAMPLACE_STD_NAMESPACE::max(bin_index_yl, 0);
    bin_index_yh = DREAMPLACE_STD_NAMESPACE::min(bin_index_yh, num_bins_y - 1);

    T& gx = grad_x_tensor[i];
    T& gy = grad_y_tensor[i];
    gx = 0.0;
    gy = 0.0;
    // update density potential map
    for (int k = bin_index_xl; k <= bin_index_xh; ++k) {
      T px = fpga_density_function(bXHi, bXLo, k, bin_size_x);
      for (int h = bin_index_yl; h <= bin_index_yh; ++h) {
        T py =
            fpga_density_function(bYHi, bYLo, h, bin_size_y);
        T area = px * py;

        int idx = k * num_bins_y + h;
        gx += area * field_map_x_tensor[idx];
        gy += area * field_map_y_tensor[idx];
      }
    }
  }

  return 0;
}

DREAMPLACE_END_NAMESPACE

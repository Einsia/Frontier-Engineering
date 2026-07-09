/**
 * @file   density_map.cpp
 * @author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
 * @date   Oct 2020
 * @brief  Compute density map according to e-place
 * (http://cseweb.ucsd.edu/~jlu/papers/eplace-todaes14/paper.pdf)
 */
#include "utility/src/torch.h"
#include "utility/src/utils.h"
// local dependency
#include "electric_potential/src/density_function.h"

DREAMPLACE_BEGIN_NAMESPACE

/// define fpga_density_function
template <typename T>
DEFINE_FPGA_DENSITY_FUNCTION(T);

/// @brief The fpga density model from elfPlace.
template <typename T, typename AtomicOp>
int computeFPGADensityMapLauncher(
    const T* x_tensor, const T* y_tensor, const T* node_size_x_tensor,
    const T* node_size_y_tensor, const T* offset_x_tensor,
    const T* offset_y_tensor, const T* ratio_tensor,
    const int num_nodes, const int num_bins_x, const int num_bins_y, const T xl,
    const T yl, const T xh, const T yh, const T bin_size_x, const T bin_size_y,
    const T targetHalfSizeX, const T targetHalfSizeY,
    const int num_threads, AtomicOp atomic_add_op,
    typename AtomicOp::type* buf_map);


#define CHECK_FLAT_CPU(x) AT_ASSERTM(!x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on CPU")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel()&1) == 0, #x "must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")


#define CALL_FPGA_LAUNCHER(begin, end, atomic_add_op, map_ptr)           \
  computeFPGADensityMapLauncher<scalar_t, decltype(atomic_add_op)>(      \
      DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + begin,                 \
      DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes + begin,     \
      DREAMPLACE_TENSOR_DATA_PTR(node_size_x_clamped, scalar_t) + begin, \
      DREAMPLACE_TENSOR_DATA_PTR(node_size_y_clamped, scalar_t) + begin, \
      DREAMPLACE_TENSOR_DATA_PTR(offset_x, scalar_t) + begin,            \
      DREAMPLACE_TENSOR_DATA_PTR(offset_y, scalar_t) + begin,            \
      DREAMPLACE_TENSOR_DATA_PTR(ratio, scalar_t) + begin, end - (begin),\
      num_bins_x, num_bins_y, xl, yl, xh, yh, bin_size_x, bin_size_y,    \
      targetHalfSizeX, targetHalfSizeY,                                  \
      at::get_num_threads(), atomic_add_op, map_ptr)

/// @brief compute density map for movable and filler cells for FPGA
/// @param pos cell locations. The array consists of all x locations and then y
/// locations.
/// @param node_size_x cell width array
/// @param node_size_y cell height array
/// @param bin_center_x bin center x locations
/// @param bin_center_y bin center y locations
/// @param initial_density_map initial density map for fixed cells
/// @param target_density target density
/// @param xl left boundary
/// @param yl bottom boundary
/// @param xh right boundary
/// @param yh top boundary
/// @param bin_size_x bin width
/// @param bin_size_y bin height
/// @param num_movable_nodes number of movable cells
/// @param num_filler_nodes number of filler cells
/// @param padding bin padding to boundary of placement region
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
at::Tensor density_map_fpga(
    at::Tensor pos, at::Tensor node_size_x_clamped,
    at::Tensor node_size_y_clamped, at::Tensor offset_x, at::Tensor offset_y,
    at::Tensor ratio, at::Tensor initial_density_map, double xl, double yl,
    double xh, double yh, double bin_size_x, double bin_size_y,
    double targetHalfSizeX, double targetHalfSizeY,
    int num_movable_nodes, int num_filler_nodes, int num_bins_x,
    int num_bins_y, int deterministic_flag) {

  CHECK_FLAT_CPU(pos);
  CHECK_EVEN(pos);
  CHECK_CONTIGUOUS(pos);

  at::Tensor density_map = initial_density_map.clone();
  int num_nodes = pos.numel() / 2;

  // total die area
  double diearea = (xh - xl) * (yh - yl);
  int integer_bits =
      DREAMPLACE_STD_NAMESPACE::max((int)ceil(log2(diearea)) + 1, 32);
  int fraction_bits = DREAMPLACE_STD_NAMESPACE::max(64 - integer_bits, 0);
  long scale_factor = (1L << fraction_bits);
  int num_bins = num_bins_x * num_bins_y;

  // Call the cuda kernel launcher
  DREAMPLACE_DISPATCH_FLOATING_TYPES(
      pos, "computeFPGADensityMapLauncher", [&] {
        if (deterministic_flag == 1) {
          std::vector<long> buf(num_bins, 0);
          AtomicAdd<long> atomic_add_op(scale_factor);
          CALL_FPGA_LAUNCHER(0, num_movable_nodes, atomic_add_op,
                                 buf.data());
          if (num_filler_nodes) {
            CALL_FPGA_LAUNCHER(num_nodes - num_filler_nodes, num_nodes,
                                   atomic_add_op, buf.data());
          }
          scaleAdd(DREAMPLACE_TENSOR_DATA_PTR(density_map, scalar_t),
                   buf.data(), 1.0 / scale_factor, num_bins,
                   at::get_num_threads());
        } else {
          auto buf = DREAMPLACE_TENSOR_DATA_PTR(density_map, scalar_t);
          AtomicAdd<scalar_t> atomic_add_op;
          CALL_FPGA_LAUNCHER(0, num_movable_nodes, atomic_add_op, buf);
          if (num_filler_nodes) {
            CALL_FPGA_LAUNCHER(num_nodes - num_filler_nodes, num_nodes,
                                   atomic_add_op, buf);
          }
        }
      });

  return density_map;
}

/// @brief Compute electric force for movable and filler cells
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
    int num_movable_nodes, int num_filler_nodes);

template <typename T, typename AtomicOp>
int computeFPGADensityMapLauncher(
    const T* x_tensor, const T* y_tensor, const T* node_size_x_clamped_tensor,
    const T* node_size_y_clamped_tensor, const T* offset_x_tensor,
    const T* offset_y_tensor, const T* ratio_tensor,
    const int num_nodes, const int num_bins_x, const int num_bins_y, const T xl,
    const T yl, const T xh, const T yh, const T bin_size_x, const T bin_size_y,
    const T targetHalfSizeX, const T targetHalfSizeY,
    const int num_threads, AtomicOp atomic_add_op,
    typename AtomicOp::type* buf_map) {
  // density_map_tensor should be initialized outside

  T inv_bin_size_x = 1.0 / bin_size_x;
  T inv_bin_size_y = 1.0 / bin_size_y;
  // do not use dynamic scheduling for determinism
  // int chunk_size =
  // DREAMPLACE_STD_NAMESPACE::max(int(num_nodes/num_threads/16), 1);
#pragma omp parallel for num_threads( \
    num_threads)  // schedule(dynamic, chunk_size)
  for (int i = 0; i < num_nodes; ++i) {
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
    int bin_index_xh =
        int((bXHi * inv_bin_size_x)) + 1;  // exclusive
    bin_index_xl = DREAMPLACE_STD_NAMESPACE::max(bin_index_xl, 0);
    bin_index_xh = DREAMPLACE_STD_NAMESPACE::min(bin_index_xh, num_bins_x);

    T regValY = DREAMPLACE_STD_NAMESPACE::min(node_y - yl, yh - node_y);
    T halfSizeY = DREAMPLACE_STD_NAMESPACE::max(offset_y, DREAMPLACE_STD_NAMESPACE::min(targetHalfSizeY, regValY));

    T bYLo = node_y - halfSizeY;
    T bYHi = node_y + halfSizeY;

    int bin_index_yl = int(bYLo * inv_bin_size_y);
    int bin_index_yh =
        int((bYHi * inv_bin_size_y)) + 1;  // exclusive
    bin_index_yl = DREAMPLACE_STD_NAMESPACE::max(bin_index_yl, 0);
    bin_index_yh = DREAMPLACE_STD_NAMESPACE::min(bin_index_yh, num_bins_y);

    T inv_halfSizes = 1.0 / (halfSizeX * halfSizeY);
    T instDensity = ratio * inv_halfSizes;

    // update density potential map
    for (int k = bin_index_xl; k < bin_index_xh; ++k) {
      T px = fpga_density_function(bXHi, bXLo, k, bin_size_x);
      T px_by_ratio = px * instDensity;

      for (int h = bin_index_yl; h < bin_index_yh; ++h) {
        T py =
            fpga_density_function(bYHi, bYLo, h, bin_size_y);
        T area = px_by_ratio * py;

        atomic_add_op(&buf_map[k * num_bins_y + h], area);
      }
    }
  }

  return 0;
}

#undef CALL_FPGA_LAUNCHER

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("density_map_fpga", &DREAMPLACE_NAMESPACE::density_map_fpga, "ElectricPotential Density Map");
  m.def("electric_force_fpga", &DREAMPLACE_NAMESPACE::electric_force_fpga, "ElectricPotential Electric Force");
}

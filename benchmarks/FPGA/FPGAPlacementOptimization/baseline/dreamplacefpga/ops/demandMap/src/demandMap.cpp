/**
 * @file   demandMap.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
 * @date   Nov 2020
 * @brief  Compute binCapMap
 */
#include "utility/src/torch.h"
#include "utility/src/utils.h"
// local dependency
#include "demandMap/src/demand_function.h"

DREAMPLACE_BEGIN_NAMESPACE

/// define compute_demand_function 
template <typename T>
DEFINE_COMPUTE_DEMAND_FUNCTION(T);

template <typename T, typename AtomicOp>
int computeDemandMapLauncher(
        const int *site_type_map, 
        const T *site_size_x, 
        const T *site_size_y, 
        const int num_bins_x, 
        const int num_bins_y, 
        const int width, 
        const int height, 
        const int num_threads,
        AtomicOp atomic_add_op,
        typename AtomicOp::type* buf_map
        );

#define CHECK_FLAT(x) AT_ASSERTM(!x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on CPU")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

#define CALL_FPGA_LAUNCHER(atomic_add_op, map_ptr)                  \
  computeDemandMapLauncher<scalar_t, decltype(atomic_add_op)>(      \
      DREAMPLACE_TENSOR_DATA_PTR(site_type_map, int),               \
      DREAMPLACE_TENSOR_DATA_PTR(site_size_x, scalar_t),            \
      DREAMPLACE_TENSOR_DATA_PTR(site_size_y, scalar_t),            \
      num_bins_x, num_bins_y, width, height,                        \
      num_threads, atomic_add_op, map_ptr)

/// @brief Compute wirelength preconditioner
int forward(
        at::Tensor site_type_map,
        at::Tensor site_size_x,
        at::Tensor site_size_y,
        int num_bins_x,
        int num_bins_y,
        int width,
        int height,
        int num_site_types,
        at::Tensor binCapMap,
        int num_threads,
        int deterministic_flag)
{
    CHECK_FLAT(site_type_map); 
    CHECK_CONTIGUOUS(site_type_map);

    CHECK_FLAT(site_size_x);
    CHECK_CONTIGUOUS(site_size_x);
    CHECK_FLAT(site_size_y);
    CHECK_CONTIGUOUS(site_size_y);

    DREAMPLACE_DISPATCH_FLOATING_TYPES(site_size_x, "computeDemandMapLauncher", [&] {
            if (deterministic_flag == 1)
            {
                double diearea = width * height;
                int integer_bits = DREAMPLACE_STD_NAMESPACE::max((int)ceil(log2(diearea)) + 1, 32);
                int fraction_bits = DREAMPLACE_STD_NAMESPACE::max(64 - integer_bits, 0);
                long scale_factor = (1L << fraction_bits);
                int num_bins = num_site_types * num_bins_x * num_bins_y;

                std::vector<long> buf(num_bins, 0);
                AtomicAdd<long> atomic_add_op(scale_factor);

                CALL_FPGA_LAUNCHER(atomic_add_op, buf.data());

                scaleAdd(DREAMPLACE_TENSOR_DATA_PTR(binCapMap, scalar_t),
                        buf.data(), 1.0 / scale_factor, num_bins, num_threads);
            } else
            {
                auto buf = DREAMPLACE_TENSOR_DATA_PTR(binCapMap, scalar_t);
                AtomicAdd<scalar_t> atomic_add_op;
                CALL_FPGA_LAUNCHER(atomic_add_op, buf);
            }

    });
    return 0; 
}

template <typename T, typename AtomicOp>
int computeDemandMapLauncher(
        const int *site_type_map, 
        const T *site_size_x, 
        const T *site_size_y, 
        const int num_bins_x, 
        const int num_bins_y, 
        const int width, 
        const int height, 
        const int num_threads,
        AtomicOp atomic_add_op,
        typename AtomicOp::type* buf_map
        )
{
    int bins_xy = num_bins_x * num_bins_y;
    int num_sites = width * height;
    T binW = T(width)/T(num_bins_x);
    T binH = T(height)/T(num_bins_y);
#pragma omp parallel for num_threads(num_threads)
    for (int s = 0; s < num_sites; ++s)
    {
        int site_type = site_type_map[s];
        int site_typeId = site_type*bins_xy;
        int rw = int(s/height);
        int cl = int(s%height);

        if (site_type > 0)
        {
            T nodeX = site_size_x[site_type];
            T nodeY = site_size_y[site_type];
            T col = DREAMPLACE_STD_NAMESPACE::round(cl/nodeY)*nodeY;
            int iLo = int(rw/binW);
            int jLo = int(col/binH);
            int iHi = DREAMPLACE_STD_NAMESPACE::min(int((rw + nodeX)/binW), num_bins_x-1);
            int jHi = DREAMPLACE_STD_NAMESPACE::min(int((col + nodeY)/binH), num_bins_y-1);
            for (int i = iLo; i <= iHi; ++i)
            {
                T w = compute_demand_function(i, binW, T(rw), nodeX);
                for (int j = jLo; j <= jHi; ++j)
                {
                    T h = compute_demand_function(j, binH, col, nodeY);
                    T area = w * h;
                    int index = site_typeId + i*num_bins_y + j;
                    atomic_add_op(&buf_map[index], area);
                }
            }
        }
    }
    return 0; 
}

#undef CALL_FPGA_LAUNCHER

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("forward", &DREAMPLACE_NAMESPACE::forward, "DemandMap forward");
}

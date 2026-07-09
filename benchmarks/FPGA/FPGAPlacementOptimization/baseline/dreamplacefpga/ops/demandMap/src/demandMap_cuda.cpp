/**
 * @file   demandMap_cuda.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
 * @date   Nov 2020
 * @brief  Compute binCapMap
 */
#include "utility/src/torch.h"
#include "utility/src/utils.h"
using namespace torch::indexing;

DREAMPLACE_BEGIN_NAMESPACE

template <typename T>
int computeDemandMapCudaLauncher(
        const int *site_type_map,
        const T *site_size_x, 
        const T *site_size_y, 
        const T binW,
        const T binH,
        const int num_site_types,
        const int num_bins_x, 
        const int num_bins_y, 
        const int width, 
        const int height, 
        const int bins_xy,
        const int deterministic_flag,
        T *binCapMap);

#define CHECK_FLAT(x) AT_ASSERTM(x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on GPU")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

/// @brief Compute bin capacity map
void forward(
        at::Tensor site_type_map, 
        at::Tensor site_size_x, 
        at::Tensor site_size_y, 
        int num_bins_x,
        int num_bins_y,
        int width, int height, 
        double binW, double binH,
        int num_site_types,
        int bins_xy,
        at::Tensor binCapMap,
        int deterministic_flag)
{
    CHECK_FLAT(site_type_map); 
    CHECK_CONTIGUOUS(site_type_map);

    CHECK_FLAT(site_size_x);
    CHECK_CONTIGUOUS(site_size_x);
    CHECK_FLAT(site_size_y);
    CHECK_CONTIGUOUS(site_size_y);

    DREAMPLACE_DISPATCH_FLOATING_TYPES(site_size_x, "computeDemandMapCudaLauncher", [&] {
            computeDemandMapCudaLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(site_type_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(site_size_x, scalar_t), 
                    DREAMPLACE_TENSOR_DATA_PTR(site_size_y, scalar_t), 
                    binW, binH, num_site_types, num_bins_x, num_bins_y,
                    width, height, bins_xy,
                    deterministic_flag,
                    DREAMPLACE_TENSOR_DATA_PTR(binCapMap, scalar_t)
                    );
            });
}

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("forward", &DREAMPLACE_NAMESPACE::forward, "DemandMap forward (CUDA)");
}

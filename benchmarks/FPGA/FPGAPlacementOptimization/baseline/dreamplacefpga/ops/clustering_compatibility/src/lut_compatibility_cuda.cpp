/**
 * @file   lut_compatibility_cuda.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Oct 2020
 * @brief  Compute the Clustering compatibility map for LUT based on elfPlace.
 */

#include "utility/src/torch.h"
#include "utility/src/utils.h"

DREAMPLACE_BEGIN_NAMESPACE

#define CHECK_FLAT(x) AT_ASSERTM(x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on GPU")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel() & 1) == 0, #x "must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

// fill the demand map node by node
template <typename T>
int fillDemandMapLUTCuda(const T *pos_x,
                         const T *pos_y,
                         const int *indices,
                         const int *type,
                         const T *node_size_x,
                         const T *node_size_y,
                         const int num_bins_x, const int num_bins_y,
                         const int num_bins_l, 
                         const T xl, const T yl, const T xh, const T yh,
                         const int num_nodes,
                         const T stddev_x, const T stddev_y,
                         const T inv_stddev_x, const T inv_stddev_y, 
                         const int ext_bin, const T inv_sqrt2,
                         const int deterministic_flag,
                         T *demMap);

// Given a Gaussian demand map, compute demand of each instance type based on local window demand distribution
template <typename T>
int computeInstanceAreaLUTCuda(const T *demMap,
                               const int *lut_fracture,
                               const int num_bins_x, 
                               const int num_bins_y,
                               const int num_bins_l,
                               const T stddev_x, const T stddev_y,
                               const int ext_bin, const T bin_area, 
                               T *areaMap);

// Set a set of instance area in a area vector based on the given area map
template <typename T>
int collectInstanceAreasLUTCuda(const T *pos_x,
                                const T *pos_y,
                                const int *indices,
                                const int *type,
                                const T *node_size_x,
                                const T *node_size_y,
                                const int num_bins_y,
                                const int num_bins_l,
                                const T *areaMap,
                                const int num_nodes,
                                const T inv_stddev_x, 
                                const T inv_stddev_y,
                                T *instAreas);

at::Tensor lut_compatibility(
    at::Tensor pos,
    at::Tensor indices,
    at::Tensor type,
    at::Tensor node_size_x,
    at::Tensor node_size_y,
    at::Tensor lut_fracture,
    int num_bins_x,
    int num_bins_y,
    int num_bins_l,
    double xl,
    double yl,
    double xh,
    double yh,
    double stddev_x,
    double stddev_y,
    double inv_stddev_x,
    double inv_stddev_y,
    int ext_bin,
    double bin_area,
    double inv_sqrt2,
    int deterministic_flag,
    at::Tensor demMap, 
    at::Tensor rsrcAreas
    )
{
    CHECK_FLAT(pos);
    CHECK_EVEN(pos);
    CHECK_CONTIGUOUS(pos);

    CHECK_FLAT(indices);
    CHECK_CONTIGUOUS(indices);

    CHECK_FLAT(type);
    CHECK_CONTIGUOUS(type);

    CHECK_FLAT(node_size_x);
    CHECK_CONTIGUOUS(node_size_x);

    CHECK_FLAT(node_size_y);
    CHECK_CONTIGUOUS(node_size_y);

    int num_nodes = pos.numel() / 2;

    // Call the cuda kernel launcher
    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "fillDemandMapLUTCuda", [&] {
        fillDemandMapLUTCuda<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t), DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes,
            DREAMPLACE_TENSOR_DATA_PTR(indices, int),
            DREAMPLACE_TENSOR_DATA_PTR(type, int),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_y, scalar_t),
            num_bins_x, num_bins_y, num_bins_l,
            xl, yl, xh, yh, indices.numel(),
            stddev_x, stddev_y,
            inv_stddev_x, inv_stddev_y, ext_bin, inv_sqrt2,
            deterministic_flag,
            DREAMPLACE_TENSOR_DATA_PTR(demMap, scalar_t));
    });

    at::Tensor areaMap = demMap.clone();

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "computeInstanceAreaLUTCuda", [&] {
        computeInstanceAreaLUTCuda<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(demMap, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(lut_fracture, int),
            num_bins_x, num_bins_y, num_bins_l,
            stddev_x, stddev_y, ext_bin, bin_area,
            DREAMPLACE_TENSOR_DATA_PTR(areaMap, scalar_t));
    });

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "collectInstanceAreasLUTCuda", [&] {
        collectInstanceAreasLUTCuda<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t), DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes,
            DREAMPLACE_TENSOR_DATA_PTR(indices, int),
            DREAMPLACE_TENSOR_DATA_PTR(type, int),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_y, scalar_t),
            num_bins_y, num_bins_l,
            DREAMPLACE_TENSOR_DATA_PTR(areaMap, scalar_t),
            indices.numel(), inv_stddev_x, inv_stddev_y,
            DREAMPLACE_TENSOR_DATA_PTR(rsrcAreas, scalar_t));
    });

    return areaMap;
}

at::Tensor flop_compatibility(
    at::Tensor pos, at::Tensor indices, at::Tensor ctrlSets,
    at::Tensor node_size_x, at::Tensor node_size_y,
    int num_bins_x, int num_bins_y, int num_bins_ck,
    int num_bins_ce, double xl, double yl, double xh,
    double yh, double stddev_x, double stddev_y,
    double inv_stddev_x, double inv_stddev_y, int ext_bin,
    double bin_area, double inv_sqrt, int slice_capacity,
    int deterministic_flag, at::Tensor demMap, at::Tensor rsrcAreas);

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m)
{
    m.def("lut_compatibility", &DREAMPLACE_NAMESPACE::lut_compatibility, "compute LUT compatibility instance areas (CUDA)");
    m.def("flop_compatibility", &DREAMPLACE_NAMESPACE::flop_compatibility, "compute Flop compatibility instance areas (CUDA)");
}

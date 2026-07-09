/**
 * @file   flop_compatibility_cuda.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Oct 2020
 * @brief  Compute the Clustering compatibility map for Flop based on elfPlace.
 */

#include "utility/src/torch.h"
#include "utility/src/utils.h"

DREAMPLACE_BEGIN_NAMESPACE

#define CHECK_FLAT(x) AT_ASSERTM(x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on GPU")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel() & 1) == 0, #x "must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

// fill the demand map node by node
template <typename T>
int fillDemandMapFFCuda(const T *pos_x,
                        const T *pos_y,
                        const int *indices,
                        const int *ctrlSets,
                        const T *node_size_x,
                        const T *node_size_y,
                        const int num_bins_x, const int num_bins_y,
                        const int num_bins_ck, const int num_bins_ce,
                        const T xl, const T yl,
                        const T xh, const T yh,
                        const int num_nodes,
                        const T stddev_x, const T stddev_y,
                        const T inv_stddev_x, const T inv_stddev_y, 
                        const int ext_bin, const T inv_sqrt,
                        const int deterministic_flag,
                        T *demMap);

// Given a Gaussian demand map, compute demand of each instance type based on local window demand distribution
template <typename T>
int computeInstanceAreaFFCuda(const T *demMap,
                              const int num_bins_x, const int num_bins_y,
                              const int num_bins_ck, const int num_bins_ce,
                              const T stddev_x, const T stddev_y,
                              const int ext_bin, const T bin_area,
                              const T half_slice, T *areaMap);

// Set a set of instance area in a area vector based on the given area map
template <typename T>
int collectInstanceAreasFFCuda(const T *pos_x,
                               const T *pos_y,
                               const int *indices,
                               const int *ctrlSets,
                               const T *node_size_x,
                               const T *node_size_y,
                               const int num_bins_y,
                               const int num_bins_ck, const int num_bins_ce,
                               const T *areaMap,
                               const int num_nodes,
                               const T inv_stddev_x, 
                               const T inv_stddev_y,
                               T *instAreas);

at::Tensor flop_compatibility(
    at::Tensor pos,
    at::Tensor indices,
    at::Tensor ctrlSets,
    at::Tensor node_size_x,
    at::Tensor node_size_y,
    int num_bins_x,
    int num_bins_y,
    int num_bins_ck,
    int num_bins_ce,
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
    double inv_sqrt,
    int slice_capacity,
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

    CHECK_FLAT(ctrlSets);
    CHECK_CONTIGUOUS(ctrlSets);

    CHECK_FLAT(node_size_x);
    CHECK_CONTIGUOUS(node_size_x);

    CHECK_FLAT(node_size_y);
    CHECK_CONTIGUOUS(node_size_y);

    int num_nodes = pos.numel() / 2;
    double half_slice = slice_capacity / 2.0;

    // Call the cuda kernel launcher
    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "fillDemandMapFFCuda", [&] {
        fillDemandMapFFCuda<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t), DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes,
            DREAMPLACE_TENSOR_DATA_PTR(indices, int),
            DREAMPLACE_TENSOR_DATA_PTR(ctrlSets, int),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_y, scalar_t),
            num_bins_x, num_bins_y,
            num_bins_ck, num_bins_ce,
            xl, yl, xh, yh, indices.numel(),
            stddev_x, stddev_y,
            inv_stddev_x, inv_stddev_y, ext_bin, inv_sqrt,
            deterministic_flag,
            DREAMPLACE_TENSOR_DATA_PTR(demMap, scalar_t));
    });

    at::Tensor areaMap = demMap.clone();

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "computeInstanceAreaFFCuda", [&] {
        computeInstanceAreaFFCuda<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(demMap, scalar_t),
            num_bins_x, num_bins_y,
            num_bins_ck, num_bins_ce,
            stddev_x, stddev_y, ext_bin, bin_area, half_slice,
            DREAMPLACE_TENSOR_DATA_PTR(areaMap, scalar_t));
    });

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "collectInstanceAreasFFCuda", [&] {
        collectInstanceAreasFFCuda<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t), DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes,
            DREAMPLACE_TENSOR_DATA_PTR(indices, int),
            DREAMPLACE_TENSOR_DATA_PTR(ctrlSets, int),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_y, scalar_t),
            num_bins_y, num_bins_ck, num_bins_ce,
            DREAMPLACE_TENSOR_DATA_PTR(areaMap, scalar_t),
            indices.numel(), inv_stddev_x, inv_stddev_y,
            DREAMPLACE_TENSOR_DATA_PTR(rsrcAreas, scalar_t));
    });

    return areaMap;
}

DREAMPLACE_END_NAMESPACE

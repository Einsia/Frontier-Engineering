/**
 * @file   lut_compatibility.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Oct 2020
 * @brief  Compute the Clustering compatibility map for LUT based on elfPlace.
 */

#include "utility/src/torch.h"
#include "utility/src/utils.h"
// local dependency
#include "clustering_compatibility/src/functions.h"

DREAMPLACE_BEGIN_NAMESPACE

/// define gaussian_auc_function 
template <typename T>
DEFINE_GAUSSIAN_AUC_FUNCTION(T);
/// define lut_compute_areas_function
template <typename T>
DEFINE_LUT_COMPUTE_AREAS_FUNCTION(T);
template <typename T>
DEFINE_LUT_COMPUTE_AREAS_FUNCTION_GENERIC(T);

#define CHECK_FLAT(x) AT_ASSERTM(!x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on CPU")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel() & 1) == 0, #x "must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")


// fill the demand map node by node
template <typename T>
int fillDemandMapLUT(const T *pos_x,
                     const T *pos_y,
                     const int *indices,
                     const int *type,
                     const T *node_size_x,
                     const T *node_size_y,
                     const int num_bins_x, 
                     const int num_bins_y,
                     const int num_bins_l,
                     int num_threads, int num_nodes,
                     T stddev_x, T stddev_y,
                     T inv_stddev_x, T inv_stddev_y, 
                     int ext_bin, T inv_sqrt2,
                     T *demandX, T *demandY, T *demMap)
{

    //int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nodes / num_threads / 16), 1);
    //#pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < num_nodes; ++i)
    {
        const int idx = indices[i];
        T node_x = pos_x[idx] + 0.5 * node_size_x[idx];
        T node_y = pos_y[idx] + 0.5 * node_size_y[idx];
        int lutType = type[idx];

        int binX = int(node_x * inv_stddev_x);
        int binY = int(node_y * inv_stddev_y);

        // compute the bin box that this net will affect
        int bin_index_xl = DREAMPLACE_STD_NAMESPACE::max(binX - ext_bin, 0);
        int bin_index_xh = DREAMPLACE_STD_NAMESPACE::min(binX + ext_bin + 1, num_bins_x);

        int bin_index_yl = DREAMPLACE_STD_NAMESPACE::max(binY - ext_bin, 0);
        int bin_index_yh = DREAMPLACE_STD_NAMESPACE::min(binY + ext_bin + 1, num_bins_y);

        T gaussianX = gaussian_auc_function(node_x, stddev_x, bin_index_xl*stddev_x, bin_index_xh* stddev_x, inv_sqrt2); 
        T gaussianY = gaussian_auc_function(node_y, stddev_y, bin_index_yl*stddev_y, bin_index_yh* stddev_y, inv_sqrt2); 

        T sf = 1.0 / (gaussianX * gaussianY);

        for (int x = bin_index_xl; x < bin_index_xh; ++x)
        {
           demandX[x - bin_index_xl] = gaussian_auc_function(node_x, stddev_x, x*stddev_x, (x+1)*stddev_x, inv_sqrt2);
        }

        for (int y = bin_index_yl; y < bin_index_yh; ++y)
        {
           demandY[y - bin_index_yl] = gaussian_auc_function(node_y, stddev_y, y*stddev_y, (y+1)*stddev_y, inv_sqrt2);
        }

        for (int x = bin_index_xl; x < bin_index_xh; ++x)
        {
            for (int y = bin_index_yl; y < bin_index_yh; ++y)
            {
                //#pragma omp atomic update
                int index = x * (num_bins_y * num_bins_l) + y * num_bins_l + lutType;
                T dem = sf * demandX[x - bin_index_xl] * demandY[y - bin_index_yl];
                demMap[index] += dem;
            }
        }
    }
    return 0;
}


// Given a Gaussian demand map, compute demand of each instance type based on local window demand distribution
template <typename T>
int computeInstanceAreaLUT(const T *demMap, const int* lut_fracture,
                           const int num_bins_x, const int num_bins_y, 
                           const int num_bins_l,
                           int num_threads, T stddev_x, T stddev_y,
                           int ext_bin, T bin_area, T *areaMap)
{

    int total_bins = num_bins_x*num_bins_y;
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(total_bins / num_threads / 16), 1);
    //#pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < total_bins; ++i)
    {
        int binX = int(i/num_bins_y);
        int binY = int(i%num_bins_y);

        // compute the bin box
        int bin_index_xl = DREAMPLACE_STD_NAMESPACE::max(binX - ext_bin, 0);
        int bin_index_xh = DREAMPLACE_STD_NAMESPACE::min(binX + ext_bin + 1, num_bins_x);

        int bin_index_yl = DREAMPLACE_STD_NAMESPACE::max(binY - ext_bin, 0);
        int bin_index_yh = DREAMPLACE_STD_NAMESPACE::min(binY + ext_bin + 1, num_bins_y);

        int idx = binX * (num_bins_y * num_bins_l) + binY * num_bins_l;

        for (int x = bin_index_xl; x < bin_index_xh; ++x)
        {
            for (int y = bin_index_yl; y < bin_index_yh; ++y)
            {
                int index = x * (num_bins_y * num_bins_l) + y * num_bins_l;
                if (x != binX && y != binY)
                {
                    for (int l = 0; l < num_bins_l; ++l)
                    {
                        areaMap[idx + l] += demMap[index + l];
                        //tempMap[idx + l] += demMap[index + l];
                    }
                }
            }
        }

        // Compute instance areas based on the window demand distribution
        T winArea = (bin_index_xh - bin_index_xl) * (bin_index_yh - bin_index_yl) * bin_area;

        //lut_compute_areas_function(winArea, tempMap, idx, num_bins_l);
        lut_compute_areas_function_generic(lut_fracture, winArea, areaMap, idx, num_bins_l);
    }
    return 0;
}


// Set a set of instance area in a area vector based on the given area map
template <typename T>
int collectInstanceAreasLUT(const T *pos_x,
                            const T *pos_y,
                            const int *indices,
                            const int *type,
                            const T *node_size_x,
                            const T *node_size_y,
                            const int num_bins_y,
                            const int num_bins_l,
                            const T *areaMap,
                            int num_threads, int num_nodes,
                            T inv_stddev_x, T inv_stddev_y,
                            T *instAreas)
{

    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nodes / num_threads / 16), 1);
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < num_nodes; ++i)
    {
        const int idx = indices[i];
        T node_x = pos_x[idx] + 0.5 * node_size_x[idx];
        T node_y = pos_y[idx] + 0.5 * node_size_y[idx];

        int binX = int(node_x * inv_stddev_x);
        int binY = int(node_y * inv_stddev_y);

        int index = binX * (num_bins_y * num_bins_l) + binY * num_bins_l + type[idx];
        instAreas[idx] = areaMap[index];
    }
    return 0;
}

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
    int num_threads, 
    double stddev_x,
    double stddev_y,
    double inv_stddev_x,
    double inv_stddev_y,
    int ext_bin,
    double bin_area,
    double inv_sqrt2,
    at::Tensor demandX, 
    at::Tensor demandY, 
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

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "fillDemandMapLUT", [&] {
        fillDemandMapLUT<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t), DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes,
            DREAMPLACE_TENSOR_DATA_PTR(indices, int),
            DREAMPLACE_TENSOR_DATA_PTR(type, int),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_y, scalar_t),
            num_bins_x, num_bins_y, num_bins_l,
            num_threads, indices.numel(),
            stddev_x, stddev_y,
            inv_stddev_x, inv_stddev_y, ext_bin, inv_sqrt2,
            DREAMPLACE_TENSOR_DATA_PTR(demandX, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(demandY, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(demMap, scalar_t));
    });

    at::Tensor areaMap = demMap.clone();

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "computeInstanceAreaLUT", [&] {
        computeInstanceAreaLUT<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(demMap, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(lut_fracture, int),
            num_bins_x, num_bins_y, num_bins_l, num_threads,
            stddev_x, stddev_y, ext_bin, bin_area,
            DREAMPLACE_TENSOR_DATA_PTR(areaMap, scalar_t));
    });

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "collectInstanceAreasLUT", [&] {
        collectInstanceAreasLUT<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t), DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes,
            DREAMPLACE_TENSOR_DATA_PTR(indices, int),
            DREAMPLACE_TENSOR_DATA_PTR(type, int),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_y, scalar_t),
            num_bins_y, num_bins_l,
            DREAMPLACE_TENSOR_DATA_PTR(areaMap, scalar_t),
            num_threads, indices.numel(), 
            inv_stddev_x, inv_stddev_y,
            DREAMPLACE_TENSOR_DATA_PTR(rsrcAreas, scalar_t));
    });

    return areaMap;
}

at::Tensor flop_compatibility(
    at::Tensor pos, at::Tensor indices, at::Tensor ctrlSets,
    at::Tensor node_size_x, at::Tensor node_size_y, int num_bins_x, 
    int num_bins_y, int num_bins_ck, int num_bins_ce,
    int num_threads, double stddev_x, double stddev_y,
    double inv_stddev_x, double inv_stddev_y, int ext_bin,
    double bin_area, double inv_sqrt, int slice_capacity,
    at::Tensor demandX, at::Tensor demandY, at::Tensor demMap, 
    at::Tensor rsrcAreas);

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m)
{
    m.def("lut_compatibility", &DREAMPLACE_NAMESPACE::lut_compatibility, "compute LUT compatibility instance areas");
    m.def("flop_compatibility", &DREAMPLACE_NAMESPACE::flop_compatibility, "compute Flop compatibility instance areas");
}

/**
 * @file   flop_compatibility.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Oct 2020
 * @brief  Compute the Clustering compatibility map for FLOP based on elfPlace.
 */

#include "utility/src/torch.h"
#include "utility/src/utils.h"
// local dependency
#include "clustering_compatibility/src/functions.h"

DREAMPLACE_BEGIN_NAMESPACE

/// define gaussian_auc_function 
template <typename T>
DEFINE_GAUSSIAN_AUC_FUNCTION(T);
/// define smooth_ceil_function 
template <typename T>
DEFINE_SMOOTH_CEIL_FUNCTION(T);
/// define flop_aggregate_demand_function
template <typename T>
DEFINE_FLOP_AGGREGATE_DEMAND_FUNCTION(T);

#define CHECK_FLAT(x) AT_ASSERTM(!x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on CPU")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel() & 1) == 0, #x "must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

// fill the demand map node by node
template <typename T>
int fillDemandMapFF(const T *pos_x,
                    const T *pos_y,
                    const int *indices,
                    const int *ctrlSets,
                    const T *node_size_x,
                    const T *node_size_y,
                    const int num_bins_x, const int num_bins_y,
                    const int num_bins_ck, const int num_bins_ce,
                    int num_threads, int num_nodes,
                    T stddev_x, T stddev_y,
                    T inv_stddev_x, T inv_stddev_y, 
                    int ext_bin, T inv_sqrt,
                    T *demandX, T *demandY, T *demMap)
{

    //unsigned int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nodes / num_threads / 16), 1);
    //#pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    unsigned int n_o_p = num_bins_y * num_bins_ck * num_bins_ce;
    unsigned int o_p = num_bins_ck * num_bins_ce;
    for (unsigned int i = 0; i < num_nodes; ++i)
    {
        const unsigned int nIdx = indices[i];
        T node_x = pos_x[nIdx] + 0.5 * node_size_x[nIdx];
        T node_y = pos_y[nIdx] + 0.5 * node_size_y[nIdx];
        //Ctrl set values
        int cksr = ctrlSets[i*3 + 1];
        int ce = ctrlSets[i*3 + 2];

        int binX = int(node_x * inv_stddev_x);
        int binY = int(node_y * inv_stddev_y);

        // compute the bin box that this net will affect
        int bin_index_xl = DREAMPLACE_STD_NAMESPACE::max(binX - ext_bin, 0);
        int bin_index_xh = DREAMPLACE_STD_NAMESPACE::min(binX + ext_bin + 1, num_bins_x);

        int bin_index_yl = DREAMPLACE_STD_NAMESPACE::max(binY - ext_bin, 0);
        int bin_index_yh = DREAMPLACE_STD_NAMESPACE::min(binY + ext_bin + 1, num_bins_y);

        T gaussianX = gaussian_auc_function(node_x, stddev_x, bin_index_xl*stddev_x, bin_index_xh* stddev_x, inv_sqrt); 
        T gaussianY = gaussian_auc_function(node_y, stddev_y, bin_index_yl*stddev_y, bin_index_yh* stddev_y, inv_sqrt); 

        T sf = 1.0 / (gaussianX * gaussianY);

        for (int x = bin_index_xl; x < bin_index_xh; ++x)
        {
           demandX[x - bin_index_xl] = gaussian_auc_function(node_x, stddev_x, x*stddev_x, (x+1)*stddev_x, inv_sqrt);
        }

        for (int y = bin_index_yl; y < bin_index_yh; ++y)
        {
           demandY[y - bin_index_yl] = gaussian_auc_function(node_y, stddev_y, y*stddev_y, (y+1)*stddev_y, inv_sqrt);
        }

        ////DBG
        //std::cout << "x limit: " << bin_index_xl << " to " << bin_index_xh << std::endl;
        //std::cout << "y limit: " << bin_index_yl << " to " << bin_index_yh << std::endl;
        ////DBG

        for (int x = bin_index_xl; x < bin_index_xh; ++x)
        {
            for (int y = bin_index_yl; y < bin_index_yh; ++y)
            {
                //#pragma omp atomic update
                unsigned int idx = x * n_o_p + y * o_p + cksr * num_bins_ce + ce; 
                T dem = sf * demandX[x - bin_index_xl] * demandY[y - bin_index_yl];
                ////DBG
                //std::cout << "idx = " << x << "(x) * " << n_o_p << "(n_o_p) + "
                //          << y << "(y) * " << o_p << "(o_p) + "
                //          << cksr << "(cksr) * " << num_bins_ce << "(num_bins_ce) + "
                //          << ce << "(ce)" << std::endl;
                //std::cout << "FillDemandMapFF: Add " << dem << " to demMap at " << idx << std::endl;
                ////DBG
                demMap[idx] += dem;
            }
        }
    }
    return 0;
}


// Given a Gaussian demand map, compute demand of each instance type based on local window demand distribution
template <typename T>
int computeInstanceAreaFF(const T *demMap,
                          const int num_bins_x, const int num_bins_y,
                          const int num_bins_ck, const int num_bins_ce,
                          int num_threads, T stddev_x, T stddev_y,
                          int ext_bin, T bin_area, T half_slice, T *areaMap)
{

    int total_bins = num_bins_x*num_bins_y;
    int n_o_p = num_bins_y * num_bins_ck * num_bins_ce;
    int o_p = num_bins_ck * num_bins_ce;

    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(total_bins / num_threads / 16), 1);
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < total_bins; ++i)
    {
        ////DBG
        //std::cout << "Start for Bin " << i << " out of " << total_bins << std::endl;
        ////DBG
        
        int binX = int(i/num_bins_y);
        int binY = int(i%num_bins_y);

        // compute the bin box
        int bin_index_xl = DREAMPLACE_STD_NAMESPACE::max(binX - ext_bin, 0);
        int bin_index_xh = DREAMPLACE_STD_NAMESPACE::min(binX + ext_bin + 1, num_bins_x);

        int bin_index_yl = DREAMPLACE_STD_NAMESPACE::max(binY - ext_bin, 0);
        int bin_index_yh = DREAMPLACE_STD_NAMESPACE::min(binY + ext_bin + 1, num_bins_y);

        int index = binX * n_o_p + binY * o_p;

        for (int x = bin_index_xl; x < bin_index_xh; ++x)
        {
            for (int y = bin_index_yl; y < bin_index_yh; ++y)
            {
                if (x != binX && y != binY)
                {
                    unsigned int idx = x * n_o_p + y * o_p;
                    flop_aggregate_demand_function(demMap, idx, areaMap, index, num_bins_ck, num_bins_ce);
                }
            }
        }
        ////DBG
        //std::cout << "For Bin " << i << " completed flop_aggregate_demand_function for x: " << bin_index_xl << " -> " << bin_index_xh
        //          << " and y : " << bin_index_yl << " -> " << bin_index_yh << std::endl;
        ////DBG
        
        //Flop compute areas
        for (int ck = 0; ck < num_bins_ck; ++ck)
        {
            T totalQ = 0.0;
            for (int ce = 0; ce < num_bins_ce; ++ce)
            {
                unsigned int updIdx = index + ck*num_bins_ce + ce;
                if (areaMap[updIdx] > 0.0)
                {
                    totalQ += smooth_ceil_function(areaMap[updIdx]* 0.25, 0.25);
                }
            }

            T sf = half_slice * smooth_ceil_function(totalQ*0.5, 0.5) / totalQ;

            for (int cE = 0; cE < num_bins_ce; ++cE)
            {
                unsigned int updIdx = index + ck*num_bins_ce + cE;
                if (areaMap[updIdx] > 0.0)
                {
                    T qrt = smooth_ceil_function(areaMap[updIdx]* 0.25, 0.25);
                    areaMap[updIdx] = sf * qrt / areaMap[updIdx];
                }
            }
        }
        ////DBG
        //std::cout << "For Bin " << i << " completed flop area compute for num_bins_ck: " << num_bins_ck
        //          << " and num_bins_ce: " << num_bins_ce << std::endl;
        ////DBG
        
    }
    return 0;
}


// Set a set of instance area in a area vector based on the given area map
template <typename T>
int collectInstanceAreasFF(const T *pos_x,
                           const T *pos_y,
                           const int *indices,
                           const int *ctrlSets,
                           const T *node_size_x,
                           const T *node_size_y,
                           const int num_bins_y,
                           const int num_bins_ck, const int num_bins_ce,
                           const T *areaMap,
                           int num_threads, int num_nodes,
                           T inv_stddev_x, T inv_stddev_y,
                           T *instAreas)
{

    int n_o_p = num_bins_y * num_bins_ck * num_bins_ce;
    int o_p = num_bins_ck * num_bins_ce;
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nodes / num_threads / 16), 1);
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (unsigned int i = 0; i < num_nodes; ++i)
    {
        const unsigned int idx = indices[i];
        T node_x = pos_x[idx] + 0.5 * node_size_x[idx];
        T node_y = pos_y[idx] + 0.5 * node_size_y[idx];
        //Ctrl set values
        int cksr = ctrlSets[i*3 + 1];
        int ce = ctrlSets[i*3 + 2];

        int binX = int(node_x * inv_stddev_x);
        int binY = int(node_y * inv_stddev_y);

        unsigned int index = binX * n_o_p + binY * o_p + cksr * num_bins_ce + ce;
        instAreas[idx] = areaMap[index];
    }
    return 0;
}

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
    int num_threads, 
    double stddev_x,
    double stddev_y,
    double inv_stddev_x,
    double inv_stddev_y,
    int ext_bin,
    double bin_area,
    double inv_sqrt,
    int slice_capacity,
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

    CHECK_FLAT(ctrlSets);
    CHECK_CONTIGUOUS(ctrlSets);

    CHECK_FLAT(node_size_x);
    CHECK_CONTIGUOUS(node_size_x);

    CHECK_FLAT(node_size_y);
    CHECK_CONTIGUOUS(node_size_y);

    int num_nodes = pos.numel() / 2;
    double half_slice = slice_capacity / 2.0;

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "fillDemandMapFF", [&] {
        fillDemandMapFF<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t), DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes,
            DREAMPLACE_TENSOR_DATA_PTR(indices, int),
            DREAMPLACE_TENSOR_DATA_PTR(ctrlSets, int),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_y, scalar_t),
            num_bins_x, num_bins_y,
            num_bins_ck, num_bins_ce,
            num_threads, indices.numel(),
            stddev_x, stddev_y,
            inv_stddev_x, inv_stddev_y, ext_bin, inv_sqrt,
            DREAMPLACE_TENSOR_DATA_PTR(demandX, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(demandY, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(demMap, scalar_t));
    });

    //std::cout << "Completed fillDemandMapFF" << std::endl;

    at::Tensor areaMap = demMap.clone();

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "computeInstanceAreaFF", [&] {
        computeInstanceAreaFF<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(demMap, scalar_t),
            num_bins_x, num_bins_y,
            num_bins_ck, num_bins_ce,
            num_threads,
            stddev_x, stddev_y, ext_bin, bin_area, half_slice,
            DREAMPLACE_TENSOR_DATA_PTR(areaMap, scalar_t));
    });
    //std::cout << "Completed computeInstanceAreaFF" << std::endl;

    DREAMPLACE_DISPATCH_FLOATING_TYPES(pos, "collectInstanceAreasFF", [&] {
        collectInstanceAreasFF<scalar_t>(
            DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t), DREAMPLACE_TENSOR_DATA_PTR(pos, scalar_t) + num_nodes,
            DREAMPLACE_TENSOR_DATA_PTR(indices, int),
            DREAMPLACE_TENSOR_DATA_PTR(ctrlSets, int),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_x, scalar_t),
            DREAMPLACE_TENSOR_DATA_PTR(node_size_y, scalar_t),
            num_bins_y, num_bins_ck, num_bins_ce,
            DREAMPLACE_TENSOR_DATA_PTR(areaMap, scalar_t),
            num_threads, indices.numel(), 
            inv_stddev_x, inv_stddev_y,
            DREAMPLACE_TENSOR_DATA_PTR(rsrcAreas, scalar_t));
    });
    //std::cout << "Completed collectInstanceAreasFF" << std::endl;

    return areaMap;
}

DREAMPLACE_END_NAMESPACE


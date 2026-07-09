#include "utility/src/utils.cuh"
#include "utility/src/limits.h"
// local dependency
#include "demandMap/src/demand_function.h"

DREAMPLACE_BEGIN_NAMESPACE

/// define compute_demand_function 
template <typename T>
inline __device__ DEFINE_COMPUTE_DEMAND_FUNCTION(T);

template <typename T, typename AtomicOp>
__global__ void __launch_bounds__(1024, 8) computeDemandMap(
        const int *site_type_map, const T *site_size_x, const T *site_size_y,
        const T binW, const T binH, const int num_bins_x, const int num_bins_y, 
        const int width, const int height, const int bins_xy,
        AtomicOp atomicAddOp, typename AtomicOp::type *binCapMap)
{
    __shared__ int num_sites;
    num_sites = width*height;

    int idx = blockIdx.x * blockDim.z + threadIdx.z;
    if (idx < num_sites)
    {
        int site_type = site_type_map[idx];
        int site_typeId = site_type*bins_xy;
        int rw = int(idx/height);
        int cl = int(idx%height);

        if (site_type > 0)
        {
            T nodeX = site_size_x[site_type];
            T nodeY = site_size_y[site_type];
            T col = DREAMPLACE_STD_NAMESPACE::round(cl/nodeY)*nodeY;
            int iLo = int(rw/binW);
            int jLo = int(col/binH);
            int iHi = DREAMPLACE_STD_NAMESPACE::min(int((rw + nodeX)/binW), num_bins_x-1);
            int jHi = DREAMPLACE_STD_NAMESPACE::min(int((col + nodeY)/binH), num_bins_y-1);

            for (int i = iLo + threadIdx.y; i <= iHi; i += blockDim.y)
            {
                T w = compute_demand_function(i, binW, T(rw), nodeX);
                for (int j = jLo + threadIdx.x; j <= jHi; j += blockDim.x)
                {
                    T h = compute_demand_function(j, binH, col, nodeY);
                    T area = w * h;
                    int index = site_typeId + i*num_bins_y + j;
                    atomicAddOp(&binCapMap[index], area);
                }
            }
        }
    }
}

template <typename T, typename AtomicOp>
int computeDemandMapCallKernel(
        const int *site_type_map, const T *site_size_x,
        const T *site_size_y, const T binW, const T binH,
        const int num_bins_x, const int num_bins_y,
        const int width, const int height,
        const int bins_xy,
        AtomicOp atomicAddOp,
        typename AtomicOp::type *binCapMap)
{
  int thread_count = 64;
  dim3 blockSize(2, 2, thread_count);

  int block_count = (width*height - 1 + thread_count) / thread_count;

    computeDemandMap<<<block_count, blockSize>>>(
            site_type_map, site_size_x, site_size_y, binW, binH,
            num_bins_x, num_bins_y, width, height, bins_xy,
            atomicAddOp, binCapMap);

    return 0;
}


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
        T *binCapMap)
{
    if (deterministic_flag == 1)
    {
    // total die area
    double diearea = width * height;
    int integer_bits = max((int)ceil(log2(diearea)) + 1, 32);
    int fraction_bits = max(64 - integer_bits, 0);
    unsigned long long int scale_factor = (1UL << fraction_bits);
    int num_bins = num_site_types * num_bins_x * num_bins_y;

    unsigned long long int *bin_cap_map = NULL;
    allocateCUDA(bin_cap_map, num_bins, unsigned long long int);

    AtomicAddCUDA<unsigned long long int> atomicAddOp(scale_factor);
    int thread_count = 512;

    copyScaleArray<<<(num_bins + thread_count - 1) / thread_count,
                     thread_count>>>(
        bin_cap_map, binCapMap, scale_factor, num_bins);

    computeDemandMapCallKernel<T, decltype(atomicAddOp)>(
                site_type_map, site_size_x, site_size_y, binW, binH,
                num_bins_x, num_bins_y, width, height, bins_xy,
                atomicAddOp, bin_cap_map);

    copyScaleArray<<<(num_bins + thread_count - 1) / thread_count,
                     thread_count>>>(binCapMap,
                     bin_cap_map, T(1.0 / scale_factor), num_bins);

    destroyCUDA(bin_cap_map);
  } else
    {
        AtomicAddCUDA<T> atomicAddOp;

        computeDemandMapCallKernel<T, decltype(atomicAddOp)>(
                site_type_map, site_size_x, site_size_y, binW, binH,
                num_bins_x, num_bins_y, width, height, bins_xy,
                atomicAddOp, binCapMap);
    }
    return 0;
}

// manually instantiate the template function
#define REGISTER_KERNEL_LAUNCHER(T)                                 \
    template int computeDemandMapCudaLauncher<T>(                   \
        const int *site_type_map, const T *site_size_x,             \
        const T *site_size_y, const T binW, const T binH,           \
        const int num_site_types, const int num_bins_x,             \
        const int num_bins_y, const int width, const int height,    \
        const int bins_xy, const int deterministic_flag, T *binCapMap);

REGISTER_KERNEL_LAUNCHER(float);
REGISTER_KERNEL_LAUNCHER(double);

DREAMPLACE_END_NAMESPACE

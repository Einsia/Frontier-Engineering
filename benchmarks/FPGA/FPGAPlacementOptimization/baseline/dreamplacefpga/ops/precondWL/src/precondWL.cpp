/**
 * @file   precondWL.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Nov 2020
 * @brief  Compute precond WL
 */
#include "utility/src/torch.h"
#include "utility/src/utils.h"

DREAMPLACE_BEGIN_NAMESPACE

template <typename T>
int computePrecondWLLauncher(
        const T *net_weights, 
        const int *flat_node2pin_start_map,
        const int *flat_node2pin_map, 
        const int *flat_net2pin, 
        const int *pin2net_map, 
        int num_nodes, 
        int num_threads, 
        T *out 
        );

#define CHECK_FLAT(x) AT_ASSERTM(!x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on CPU")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

/// @brief Compute wirelength preconditioner
void forward(
        at::Tensor net_weights,
        at::Tensor flat_node2pin_start_map,
        at::Tensor flat_node2pin_map,
        at::Tensor flat_net2pin,
        at::Tensor pin2net_map,
        int num_nodes,
        int num_threads,
        at::Tensor out) 
{
    CHECK_FLAT(net_weights); 
    CHECK_CONTIGUOUS(net_weights);

    CHECK_FLAT(flat_node2pin_start_map); 
    CHECK_CONTIGUOUS(flat_node2pin_start_map);
    CHECK_FLAT(flat_node2pin_map);
    CHECK_CONTIGUOUS(flat_node2pin_map);

    CHECK_FLAT(flat_net2pin); 
    CHECK_CONTIGUOUS(flat_net2pin);

    CHECK_FLAT(pin2net_map);
    CHECK_CONTIGUOUS(pin2net_map);

    DREAMPLACE_DISPATCH_FLOATING_TYPES(out, "computePrecondWLLauncher", [&] {
            computePrecondWLLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(net_weights, scalar_t), 
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_start_map, int), 
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin, int), 
                    DREAMPLACE_TENSOR_DATA_PTR(pin2net_map, int), 
                    num_nodes, num_threads, 
                    DREAMPLACE_TENSOR_DATA_PTR(out, scalar_t)
                    );
            });
}

template <typename T>
int computePrecondWLLauncher(
        const T *net_weights, 
        const int *flat_node2pin_start_map,
        const int *flat_node2pin_map, 
        const int *flat_net2pin, 
        const int *pin2net_map, 
        int num_nodes, 
        int num_threads, 
        T *out 
        )
{
    int chunk_size = DREAMPLACE_STD_NAMESPACE::max(int(num_nodes/ num_threads / 16), 1);
    //#pragma omp parallel for schedule(static)
    //#pragma omp parallel for num_threads(num_threads)
    #pragma omp parallel for num_threads(num_threads) schedule(dynamic, chunk_size)
    for (int i = 0; i < num_nodes; ++i)
    {
        int beg = flat_node2pin_start_map[i];
        int end = flat_node2pin_start_map[i+1];

        for (int p = beg; p < end; ++p)
        {
            int netId = pin2net_map[flat_node2pin_map[p]];
            int numPins = flat_net2pin[netId+1] - flat_net2pin[netId];
            //Ignore single pin nets
            if (numPins > 1)
            {
                out[i] += net_weights[netId]/(numPins-1.0);
            }
        }
    }

    return 0; 
}

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("forward", &DREAMPLACE_NAMESPACE::forward, "PrecondWL forward");
}

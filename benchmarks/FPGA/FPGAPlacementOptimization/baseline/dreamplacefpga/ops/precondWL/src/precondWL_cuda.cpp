/**
 * @file   precondWL_cuda.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Nov 2020
 * @brief  Compute precond WL
 */
#include "utility/src/torch.h"
#include "utility/src/Msg.h"
using namespace torch::indexing;

DREAMPLACE_BEGIN_NAMESPACE

template <typename T>
int computePrecondWLCudaLauncher(
        const int *flat_node2pin_start_map,
        const int *flat_node2pin_map, 
        const int *pin2net_map, 
        const int *flat_net2pin, 
        const T *net_weights, 
        int num_nodes, 
        T *out 
        );


#define CHECK_FLAT(x) AT_ASSERTM(x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on GPU")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")


/// @brief Compute half-perimeter wirelength along with net bbox 
/// @param pos cell locations, array of x locations and then y locations 
/// @param flat_netpin similar to the JA array in CSR format, which is flattened from the net2pin map (array of array)
/// @param netpin_start similar to the IA array in CSR format, IA[i+1]-IA[i] is the number of pins in each net, the length of IA is number of nets + 1
/// @param net_mask an array to record whether compute the where for a net or not 
void forward(
        at::Tensor flat_node2pin_start_map,
        at::Tensor flat_node2pin_map,
        at::Tensor pin2net_map,
        at::Tensor flat_net2pin,
        at::Tensor net_weights,
        int num_nodes,
        at::Tensor out
        ) 
{
    CHECK_FLAT(flat_node2pin_start_map); 
    CHECK_CONTIGUOUS(flat_node2pin_start_map);
    CHECK_FLAT(flat_node2pin_map);
    CHECK_CONTIGUOUS(flat_node2pin_map);
    CHECK_FLAT(pin2net_map);
    CHECK_CONTIGUOUS(pin2net_map);
    CHECK_FLAT(flat_net2pin);
    CHECK_CONTIGUOUS(flat_net2pin);

    CHECK_FLAT(net_weights);
    CHECK_CONTIGUOUS(net_weights);

    DREAMPLACE_DISPATCH_FLOATING_TYPES(out, "computePrecondWLCudaLauncher", [&] {
            computePrecondWLCudaLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_map, int), 
                    DREAMPLACE_TENSOR_DATA_PTR(pin2net_map, int), 
                    DREAMPLACE_TENSOR_DATA_PTR(flat_net2pin, int), 
                    DREAMPLACE_TENSOR_DATA_PTR(net_weights, scalar_t), 
                    num_nodes, 
                    DREAMPLACE_TENSOR_DATA_PTR(out, scalar_t)
                    );
            });
}

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("forward", &DREAMPLACE_NAMESPACE::forward, "PrecondWL forward (CUDA)");
}

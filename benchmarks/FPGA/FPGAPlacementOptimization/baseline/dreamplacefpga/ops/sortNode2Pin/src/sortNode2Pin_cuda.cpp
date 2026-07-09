/**
 * @file   sortNode2Pin_cuda.cpp
 * @author Rachel Selina (DREAMPlaceFPGA-PL)
 * @date   Nov 2021
 * @brief  sort node2pin
 */

#include "utility/src/torch.h"
#include "utility/src/Msg.h"
using namespace torch::indexing;

DREAMPLACE_BEGIN_NAMESPACE

int computeSortNode2PinCudaLauncher(
        const int *flat_node2pin_start_map,
        int *flat_node2pin_map, 
        const int *sorted_pin_map, 
        const int num_nodes, 
        int *out 
        );


#define CHECK_FLAT(x) AT_ASSERTM(x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on GPU")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")


/// @brief sort node2pin map
/// @param flat_netpin similar to the JA array in CSR format, which is flattened from the net2pin map (array of array)
/// @param netpin_start similar to the IA array in CSR format, IA[i+1]-IA[i] is the number of pins in each net, the length of IA is number of nets + 1
void forward(
        at::Tensor flat_node2pin_start_map,
        at::Tensor flat_node2pin_map,
        at::Tensor sorted_pin_map,
        int num_nodes,
        at::Tensor out
        ) 
{
    CHECK_FLAT(flat_node2pin_start_map); 
    CHECK_CONTIGUOUS(flat_node2pin_start_map);
    //CHECK_FLAT(flat_node2pin_map);
    //CHECK_CONTIGUOUS(flat_node2pin_map);
    CHECK_FLAT(sorted_pin_map);
    CHECK_CONTIGUOUS(sorted_pin_map);

    //DREAMPLACE_DISPATCH_FLOATING_TYPES(out.type(), "computeSortNode2PinCudaLauncher", [&] {
            computeSortNode2PinCudaLauncher(
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_start_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_map, int), 
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_pin_map, int), 
                    num_nodes, 
                    DREAMPLACE_TENSOR_DATA_PTR(out, int)
                    );
     //       });
}

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("forward", &DREAMPLACE_NAMESPACE::forward, "SortNode2Pin forward (CUDA)");
}

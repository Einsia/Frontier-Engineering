/**
 * @file   sortNode2Pin.cpp
 * @author Rachel Selina (DREAMPlaceFPGA-PL)
 * @date   Nov 2021
 * @brief  sort node2pin
 */
#include "utility/src/torch.h"
#include "utility/src/Msg.h"

DREAMPLACE_BEGIN_NAMESPACE

int computeSortNode2PinLauncher(
        const int *flat_node2pin_start_map,
        int *flat_node2pin_map, 
        const int *sorted_pin_map, 
        const int num_nodes, 
        const int num_threads, 
        int *out 
        );

#define CHECK_FLAT(x) AT_ASSERTM(!x.is_cuda() && x.ndimension() == 1, #x "must be a flat tensor on CPU")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x "must be contiguous")

/// @brief Sort node2pin
void forward(
        at::Tensor flat_node2pin_start_map,
        at::Tensor flat_node2pin_map,
        at::Tensor sorted_pin_map,
        int num_nodes,
        int num_threads,
        at::Tensor out) 
{
    CHECK_FLAT(flat_node2pin_start_map); 
    CHECK_CONTIGUOUS(flat_node2pin_start_map);
    //CHECK_FLAT(flat_node2pin_map);
    //CHECK_CONTIGUOUS(flat_node2pin_map);
    CHECK_FLAT(sorted_pin_map);
    CHECK_CONTIGUOUS(sorted_pin_map);

    //DREAMPLACE_DISPATCH_FLOATING_TYPES(out.type(), "computeSortNode2PinLauncher", [&] {
            computeSortNode2PinLauncher(
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_start_map, int), 
                    DREAMPLACE_TENSOR_DATA_PTR(flat_node2pin_map, int),
                    DREAMPLACE_TENSOR_DATA_PTR(sorted_pin_map, int), 
                    num_nodes, 
                    num_threads, 
                    DREAMPLACE_TENSOR_DATA_PTR(out, int)
                    );
     //      });
}

int computeSortNode2PinLauncher(
        const int *flat_node2pin_start_map,
        int *flat_node2pin_map, 
        const int *sorted_pin_map, 
        const int num_nodes, 
        const int num_threads, 
        int *out 
        )
{
    #pragma omp parallel for num_threads(num_threads)
    for (int i = 0; i < num_nodes; ++i)
    {
        int beg = flat_node2pin_start_map[i];
        int end = flat_node2pin_start_map[i+1];

        std::sort(flat_node2pin_map+beg, flat_node2pin_map+end, [&sorted_pin_map](const auto &a, const auto &b){return sorted_pin_map[a] < sorted_pin_map[b];});
        out[i] = sorted_pin_map[flat_node2pin_map[beg]];
    }

    return 0; 
}

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("forward", &DREAMPLACE_NAMESPACE::forward, "SortNode2Pin forward");
}

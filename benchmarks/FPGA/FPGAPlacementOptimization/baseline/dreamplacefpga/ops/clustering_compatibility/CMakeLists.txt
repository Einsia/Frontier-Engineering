set(OP_NAME clustering_compatibility)

set(INCLUDE_DIRS 
  ${CMAKE_CURRENT_SOURCE_DIR}/..
  )

set(LINK_LIBS utility_cxx
  OpenMP::OpenMP_CXX
  )

add_pytorch_extension(clustering_compatibility_cpp
  src/lut_compatibility.cpp
  src/flop_compatibility.cpp
  EXTRA_INCLUDE_DIRS ${INCLUDE_DIRS}
  EXTRA_LINK_LIBRARIES ${LINK_LIBS})

install(TARGETS 
  clustering_compatibility_cpp
  DESTINATION dreamplacefpga/ops/${OP_NAME})

if(TORCH_ENABLE_CUDA)
add_pytorch_extension(clustering_compatibility_cuda
  src/lut_compatibility_cuda.cpp
  src/lut_compatibility_cuda_kernel.cu
  src/flop_compatibility_cuda.cpp
  src/flop_compatibility_cuda_kernel.cu
  EXTRA_INCLUDE_DIRS ${INCLUDE_DIRS}
  EXTRA_LINK_LIBRARIES ${LINK_LIBS})

install(TARGETS 
  clustering_compatibility_cuda
  DESTINATION dreamplacefpga/ops/${OP_NAME})
endif(TORCH_ENABLE_CUDA)

file(GLOB INSTALL_SRCS ${CMAKE_CURRENT_SOURCE_DIR}/*.py)
install(FILES ${INSTALL_SRCS} DESTINATION dreamplacefpga/ops/${OP_NAME})

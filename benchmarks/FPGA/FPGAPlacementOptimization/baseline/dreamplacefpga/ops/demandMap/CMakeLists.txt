set(OP_NAME demandMap)

set(INCLUDE_DIRS 
  ${CMAKE_CURRENT_SOURCE_DIR}/..
  )

set(LINK_LIBS utility_cxx
  OpenMP::OpenMP_CXX
  )

add_pytorch_extension(demandMap_cpp
  src/demandMap.cpp
  EXTRA_INCLUDE_DIRS ${INCLUDE_DIRS}
  EXTRA_LINK_LIBRARIES ${LINK_LIBS})

install(TARGETS 
  demandMap_cpp
  DESTINATION dreamplacefpga/ops/${OP_NAME})

if(TORCH_ENABLE_CUDA)

add_pytorch_extension(demandMap_cuda
  src/demandMap_cuda.cpp
  src/demandMap_cuda_kernel.cu
  EXTRA_INCLUDE_DIRS ${INCLUDE_DIRS}
  EXTRA_LINK_LIBRARIES ${LINK_LIBS})

install(TARGETS 
  demandMap_cuda
  DESTINATION dreamplacefpga/ops/${OP_NAME})
endif(TORCH_ENABLE_CUDA)

file(GLOB INSTALL_SRCS ${CMAKE_CURRENT_SOURCE_DIR}/*.py)
install(FILES ${INSTALL_SRCS} DESTINATION dreamplacefpga/ops/${OP_NAME})

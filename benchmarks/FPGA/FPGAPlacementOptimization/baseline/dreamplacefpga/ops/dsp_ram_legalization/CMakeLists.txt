set(OP_NAME dsp_ram_legalization)

set(INCLUDE_DIRS 
  ${CMAKE_CURRENT_SOURCE_DIR}/..
  ${LIMBO_SOURCE_DIR}
  ${LEMON_INCLUDE_DIRS}
  )

set(LINK_LIBS utility_cxx
  lemon
  OpenMP::OpenMP_CXX
  )

add_pytorch_extension(legalize_cpp
  src/legalize.cpp
  EXTRA_INCLUDE_DIRS ${INCLUDE_DIRS}
  EXTRA_LINK_LIBRARIES ${LINK_LIBS}
  )

install(TARGETS legalize_cpp DESTINATION dreamplacefpga/ops/${OP_NAME})
file(GLOB INSTALL_SRCS ${CMAKE_CURRENT_SOURCE_DIR}/*.py)
install(FILES ${INSTALL_SRCS} DESTINATION dreamplacefpga/ops/${OP_NAME})

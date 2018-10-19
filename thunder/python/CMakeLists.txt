set(PYBIND11_CPP_STANDARD -std=c++11)
pybind11_add_module(pythunder thunder.cc)

#target_link_libraries(pythunder PRIVATE pybind11::module)
target_link_libraries(pythunder PRIVATE thunder)

set_target_properties(pythunder PROPERTIES PREFIX "${PYTHON_MODULE_PREFIX}"
        SUFFIX "${PYTHON_MODULE_EXTENSION}" COMPILE_FLAGS "-Wno-register")
set(PYBIND11_CPP_STANDARD -std=c++17)
# for some reason it gives LTO errors on my laptop with release mode
pybind11_add_module(pycyclone cyclone.cc)

#target_link_libraries(pythunder PRIVATE pybind11::module)
set(CMAKE_EXE_LINKER_FLAGS " -static")
target_link_libraries(pycyclone PRIVATE cyclone)
target_link_libraries(pycyclone PUBLIC -static-libgcc -static-libstdc++)

set_target_properties(pycyclone PROPERTIES PREFIX "${PYTHON_MODULE_PREFIX}"
        SUFFIX "${PYTHON_MODULE_EXTENSION}" COMPILE_FLAGS "-Wno-register")

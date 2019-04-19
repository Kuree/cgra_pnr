set(PYBIND11_CPP_STANDARD -std=c++11)
pybind11_add_module(pythunder thunder.cc)

#target_link_libraries(pythunder PRIVATE pybind11::module)
set(CMAKE_EXE_LINKER_FLAGS " -static")
target_link_libraries(pythunder PRIVATE thunder)
if (${STATIC})
target_link_libraries(pythunder PUBLIC -static-libgcc -static-libstdc++)
endif()

set_target_properties(pythunder PROPERTIES PREFIX "${PYTHON_MODULE_PREFIX}"
        SUFFIX "${PYTHON_MODULE_EXTENSION}" COMPILE_FLAGS "-Wno-register")


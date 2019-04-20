set(PYBIND11_CPP_STANDARD -std=c++17)
# for some reason it gives LTO errors on my laptop with release mode
pybind11_add_module(pycyclone cyclone.cc)

set_target_properties(pycyclone PROPERTIES LINK_SEARCH_START_STATIC 1)
set_target_properties(pycyclone PROPERTIES LINK_SEARCH_END_STATIC 1)
set(CMAKE_FIND_LIBRARY_SUFFIXES ".a")

target_link_libraries(pycyclone PRIVATE cyclone)
target_link_libraries(pycyclone PUBLIC ${STATIC_FLAG})


set_target_properties(pycyclone PROPERTIES PREFIX "${PYTHON_MODULE_PREFIX}"
        SUFFIX "${PYTHON_MODULE_EXTENSION}" COMPILE_FLAGS "-Wno-register")

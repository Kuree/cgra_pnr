cmake_minimum_required(VERSION 3.8)
project(thunder)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "-Wall -Wextra -Werror -fPIC")

include(CheckCXXCompilerFlag)
CHECK_CXX_COMPILER_FLAG(-funroll-all-loops UNROLL)
if (UNROLL)
    # osx's clang doesn't support it (travis)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -funroll-all-loops")
endif()

find_package(Threads REQUIRED)

set(HEADER_LIBRARY src/include/randutils.hpp
                   src/include/tqdm.h
                   src/include/cxxpool.h
                   src/include/spline.h src/layout.cc src/layout.hh
                   src/graph.cc src/graph.hh)

add_library(thunder src/anneal.cc src/anneal.hh src/util.cc
            src/util.hh src/detailed.cc src/detailed.hh
            src/multi_place.cc src/multi_place.hh
            src/global.cc src/global.hh
            src/vpr.cc src/vpr.hh
            src/io.cc src/io.hh
            ${HEADER_LIBRARY})

add_subdirectory(python/pybind11)
add_subdirectory(lib/leidenalg)
add_subdirectory(python)
add_subdirectory(example)

target_link_libraries(thunder leidenalg ${CMAKE_THREAD_LIBS_INIT})

cmake_minimum_required(VERSION 3.0)
project(cyclone)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "-Wall -Wextra -Werror -fPIC")

include(CheckCXXCompilerFlag)
CHECK_CXX_COMPILER_FLAG(-funroll-all-loops UNROLL)
if (${UNROLL})
    # osx's clang doesn't support it (travis)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -funroll-all-loops")
endif()

CHECK_CXX_COMPILER_FLAG(-static-libgcc STATIC)
if (${STATIC})
    set(STATIC_FLAG "-static-libgcc -static-libstdc++")
endif()

add_library(cyclone src/graph.hh src/graph.cc src/route.hh
                    src/route.cc src/net.cc src/net.hh src/util.cc src/util.hh
                    src/global.cc src/global.hh src/io.cc src/io.hh)

add_subdirectory(python/pybind11)
add_subdirectory(python)

add_subdirectory(example)

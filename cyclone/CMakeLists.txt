cmake_minimum_required(VERSION 3.0)
project(cyclone)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "-Wall -Wextra -Werror -fPIC -pthread \
    -funroll-all-loops -O3 -march=native")

add_library(cyclone src/graph.hh
                    src/graph.cc)

add_subdirectory(python/pybind11)
add_subdirectory(python)

add_executable(demo_test test.cc)
target_link_libraries(demo_test cyclone)

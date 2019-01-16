cmake_minimum_required(VERSION 3.0)
project(cyclone)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "-Wall -Wextra -Werror -fPIC -pthread \
    -funroll-all-loops -O3 -march=native")

add_library(cyclone src/graph.hh src/graph.cc src/route.hh
                    src/route.cc src/net.cc src/net.hh src/util.cc src/util.hh
                    src/global.cc src/global.hh src/io.cc src/io.hh)

target_link_libraries(cyclone stdc++fs)

add_subdirectory(python/pybind11)
add_subdirectory(python)


add_subdirectory(example)

cmake_minimum_required(VERSION 3.5)
project(thunder)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_FLAGS "-Wall -Wextra -Werror -fPIC -pthread -g")

add_library(thunder src/anneal.cc src/anneal.hh src/util.cc
            src/util.hh src/detailed.cc src/detailed.hh
            src/multi_place.cc src/multi_place.hh
            src/include/randutils.hpp src/include/tqdm.h
            src/include/cxxpool.h)

add_subdirectory(python/pybind11)
add_subdirectory(python)

add_executable(test test.cc)
target_link_libraries(test thunder)
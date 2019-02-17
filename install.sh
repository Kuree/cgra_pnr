#!/bin/bash
set -e

file_dir=$(dirname "$(realpath $0)")
# placer
build_dir=${file_dir}/thunder/build
mkdir -p ${build_dir}
cd ${build_dir}
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j placer
cd ..

# router
# for travis we use C++ implementation directly since it's determinstic
build_dir=${file_dir}/cyclone/build
mkdir -p ${build_dir}
cd ${build_dir}
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j router
cd ..

#!/bin/bash

# for travis we use C++ implementation directly since it's determinstic
file_dir=$(dirname "$(realpath $0)")
build_dir=${file_dir}/build
mkdir ${build_dir}
pushd ${build_dir}
cmake ..
make -j router
popd

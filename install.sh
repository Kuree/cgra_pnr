#!/bin/bash

file_dir=$(dirname "$(realpath $0)")
# placer
# TODO

# router
# for travis we use C++ implementation directly since it's determinstic
build_dir=${file_dir}/cyclone/build
mkdir -p ${build_dir}
pushd ${build_dir}
cmake ..
make -j router
popd

#!/usr/bin/env bash
set -xe
declare -a design_files=("conv_1_2_mapped" "conv_2_1_mapped" "conv_3_1_mapped"
                         "conv_bw_mapped" "onebit_bool_mapped" "pointwise_mapped")


# clone CGRAGenerator and build it
git clone --single-branch -b master --depth 1 \
        https://github.com/StanfordAHA/CGRAGenerator
pushd CGRAGenerator/hardware/generator_z/top
./build_cgra.sh

cgra=$(realpath cgra_info.xml)
popd

for file in "${design_files[@]}"
do
    echo "Downloading $file"
    rm -f ${file}.json
    wget "https://cdn.jsdelivr.net/gh/StanfordAHA/CGRAGenerator@master/bitstream/bsbuilder/testdir/examples/${file}.json"
    echo "Running PnR tools on ${file}"
    ./scripts/pnr_flow.sh $cgra $file.json
done


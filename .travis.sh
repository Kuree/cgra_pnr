#!/usr/bin/env bash
set -xe
declare -a design_files=("conv_1_2_mapped" "conv_2_1_mapped" "conv_3_1_mapped"
                         "conv_bw_mapped" "onebit_bool_mapped" "pointwise_mapped")


echo "Downloading CGRA info"
wget https://github.com/StanfordAHA/CGRAGenerator/raw/shortmem/hardware/generator_z/top/examples/cgra_info.txt.shortmem
cgra="cgra_info.txt.shortmem"

for file in "${design_files[@]}"
do
    echo "Downloading $file"
    rm -f ${file}.json
    wget "https://github.com/StanfordAHA/CGRAGenerator/raw/master/bitstream/bsbuilder/testdir/examples/${file}.json"
    echo "Running PnR tools on ${file}"
    ./scripts/pnr_flow.sh $cgra $file.json
    echo "Running PnR tools on ${file} -no-reg-fold"
    ./scripts/pnr_flow.sh -no-reg-fold $cgra $file.json
done


#!/usr/bin/env bash
set -e

function print_usage() {
    echo "Usage: $0 [--no-reg-fold] <arch_file> <netlist.packed>" >&2
    exit 1
}

file_dir=$(dirname "$(realpath $0)")
root_dir=$(realpath ${file_dir}/../)

if [ "$#" -eq 2 ]; then
    cgra=$1
    packed=$2
elif [ "$#" -eq 3 ]; then
    option=$1
    cgra=$2
    packed=$3
else
    print_usage
fi

if ! [ -f ${cgra} ] || ! [ -f ${packed} ]; then
    print_usage
fi

# assume user already have the env activated
emb="${packed%.packed}.emb"
place="${packed%.packed}.place"
python ${root_dir}/random_walk.py -i ${packed} -o ${emb}
python ${root_dir}/place.py --cgra ${cgra} -i ${packed} -e ${emb} -o ${place} --no-vis ${option}

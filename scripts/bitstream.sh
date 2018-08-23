#!/usr/bin/env bash
set -e
file_dir=$(dirname "$(realpath $0)")
root_dir=$(realpath $file_dir/../)

function print_usage() {
    echo "Usage: $0 [--no-reg-fold] <arch_file> <netlist.packed>" >&2
    exit 1
}

if [ "$#" -eq 2 ]; then
    cgra=$1
    packed=$2
    bsb="${packed%.packed}.bsb"
elif [ "$#" -eq 3 ]; then
    if [[ $1 == -* ]]; then
        option=$1
        cgra=$2
        packed=$3
        bsb="${packed%.packed}.bsb"
    else
        cgra=$1
        packed=$2
        bsb=$3
    fi
elif [ "$#" -eq 4 ]; then
    option=$1
    cgra=$2
    packed=$3
    bsb=$4
else
    print_usage
fi

if ! [ -f ${cgra} ] || ! [ -f ${packed} ]; then
    print_usage
fi

# assume user already have the env activated
place="${packed%.packed}.place"
if ! [ -f "$place" ] ; then
    echo "$place not found" >&2
    exit 1
fi

route="${packed%.packed}.route"
if ! [ -f "$route" ] ; then
    echo "$route not found" >&2
    exit 1
fi

netlist="${packed%.packed}.json"
python ${root_dir}/bitstream.py ${option} -c ${cgra} -n ${netlist} \
                                -i ${packed} -p ${place} -r ${route} -o ${bsb}

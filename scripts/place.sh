#!/usr/bin/env bash
set -e

# global variables
is_garet=0

function print_usage() {
    echo "Usage: $0 [--no-reg-fold] <arch_file> <netlist.packed>" >&2
    exit 1
}

function detect_garnet() {
    PATTERN="<CGRA>"
    if grep -q "${PATTERN}" $1; then
        is_garnet=0;
    else
        is_garnet=1;
    fi
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
place="${packed%.packed}.place"

# check if it's garnet or not
detect_garnet ${cgra}

if [ ${is_garnet} -eq "1" ]; then
    # we need to look up the layout file
    layout=$(awk -F "=" '/layout/ {print $2}' ${cgra})
    echo "Using layout file " ${layout}
    python ${root_dir}/place.py --layout ${layout} -i ${packed} -o ${place} --no-vis ${option}
else
    echo "Using cgra_info file " ${cgra}
    python ${root_dir}/place.py --cgra ${cgra} -i ${packed} -o ${place} --no-vis ${option}
fi

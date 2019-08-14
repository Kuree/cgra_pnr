#!/usr/bin/env bash
set -e

# global variables
is_garnet=0

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
root_dir=$(realpath $file_dir/../)
router=${root_dir}/cyclone/build/example/router

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
if ! [ -f "$place" ] ; then
    echo "$place not found" >&2
    exit 1
fi

route="${packed%.packed}.route"

detect_garnet ${cgra}

# if it's garnet, we already have the grpah files specified
if [ ${is_garnet} -eq "1" ]; then
    echo "Using routing files"
    rm -rf ${route}
    # garnet files has to use router
    if ! [ -f ${router} ]; then
        echo "${router} not found"
        exit 1
    fi
    graphs=$(awk -F "=" '/graph/ {print $2}' ${cgra})
    ${router} ${packed} ${place} ${graphs[@]} ${route}
    echo "Save result to ${route}"
else
    # dump the graph files
    graph_dir=$(dirname ${packed})
    python ${root_dir}/process_graph.py -i ${cgra} -o ${graph_dir}


    # if the C++ binary exists, we will use it instead
    if [ -f ${router} ]; then
        echo "Using C++ implementation"
        rm -rf ${route}
        ${router} ${packed} ${place} 1 ${graph_dir}/1bit.graph \
            16 ${graph_dir}/16bit.graph ${route}
    else
        echo "Using Python binding. Results may be undeterministic."
        echo "To use C++ implementation, do ${root_dir}/cyclone/install.sh"
        python ${root_dir}/router.py ${option} -g ${graph_dir} -i ${packed} -p ${place} -o ${route}
    fi
fi


#!/usr/bin/env bash
set -e

function print_usage() {
    echo "Usage: $0 [--no-reg-fold] <arch_file> <netlist.packed>" >&2
    exit 1
}

file_dir=$(dirname "$(realpath $0)")
root_dir=$(realpath $file_dir/../)

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

# dump the graph files
graph_dir=$(dirname ${packed})
python ${root_dir}/process_graph.py -i ${cgra} -o ${graph_dir}

route="${packed%.packed}.route"

# if the C++ binary exists, we will use it instead
router=${root_dir}/cyclone/build/example/router
if [ -f ${router} ]; then
    echo "Using C++ implementation"
    rm -rf ${route}
    ${router} ${packed} ${place} ${graph_dir}/1bit.graph 1 ${route}
    ${router} ${packed} ${place} ${graph_dir}/16bit.graph 16 ${route}
else
    echo "Using Python binding. Results may be undeterministic."
    echo "To use C++ implementation, do \${ROOT}/cyclone/.travis.sh"
    python ${root_dir}/new_router.py ${option} -g ${graph_dir} -i ${packed} -p ${place} -o ${route}
fi

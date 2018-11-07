#!/usr/bin/env bash
set -e

function print_usage() {
    echo "Usage: $0 <mapped_netlist.json> <fixed_netlist.json>" >&2
    exit 1
}

if [ "$#" -eq 2 ]; then
    input_json=$1
    output_json=$2
else
    print_usage
fi

if ! [ -f ${input_json} ]; then
    print_usage
fi

BASEDIR=$(dirname "$0")

# fix things in order since const fix broke the json formatting
smax_fix=${output_json}.smax

echo "Fixing smax..."
python ${BASEDIR}/fix_smax.py ${input_json} ${smax_fix}

echo "Fixing constants..."
python ${BASEDIR}/fix_const.py ${smax_fix} ${output_json}

echo "Saved output to ${output_json}"

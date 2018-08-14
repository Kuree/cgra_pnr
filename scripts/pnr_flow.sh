#!/usr/bin/env bash
set -xe

function print_usage() {
    echo "Usage: $0 [-no-reg-fold] <arch_file> <netlist.json>" >&2
    exit 1
}

if [ "$#" -eq 2 ]; then
    cgra=$1
    netlist=$2
elif [ "$#" -eq 3 ]; then
    option=$1
    cgra=$2
    netlist=$3
else
    print_usage
fi

if ! [ -f ${cgra} ] || ! [ -f ${netlist} ]; then
    print_usage
fi

BASEDIR=$(dirname "$0")

# assume user already have the env activated
# pack
python $BASEDIR/../packer.py ${netlist} -cgra ${option}

# place
packed="${netlist%.json}.packed"
$BASEDIR/place.sh ${option} ${cgra} ${packed}
# route
$BASEDIR/route.sh ${option} ${cgra} ${packed}

# produce bitstream
$BASEDIR/bitstream.sh ${option} ${cgra} ${packed}

result="${netlist%.json}.bsb"
echo "save result to ${result}"

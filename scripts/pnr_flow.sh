#!/usr/bin/env bash
set -e

# global variables
is_garnet=0

function print_usage() {
    echo "Usage: $0 [--no-reg-fold] <arch_file> <netlist.json> [<output.bsb>]" >&2
    echo "    if <output.bsb> not specified, it will output <netlist.bsb>" >&2
    echo "    to the same directory as <netlist.json>" >&2
    exit 1
}

function detect_garnet() {
    PATTERN="<CGRA>"
    echo $1;
    if grep -q "${PATTERN}" $1; then
        is_garnet=0;
    else
        is_garnet=1;
    fi
}

if [ "$#" -eq 2 ]; then
    cgra=$1
    netlist=$2
elif [ "$#" -eq 3 ]; then
    if [[ $1 == -* ]]; then
        option=$1
        cgra=$2
        netlist=$3
    else
        cgra=$1
        netlist=$2
        bsb=$3
    fi
elif [ "$#" -eq 4 ]; then
    option=$1
    cgra=$2
    netlist=$3
    bsb=$4
else
    print_usage
fi

if ! [ -f ${cgra} ] || ! [ -f ${netlist} ]; then
    print_usage
fi

BASEDIR=$(dirname "$0")
packed="${netlist%.json}.packed"

# assume user already have the env activated
# pack
python ${BASEDIR}/../packer.py -n ${netlist} -o ${packed} ${option}

# detect if the cgra file is cgra_info from CGRAGenerator or from garnet
detect_garnet ${cgra}

# we internally use the layout representation for the cgra
echo $is_garnet ${cgra}

# place
${BASEDIR}/place.sh ${option} ${cgra} ${packed}
# route
${BASEDIR}/route.sh ${option} ${cgra} ${packed}

# produce bitstream. only vaid for CGRAGenerator based info for now
if [ ${is_garnet} -ne "1" ]; then
    echo "save result to ${bsb}"
    ${BASEDIR}/bitstream.sh ${option} ${cgra} ${packed} ${bsb}

    echo "Analyzing timing..."
    route="${netlist%.json}.route"
    python ${BASEDIR}/../analyzer.py ${cgra} ${netlist} ${route}
fi


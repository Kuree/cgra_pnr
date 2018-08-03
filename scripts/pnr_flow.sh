#!/usr/bin/env bash
set -xe

if [ "$#" -ne 2 ] || ! [ -f "$1" ] || ! [ -f "$2" ]; then
  echo "Usage: $0 <arch_file> <netlist.json>" >&2
  exit 1
fi

BASEDIR=$(dirname "$0")

# assume user already have the env activated
# pack
python $BASEDIR/../packer.py $2 -cgra

# place
packed="${2%.json}.packed"
$BASEDIR/place.sh $1 $packed
# route
$BASEDIR/route.sh $1 $packed

# produce bitstream
$BASEDIR/bitstream.sh $1 $packed

result="${2%.json}.bsb"
echo "save result to $result"

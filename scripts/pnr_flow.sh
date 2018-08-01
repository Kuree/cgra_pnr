#!/usr/bin/env bash

if [ "$#" -ne 2 ] || ! [ -f "$1" ] || ! [ -f "$2" ]; then
  echo "Usage: $0 <arch_file> <netlist.json>" >&2
  exit 1
fi

# assume user already have the env activated
# place
./place.sh $1 $2
# route
./route.sh $1 $2

# produce bitstream
./bitstream.sh $1 $2

result="$(basename "$2" .json).bsb"
echo "save result to $result"

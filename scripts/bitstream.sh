#!/usr/bin/env bash
set -xe

if [ "$#" -ne 2 ] || ! [ -f "$1" ] || ! [ -f "$2" ]; then
  echo "Usage: $0 <arch_file> <netlist.packed>" >&2
  exit 1
fi

# assume user already have the env activated
place="${2%.packed}.place"
if ! [ -f "$place" ] ; then
    echo "$place not found" >&2
    exit 1
fi

route="${2%.packed}.route"
if ! [ -f "$route" ] ; then
    echo "$route not found" >&2
    exit 1
fi

python bitstream.py $1 $2 $place $route

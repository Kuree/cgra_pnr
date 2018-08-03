#!/usr/bin/env bash
set -xe

if [ "$#" -ne 2 ] || ! [ -f "$1" ] || ! [ -f "$2" ]; then
  echo "Usage: $0 <arch_file> <netlist.json>" >&2
  exit 1
fi

# assume user already have the env activated
python random_walk.py $2 -cgra
emb="${2%.packed}.emb"
python place.py $1 $2 $emb -no-vis -cgra

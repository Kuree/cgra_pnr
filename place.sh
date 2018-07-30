#!/usr/bin/env bash

if [ "$#" -ne 2 ] || ! [ -f "$1" ] || ! [ -f "$2" ]; then
  echo "Usage: $0 <arch_file> <netlist.json>" >&2
  exit 1
fi

# assume user already have the env activated
python random_walk.py $2
emb="$(basename "$2" .json).emb"
python place.py $1 $2 $emb

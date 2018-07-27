#!/usr/bin/env bash

if [ "$#" -ne 1 ] || ! [ -f "$1" ]; then
  echo "Usage: $0 <netlist.json>" >&2
  exit 1
fi

# assume user already have the env activated
python random_walk.py $1
python place_sa.py $1

#!/usr/bin/env bash
set -xe
file_dir=$(dirname "$(realpath $0)")
root_dir=$(realpath $file_dir/../)

if [ "$#" -ne 2 ] || ! [ -f "$1" ] || ! [ -f "$2" ]; then
  echo "Usage: $0 <arch_file> <netlist.json>" >&2
  exit 1
fi

# assume user already have the env activated
python ${root_dir}/random_walk.py $2 -cgra
emb="${2%.packed}.emb"
python ${root_dir}/place.py $1 $2 $emb -no-vis -cgra

#!/usr/bin/env bash
set -xe
file_dir=$(dirname "$(realpath $0)")
root_dir=$(realpath $file_dir/../)

if [ "$#" -ne 2 ] || ! [ -f "$1" ] || ! [ -f "$2" ]; then
  echo "Usage: $0 <arch_file> <netlist.json>" >&2
  exit 1
fi

# assume user already have the env activated
place="${2%.packed}.place"
if ! [ -f "$place" ] ; then
    echo "$place not found" >&2
    exit 1
fi

python ${root_dir}/router.py $1 $2 $place -no-vis

#!/usr/bin/env bash
set -e

# deploy everything to serverless
# by default it deploys to aws

function print_usage() {
    echo "Usage: $0 <deploy_package_dir>" >&2
    exit 1
}

if [ "$#" -eq 1 ]; then
    DST_DIR=$1
else
    print_usage
fi

BASEDIR=$(dirname "$0")
ROOTDIR=$(realpath ${BASEDIR}/../)

if [ ! -d ${DST_DIR} ]; then
    mkdir ${DST_DIR}
fi

# first install python packages over
# some pip may need --system, some may not
pip install thunder/ -t ${DST_DIR}

# then copy files that will be used for detailed placement
cp -r ${ROOTDIR}/arch ${DST_DIR}/
cp ${ROOTDIR}/place.py ${DST_DIR}/
cp ${ROOTDIR}/util.py ${DST_DIR}/

pushd ${DST_DIR}
touch serverless.yml

declare -a mem_sizes=("256" "512" "1024" "1600" "2048" "3008")
echo "service: thunder

provider:
   name: aws
   runtime: python2.7
   region: us-west-2

custom:
  serverless-offline:
    port: 4000

functions:"  > serverless.yml
for mem in "${mem_sizes[@]}"
do
   echo \
"   place_${mem}:
     handler: place.detailed_placement_thunder
     timeout: 900
     memorySize: ${mem}
     events:
       - http:
           path: place_${mem}
           method: post" >> serverless.yml
done
popd

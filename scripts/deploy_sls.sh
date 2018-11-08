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
# Keyi: AWS Lambda doesn't like -march=native
# remove it when building packages for lambda
temp_cmake=$(mktemp)
thunder_cmake="thunder/CMakeLists.txt"
cp ${thunder_cmake} ${temp_cmake}
echo "CMakeList.txt backup: ${temp_cmake}"
sed -i -e 's/-march=native//g' ${thunder_cmake}
pip install thunder/ -t ${DST_DIR}
cp ${temp_cmake} ${thunder_cmake}

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
     memorySize: ${mem}" >> serverless.yml
done
popd

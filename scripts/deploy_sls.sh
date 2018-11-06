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
pip install -r ${ROOTDIR}/requirements.txt -t ${DST_DIR} --system
pip install thunder/ -t ${DST_DIR} --system

# then copy files that will be used for detailed placement
cp -r ${ROOTDIR}/placer ${DST_DIR}/
cp -r ${ROOTDIR}/arch ${DST_DIR}/
cp ${ROOTDIR}/place.py ${DST_DIR}/
cp ${ROOTDIR}/util.py ${DST_DIR}/
cp ${ROOTDIR}/visualize.py ${DST_DIR}

pushd ${DST_DIR}
touch serverless.yml
echo "service: threadreaper-place

provider:
   name: aws
   runtime: python2.7

plugins:
  - serverless-offline-python

custom:
  serverless-offline:
    port: 4000

functions:
   place:
     handler: place.detailed_placement_thunder
     events:
       - http:
           path: place
           method: post

   " > serverless.yml

popd

#!/bin/sh
set -e

# thunder
pushd thunder/
python setup.py sdist upload -r pypi
popd

# cyclone
pushd cyclone/
python setup.py sdist upload -r pypi
popd

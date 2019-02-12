#!/bin/sh
set -e

# thunder
cd thunder/
python setup.py sdist upload -r pypi
cd ..

# cyclone
cd cyclone/
python setup.py sdist upload -r pypi
cd ..

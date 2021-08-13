#!/usr/bin/env bash
set -e

if [[ "$OS" == "linux" ]]; then
    if [[ "$BUILD_WHEEL" == true ]]; then
        docker pull keyiz/manylinux-igraph
        docker run -d --name manylinux --rm -it --mount type=bind,source="$(pwd)"/../cgra_pnr,target=/cgra_pnr keyiz/manylinux-igraph bash

        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && python setup.py bdist_wheel'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && auditwheel show dist/*'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && auditwheel repair dist/*'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && pip install wheelhouse/*'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && python setup.py bdist_wheel'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && auditwheel show dist/*'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && auditwheel repair dist/*'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && pip install wheelhouse/*'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/ && pip install pytest && pytest -v tests/'
        docker exec -i manylinux bash -c 'cd /cgra_pnr && mkdir wheelhouse && cp thunder/wheelhouse/* wheelhouse/ && cp cyclone/wheelhouse/* wheelhouse'
    fi

elif [[ "$OS" == "osx" ]]; then
    python --version
    cd thunder && CXX=g++-9 python setup.py bdist_wheel
    pip install dist/*.whl
    cd ..
    cd cyclone && CXX=g++-9 python setup.py bdist_wheel
    pip install dist/*.whl
    cd ..
    pytest -v tests/
    mkdir dist && cp thunder/dist/* dist/ && cp cyclone/dist/* dist/
else
    python --version
    python -m pip install wheel pytest twine
    python setup.py bdist_wheel
    python -m pip install --find-links=dist kratos
    python -m pytest -v tests/
fi

echo [distutils]                                  > ~/.pypirc
echo index-servers =                             >> ~/.pypirc
echo "  pypi"                                    >> ~/.pypirc
echo                                             >> ~/.pypirc
echo [pypi]                                      >> ~/.pypirc
echo repository=https://upload.pypi.org/legacy/  >> ~/.pypirc
echo username=keyi                               >> ~/.pypirc
echo password=$PYPI_PASSWORD                     >> ~/.pypirc

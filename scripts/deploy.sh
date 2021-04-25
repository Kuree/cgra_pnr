#!/usr/bin/env bash
set -e

if [[ "$OS" == "linux" ]]; then
    if [[ "$BUILD_WHEEL" == true ]]; then
        docker cp ~/.pypirc manylinux:/home/
        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && for PYBIN in cp36 cp37; do /opt/python/${PYBIN}-${PYBIN}m/bin/python setup.py bdist_wheel; done'
        # python 3.8+ has different names now
        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && for PYBIN in cp38 cp39; do /opt/python/${PYBIN}-${PYBIN}/bin/python setup.py bdist_wheel; done'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && for WHEEL in dist/*.whl; do auditwheel repair "${WHEEL}"; done'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && twine upload --config-file /home/.pypirc --skip-existing wheelhouse/*'
        # upload the src
        docker exec -i manylinux bash -c 'cd /cgra_pnr/thunder && python setup.py sdist && twine upload --config-file /home/.pypirc --skip-existing dist/*.gz'

        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && for PYBIN in cp36 cp37; do /opt/python/${PYBIN}-${PYBIN}m/bin/python setup.py bdist_wheel; done'
        # python 3.8+ has different names now
        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && for PYBIN in cp38 cp39; do /opt/python/${PYBIN}-${PYBIN}/bin/python setup.py bdist_wheel; done'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && for WHEEL in dist/*.whl; do auditwheel repair "${WHEEL}"; done'
        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && twine upload --config-file /home/.pypirc --skip-existing wheelhouse/*'
        # upload the src
        docker exec -i manylinux bash -c 'cd /cgra_pnr/cyclone && python setup.py sdist && twine upload --config-file /home/.pypirc --skip-existing dist/*.gz'
    fi
fi

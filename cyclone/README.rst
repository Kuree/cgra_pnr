Cyclone
-------

|PyPI version|
|PyPI - Wheel|

Cyclone is a CGRA router as part of PnR system.

Requirement
-----------

-  CMake 3.9+
-  g++-7/clang-6 or above

Install
-------

To install from source, simply do

::

    mkdir build
    cd build
    cmake .. && make -j

Cyclone also has a complete Python binding available, to use the Python
binding, simply do

::

    pip install pycyclone

You can see the example code in ``example`` folder.

.. |PyPI version| image:: https://badge.fury.io/py/pycyclone.svg
   :target: https://badge.fury.io/py/pycyclone
.. |PyPI - Wheel| image:: https://img.shields.io/pypi/wheel/pycyclone.svg

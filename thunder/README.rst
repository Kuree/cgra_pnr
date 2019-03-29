Thunder
-------

|PyPI version|
|PyPI - Wheel|

Thunder is a high-performance CGRA placement engine. It is uses
multi-processing to speed up the placement. Users can also use AWS
lambda to enable high parallelism if desired (C++ lambda invocation
coming soon).

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

Thunder also has a complete Python binding available, to use the Python
binding, simply do

::

    pip install pythunder

You can see the example code in ``example`` folder.

.. |PyPI version| image:: https://badge.fury.io/py/pythunder.svg
   :target: https://badge.fury.io/py/pythunder
.. |PyPI - Wheel| image:: https://img.shields.io/pypi/wheel/pythunder.svg

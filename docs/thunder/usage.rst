Usage
=====

``place.py`` in the root folder shows some examples of how to use
``pythunder``, Thunder’s python binding. The overall placement flow is
as follows:

1. global placement for each computation kernels
2. detailed placement within each kernels
3. global refinement

Depends on what kind of architecture file, you need to use different
arguments to specify. ``-c`` means ``cgra_info.txt``, which is used from
``CGRAGenerator``; ``-l`` means layout file, which can be obtained from
``garnet``.

::

   python place.py -i netlist.packed -c cgra_info.txt -o netlist.placed --no-vis

Here we use ``--no-vis`` to turn off visualization.

Global Placement
''''''''''''''''

First you need to partition the netlist into computation kernels. The
default algorithm is provided by ``leidenalg``:

.. code:: python

   clusters = partition_netlist(netlists)

You can see more details in ``community.py`` to see how to use
``leidenalg`` to partition the netlist into multiple computation
kernels.

Once we have the partitions, we can then proceed to call the global
placer:

.. code:: python

   gp = pythunder.GlobalPlacer(clusters, netlists, fixed_blk_pos, layout)
   gp.solve()
   gp.anneal()

The constructor takes cluster in form of ``Dict[str, Set[str]]``. The
key is cluster ID and the value is a set of block IDs. ``netlists`` is
in form of ``Dict[std, List[Tuple[str, str]]]``, where the key is net ID
and the value is a list of block IDS and ports. ``fixed_blk_pos`` is for
fixed blocks, such as IOs, and layout is the layout class.

Detailed Placement
''''''''''''''''''

By default the detailed placement is carried within the C++ with
multi-processing. It is because Python’s GIL is very tricky to deal with
when you have multi-processing with C++ runtime. Notice that in detailed
placement, since we need to approximate the kernel location, we need to
provide extra centroid information for each clusters.

.. code:: python

   pythunder.detailed_placement(clusters, cells, netlists, fixed_blocks,
                                clb_type,
                                fold_reg,
                                seed)

Global Refinement
                 

This stage is essentially a detailed placement where the scope is the
entire board and no hill-climbing.

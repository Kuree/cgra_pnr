import subprocess
import os
import pytest
import tempfile


# discover the avaiable tests
test_dir = os.path.dirname(os.path.abspath(__file__))
vectors_dir = os.path.join(test_dir, "vectors")
dirnames = os.listdir(vectors_dir)
dirnames = [d for d in dirnames if "partition" in d]


@pytest.mark.parametrize("dirname", dirnames)
def test_pnr(dirname):
    netlist = os.path.join(dirname, "design.packed")

    with tempfile.TemporaryDirectory() as temp:
        # call partition
        # if it has partition set
        partition_file = os.path.join(dirname, "design.part")
        args = ["partition", netlist, temp]
        if os.path.isfile(os.path.join(vectors_dir, partition_file)):
            args += ["-c", partition_file]

        subprocess.check_call(args, cwd=vectors_dir)

        files = os.listdir(temp)
        count = sum([1 for f in files if ".packed" in f])
        assert count >= 2

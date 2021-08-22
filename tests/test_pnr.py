import subprocess
import os
import pytest
import tempfile


# discover the avaiable tests
test_dir = os.path.dirname(os.path.abspath(__file__))
vectors_dir = os.path.join(test_dir, "vectors")
dirnames = os.listdir(vectors_dir)


@pytest.mark.parametrize("dirname", dirnames)
def test_pnr(dirname):
    meta = os.path.join(dirname, "design.info")
    netlist = os.path.join(dirname, "design.packed")
    layout = os.path.join(dirname, "design.layout")

    with tempfile.TemporaryDirectory() as temp:
        placement_file = os.path.join(temp, "design.place")
        route_file = os.path.join(temp, "design.route")
        # call placer
        args = ["placer", layout, netlist, placement_file]
        subprocess.check_call(args, cwd=vectors_dir)
        # call router
        graphs = []
        for i in {1, 16}:
            graphs += ["-g", os.path.join(dirname, "{0}.graph".format(i))]
        args = ["router", "-p", netlist, "-P", placement_file] + graphs + ["-o", route_file]
        print("args", " ".join(args))
        subprocess.check_call(args, cwd=vectors_dir)

        assert os.path.isfile(placement_file)
        assert os.path.isfile(route_file)

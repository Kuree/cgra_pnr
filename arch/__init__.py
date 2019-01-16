from .arch import parse_cgra, parse_vpr, parse_fpga, get_layout
from .netlist import group_reg_nets
from .cgra_packer import load_packed_file
from .cgra_packer import read_netlist_json
from .cgra_analytics import compute_routing_usage
from .cgra_analytics import compute_total_wire, compute_area_usage
from .cgra import parse_placement, save_placement
from .bookshelf import mock_board_meta
from .parser import parse_routing

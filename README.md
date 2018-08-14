PnR
---
Generic place and route tool for CGRA/FPGA.
## Getting started
### Prerequisites
+ GCC 4.0.x and above
+ Python 2.6+/Python 3.5+
### Install
```
$ make
$ pip install -r requirements.txt
```
### Usage
```
$ ./scripts/pnr_flow.sh <cgra_info.txt> <mapped_design.json>
```
Files created in the same directory as `<mapped_design.json>`:
+ `<mapped_design.n2v>`: random walk on the star-expanded netlist graph
+ `<mapped_design.emb>`: netlist embedding computed by `word2vec`
+ `<mapped_design.packed>`: packed netlists, including information on converted netlist as well as id information used internally throughout the toolchain.
+ `<mapped_design.place>`, placement result, using internal id
+ `<mapped_design.route>`, routing result. Each section is the route for a single net. More details see the header section in the result file
+ `<mapped_design.bsb`, bsbuilder files can be compiled to bitstream via `bsbuilder.py` in `CGRAGenerator`

#### FPGA
~~It currently can place FPGA based on a custom format designed for VPR. I will release the modified VPR soon. It uses a different format than the packed CGRA file.~~

Due to the recent changes to the initial placement as well as annealing movement change, I've decided to drop suuport of FPGA in the `master` branch. FPGA code is still accessible in older branches.

### Work in progress
1. Integrate DAG kernel based partition.
2. ~~Use register folding instead of wasting PE tiles for registers that drives more than one net.~~ Done
3. (Maybe) reimplement in C++ for efficiency.

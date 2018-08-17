CGRA PnR [![Build Status](https://travis-ci.org/Kuree/cgra_pnr.svg?branch=master)](https://travis-ci.org/Kuree/cgra_pnr)
---
Generic place and route tool for CGRA/FPGA.
## Getting started
### Prerequisites
+ GCC 4.0.x and above
+ Python 2.7+/Python 3.6+
### Install
```
$ make
$ pip install -r requirements.txt
```
### Usage
```
$ ./scripts/pnr_flow.sh [-no-reg-fold] <cgra_info.txt> <mapped_design.json>
```
`-no-reg-fold` optimizes for the routing path as it turns some registers into PE tiles. Without using `-no-reg-fold` we will have about 15% area reduction, but it may have longer path, based on the current CGRA design. So given timing information as well as more flexible hardware generation in the future, this option needs to be used on a case by case basis.

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
1. ~~Integrate DAG kernel based partition.~~
2. ~~Use register folding instead of wasting PE tiles for registers that drives more than one net.~~ Done
3. (Maybe) reimplement in C++ for efficiency.

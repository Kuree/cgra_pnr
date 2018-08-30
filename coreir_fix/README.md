CoreIR Fix
---
This folder contains scripts that attempt to fix mapped JSON files produced by CGRA Mapper. Because of the current development stage of CGRA Mapper, you may be required to run one of the scripts then proceed to the PnR flow.

1. `fix_mux.py`: fix mux section because there is a disagreement on mux implementation bewteen the actual PE design and CoreIR.
2. `fix_const.py`: fix CoreIR Mapper not be able to duplicate constants:
    - currently it will remove all the formatting in the json file. I will fix it later
3. `fix_smax.py`: fix op debug string error. The CGRA Mapper will try to use `max` instead of `smax` in all cases, which is incorrect.


`fix_all.sh` is a simple script that fixes all the bugs in the netlist file. To see the usage, simply:
```
./fix_all.sh
Usage: ./fix_all.sh <mapped_netlist.json> <fixed_netlist.json>
```

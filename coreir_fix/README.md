CoreIR Fix
---
This folder contains scripts that attempt to fix mapped JSON files produced by CGRA Mapper. Because of the current development stage of CGRA Mapper, you may be required to run one of the scripts then proceed to the PnR flow.

1. `fix_mux.py`: fix mux section because there is a disagreement on mux implementation bewteen the actual PE design and CoreIR.
2. `fix_const.py`: fix CoreIR Mapper not be able to duplicate constants:
    - currently it will remove all the formatting in the json file. I will fix it later

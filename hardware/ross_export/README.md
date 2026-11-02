# Vivado Revision Control Export

This directory is organized for git check-in.

## Check In
- Sources/
- Scripts/
- .gitignore
- README.md
- Sources/Constraints/ (includes DFX pblock constraints if present)
- Sources/Checkpoints/ if present and intentionally versioned
- Sources/NoC/ if present

Note: <proj_name>.xpr is intentionally NOT part of this export or check-in --
this skill recreates the project deterministically via Scripts/build.tcl
instead of revision-controlling the XPR itself.

## Do Not Check In
- .Xil/
- *.jou, *.log, vivado*.backup.*
- dfx_medical.cache/
- dfx_medical.gen/
- dfx_medical.hw/
- dfx_medical.ip_user_files/
- dfx_medical.runs/
- dfx_medical.sim/
- dfx_medical.srcs/

## Recreate
Run Vivado in batch mode with Scripts/build.tcl to recreate the project from the checked-in sources.

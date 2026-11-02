param([ValidateSet('all','csim','hls','rm','implement')][string]$Stage='all')
$ErrorActionPreference='Stop'
$env:PROCESSOR_ARCHITECTURE='AMD64'
$root=([IO.Path]::GetFullPath($PSScriptRoot)).Replace('\','/')
# Use real workspace paths; this build creates no virtual drive mappings.
$env:SURFACE_FIXTURE_ROOT="$root/fixtures/"
Push-Location $PSScriptRoot
try {
 New-Item -ItemType Directory -Force build | Out-Null
 if($Stage -in @('all','csim','hls')) {
  & D:/Xilinx_Project/2026FPGA/.venv_mc/Scripts/python.exe prepare.py --fixtures
  if($LASTEXITCODE){throw 'Reference generation failed'}
  @"
part=xck26-sfvc784-2LV-c
[hls]
flow_target=vivado
syn.top=scope_visual
syn.file=$root/hls/scope.cpp
syn.cflags=-std=c++14
tb.file=$root/hls/testbench.cpp
tb.cflags=-std=c++14
clock=10ns
syn.compile.pipeline_loops=0
package.output.format=ip_catalog
package.output.syn=false
package.output.file=$root/build/hls/ip.zip
"@ | Set-Content -LiteralPath build/scope.cfg -Encoding ascii
  & F:/AMDDesignTools/2025.2.1/Vitis/bin/vitis-run.bat --mode hls --csim --config build/scope.cfg --work_dir build/hls *> build/csim.log
  if($LASTEXITCODE){throw 'C simulation failed'}
 }
 if($Stage -in @('all','hls')) {
  & F:/AMDDesignTools/2025.2.1/Vitis/bin/v++.bat -c --mode hls --config build/scope.cfg --work_dir build/hls *> build/hls.log
  if($LASTEXITCODE){throw 'HLS synthesis failed'}
  & F:/AMDDesignTools/2025.2.1/Vitis/bin/vitis-run.bat --mode hls --cosim --config build/scope.cfg --work_dir build/hls *> build/cosim.log
  if($LASTEXITCODE -or -not (Select-String build/cosim.log -Pattern 'C/RTL co-simulation finished: PASS' -Quiet)){throw 'RTL simulation failed'}
  ((Get-Content build/scope.cfg -Raw)+"`ncosim.random_stall=true`n") | Set-Content -LiteralPath build/random.cfg -Encoding ascii
  & F:/AMDDesignTools/2025.2.1/Vitis/bin/vitis-run.bat --mode hls --cosim --config build/random.cfg --work_dir build/hls *> build/cosim_random.log
  if($LASTEXITCODE -or -not (Select-String build/cosim_random.log -Pattern 'C/RTL co-simulation finished: PASS' -Quiet)){throw 'Random-stall RTL simulation failed'}
  & F:/AMDDesignTools/2025.2.1/Vitis/bin/vitis-run.bat --mode hls --package --config build/scope.cfg --work_dir build/hls *> build/package.log
  if($LASTEXITCODE){throw 'IP package failed'}
 }
 if($Stage -in @('all','rm')) {
  & F:/AMDDesignTools/2025.2.1/Vivado/bin/vivado.bat -mode batch -source build_rm.tcl -log build/rm.log -journal build/rm.jou
  if($LASTEXITCODE){throw 'RM synthesis failed'}
 }
 if($Stage -in @('all','implement')) {
  & F:/AMDDesignTools/2025.2.1/Vivado/bin/vivado.bat -mode batch -source implement.tcl -log build/implement.log -journal build/implement.jou
  if($LASTEXITCODE){throw 'Implementation failed'}
 }
} finally {Pop-Location}

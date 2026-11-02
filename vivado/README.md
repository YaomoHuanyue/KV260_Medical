# KV260 Medical：独立Vivado工程

使用 **Vivado 2025.2.1**，器件 `xck26-sfvc784-2LV-c`，板卡文件 `kv260_som 1.4`。

## 直接打开

打开 `project/KV260_Medical.xpr`。在左侧Sources展开 `system_top → system_ps_wrapper → system_ps`，双击 `system_ps.bd`，或使用Flow Navigator中的Open Block Design。

实际BD文件是：

`project/KV260_Medical.srcs/sources_1/bd/system_ps/system_ps.bd`

BD包含PS、控制/内存SmartConnect、DFX读写搬运器、双向AXI Shutdown Manager、GPIO、复位与常量，共11个IP块。端口及地址与冻结平台一致，AXIS数据宽度512位，PL时钟100 MHz。

Sources中另有 `algorithm_mc.bd`，实际路径 `project/KV260_Medical.srcs/sources_1/bd/algorithm_mc/algorithm_mc.bd`。它实例化本轮WSL编译生成的MC IP，展示输入/输出AXIS、AXI-Lite控制、时钟、复位和中断。这是计算核接口查看入口；生产DFX模块仍用已通过综合布线的RTL边界适配器，主顶层仍为 `system_top`。

## 目录

| 目录/文件 | 内容 |
|---|---|
| `project` | 已实际生成的XPR、BD、IP实例和wrapper，可直接打开 |
| `hardware/ross_export/Sources/BD` | 主BD的可重建Tcl |
| `hardware/ross_export/Sources/RTL` | 顶层、静态保护逻辑、DFX分区端口声明 |
| `dfx/medical/ip` | 静态读写搬运器的完整IP仓库 |
| `hardware/static/floorplan.tcl` | 冻结DFX分区的物理约束生成逻辑 |
| `hardware/rm` | 9个医疗动态模块的独立工程生成脚本 |
| `hardware/hls_targets.json` | 11个HLS核、顶层函数和源文件清单 |
| `modules`、`accelerators`、`dfx` | 对应的HLS C++、头文件和RM绑定生成器 |
| `hardware/frozen` | 冻结静态DCP与完整PR参考配置 |
| `checkpoints/ct_cf5_routed.dcp` | 当前cf5 CT核心的实际完整布线设计，包含真实PL计算单元 |
| `checkpoints/mc_axis8_candidate.dcp` | 本轮WSL实际完成的MC动态配置布线设计 |
| `checkpoints/static_source_synth.dcp` | 本轮静态源工程实际综合结果 |
| `ip_repo/binary_mc_axis` | 本轮HLS实际生成的完整MC IP |
| `firmware_candidates/MC_axis8` | 本轮MC候选位流，未替换正式板卡固件 |
| `reports` | 本次MCP检查，以及与冻结位流相对应的历史来源记录 |

主BD是DFX静态平台。医疗算法位于顶层 `rp` 动态分区，不会把所有算法同时画进静态BD。`rm_stub.v` 是源工程的分区接口声明；真正的算法实现见动态模块源码和布线检查点。

## 查看真实CT硬件

关闭源工程后，通过File → Checkpoint → Open，打开 `checkpoints/ct_cf5_routed.dcp`；或在Ross会话执行 `source /path/to/this_folder/open_current_CT.tcl`。在Implemented Design的Netlist/Schematic中查看 `rp` 下的计算层次和实际资源。

该DCP的SHA256为 `9c5a7481103b60e9746adba711c4ca5bfbedbd05d57d65236b8a3dc61a589dcd`，对应当前cf5局部位流。来源证明保存在 `reports/baseline_bit_generation_verified.json`。

`generate_current_CT_bit.tcl` 可从该冻结布线设计重新生成位流，不重新布线、不安装到板卡。它与“从修改后的HLS源码重新综合实现”是两个构建入口。

## 从源码重建

在空Vivado会话中，通过AMD Ross MCP执行 `source /path/to/this_folder/create_project.tcl`。脚本从自身位置定位全部项目源文件；无需依赖其他工程文件夹。已有XPR时使用 `open_project.tcl`，创建脚本会拒绝覆盖已有工程。

静态BD采用Global Synthesis，确保VHDL/Verilog的IP实现进入源编译列表，支持Open Elaborated Design。

动态模块：先用 `scripts/run_hls.py <target> csynth --tools <Vitis目录>` 综合，再用同一入口的 `package` 打包；随后在Ross会话依次运行对应的 `hardware/rm/<target>.tcl`、`hardware/synthesize_rm.tcl` 和 `hardware/implement_rm.tcl`。通过环境变量 `KV260_RM_TARGET` 指定目标。CT模块需要先准备ct_reader、ct_conv、ct_writer三个HLS核。

DFX继续采用原有冻结静态区和独立RM实现流程。本次未把9个模块改造成新的Project-Mode PR配置，也未更换板卡的固件。

## 验证范围

本次使用官方AMD Ross MCP实际生成XPR、BD及IP输出，执行BD验证和工程路径检查。详细结果、修复记录及尚未重复执行的项目见 `reports/VALIDATION.md`。历史布线证明保留原始结论和日期，不记作本次重新布线。

私人服务器的Ubuntu 24.04 WSL2已完成静态源工程综合，以及MC的845项C仿真、HLS综合、RM综合、DFX布局布线、单份完整黄金配置PR校验和位流生成。MC在100 MHz下最终建立余量2.306 ns、保持余量0.010 ns。本轮未重新实现全部9个RM，未测试新候选的板卡性能。远端本任务文件已全部取回校验，WSL/Windows暂存目录和进程已清理。

第三方Ross helper保持官方固定提交 `2cdc9eef1b6b5b17fa45f5e4d468e5483a1c92de` 的原始内容，许可见 `tools/amd_ross/LICENSE`。检查点如需推送Git，应先安装Git LFS。

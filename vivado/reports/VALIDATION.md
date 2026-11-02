# 独立 Vivado 工程验证

日期：2026-11-02（电脑时区；服务器原始日志为2026-11-03）。官方AMD Ross工作流；Vivado/Vitis 2025.2.1，Vivado SW Build 6403652。

## 实际工程

主工程 project/KV260_Medical.xpr 已生成并实际关闭、从磁盘重开。器件xck26-sfvc784-2LV-c，顶层system_top，PR_FLOW=1；外部源文件路径为0。

system_ps.bd含11个IP，algorithm_mc.bd含1个本轮HLS生成的MC IP。两个BD强制校验和输出生成均通过，采用Global Synthesis。主BD的SmartConnect自动配置和PS AXI USER宽度警告保留。

MC BD是独立的计算核接口查看入口，未接入静态主顶层。生产RM继续使用实际综合布线的RTL边界适配器。静态源工程的rp为明确的DFX分区黑盒；9个算法不同时实例化在主BD。

当前cf5 CT完整布线DCP与原位流生成记录的SHA256一致；见baseline_bit_generation_verified.json。这是历史已接受的CT物理设计，本轮未重新布线。11个HLS核、9个RM源码与入口已独立收集。

## 本轮真实构建

| 检查 | 实际环境与结果 |
|---|---|
| 静态源工程RTL展开 | 本地Windows，Ross MCP，通过；167.296秒，日志峰值约4588 MB |
| 静态源工程综合 | 私人服务器Ubuntu 24.04 WSL2，Ross MCP；synth_1完成100%，保存static_source_synth.dcp；rp黑盒符合分区边界 |
| MC C仿真 | WSL2，官方vitis-run；845项检查通过 |
| MC HLS综合和打包 | WSL2，官方v++/vitis-run；通过，分别23.347秒、13.016秒 |
| MC RM RTL综合 | WSL2，Ross MCP；通过，无未解析黑盒 |
| MC DFX opt/place/route | WSL2，Ross MCP，冻结静态DCP；通过，0条失败、未布线、重叠网络 |
| 最终时序 | RP时钟10.000 ns；WNS 2.306 ns，WHS 0.010 ns |
| PR兼容校验 | 与保留的1份完整黄金MC配置比较通过，未重新执行全部RM两两比较 |
| 位流生成 | 完整及局部位流生成，DRC 0 errors；partial.bin为7,868,904字节 |
| 结果取回 | 3791个自有任务成员流式校验，3130个普通文件SHA256全部通过；3份DCP ZIP CRC通过 |

MC动态分区实际资源：LUT 11540、FF 10229、RAMB36 17、RAMB18 7、URAM 0、DSP 18。见wsl/mc/RP_utilization.rpt。最终原生时序查询和MCP请求结果见WSL_MCP_signoff.json，本地BD验证见MCP_final_project.json。

## 环境修复与失败

- 初次RTL展开因BD OOC未把VHDL IP实现纳入全局编译，失败3次；改Global Synthesis后通过。算法RTL未改。初始诊断在.vivado-ai/elaboration_initial/vivado_agentic_ai_reports/rtl-elaboration-analysis/REPORT.md。
- 展开有大量生成IP未用端口警告，计数见elaboration_warning_summary.json。本轮未完成全部警告审计。
- WSL缺en_US.UTF-8、make和C开发头文件。只在本任务目录生成私有locale、下载解包依赖；没有全局安装。C仿真先后因make、features.h、include_next次序失败，最终使用私有-idirafter和链接搜索路径通过。CLI参数与失败记录保留。
- Vivado内部调用宿主Python受到PYTHONHOME/PYTHONPATH污染，首次RM创建失败，后续错误调用出现No open project；构建脚本使用python -E后，实际创建及综合布线通过。数值算法未改。
- 所有构建、时序和位流检查通过后，MCP关闭远端Vivado；外层包装进程记录exit 134。此为关停阶段异常，不记作干净exit 0；原始wsl/vivado_ended.json保留。最终DCP CRC、时序和位流产物独立通过。
- 最终本地第一次重开被MCP重复命令缓存跳过，后续校验报No open project；更换等价命令后实际打开并校验通过，原会话保留失败记录。
- Tcl模式write_bd_layout要求GUI，未生成SVG。实际BD和布局已保存，可用Vivado图形界面打开。

## 范围与清理

本轮未执行新MC的RTL协同仿真、板卡性能和数值回归，未重新实现全部9个RM，未更换冻结静态区，未编程板卡或改变正式医疗服务。新位流放在firmware_candidates中。

远端任务文件全部取回并流式校验后，保留117份必要报告/候选文件的紧凑归档及可直接使用的工程产物，没有解压完整编译工作区。本任务WSL/Windows目录和进程已清理；其他服务器文件、进程未改动。凭据未纳入独立工程。

官方技能：vivado-revision-control 1.0.0、hls-run-flow 1.0.0、vivado-rtl-elaboration-analysis 1.0.0。固定上游提交2cdc9eef1b6b5b17fa45f5e4d468e5483a1c92de保持不变。Vivado操作通过官方Ross MCP，HLS通过技能规定的CLI，原始请求/结果和命令记录保留。

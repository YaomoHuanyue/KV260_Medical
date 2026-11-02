# FPGA构建

固定器件 `xck26-sfvc784-2LV-c`，Vivado/Vitis `2025.2.1`，PL时钟100 MHz，公共RP边界67组端口/1830位。

## 静态工程还原

在AMD Ross Vivado MCP的ipi会话中执行：

```tcl
source /path/to/checkout/hardware/ross_export/Scripts/build.tcl
```

这会生成 `build/ross_project/dfx_medical.xpr`。脚本、IP仓库和RTL均从checkout相对定位；不需要原来的2026FPGA目录。
也可执行 `hardware/static/create_project.tcl` 从原始参数还原静态设计，输出 `build/fpga_static/project`。

`KV260_CREATE_ONLY=1` 用于仅还原工程结构，不预生成全部IP输出；后续综合会重新生成。默认完整生成。
`PYTHON`可指定Python可执行程序，未设置时使用PATH中的`python`。

静态XPR用于BD/RTL编辑与综合；当前DFX实现沿用已经冻结的静态布线检查点，不通过空RM冒充医疗算法。

## HLS核

以HU量化为例：

```bash
python scripts/run_hls.py hu32 csim --tools /opt/amd/2025.2.1/Vitis
python scripts/run_hls.py hu32 csynth --tools /opt/amd/2025.2.1/Vitis
python scripts/run_hls.py hu32 cosim --tools /opt/amd/2025.2.1/Vitis
python scripts/run_hls.py hu32 package --tools /opt/amd/2025.2.1/Vitis
```

Windows可把 `--tools` 改为实际安装的Vitis目录。也可设置 `AMD_VITIS_ROOT`。
配置与输出位于 `build/hls/<target>`；未把本机安装盘符写进Git构建入口。
HU测试用LUT由脚本确定性生成，不包含患者CT。其他测试台若需要外部fixture，应按原测试台的环境变量提供；综合和IP打包不依赖患者数据。

CT动态模块包含 `ct_reader`、`ct_conv`、`ct_writer` 三个HLS核，先分别综合并打包。其他模块与核的对应关系见 `hardware/rm_targets.json`。

## 动态模块

在Ross会话中逐条执行（示例HU）：

```tcl
set ::env(PYTHON) /usr/bin/python3
set ::env(KV260_RM_TARGET) hu32
source /path/to/checkout/hardware/rm/hu32.tcl
source /path/to/checkout/hardware/synthesize_rm.tcl
source /path/to/checkout/hardware/implement_rm.tcl
```

每个模块先创建真实HLS核的工程，再综合并检查未解析黑盒。实现读取 `hardware/frozen/static_routed.dcp`，把综合结果接入 `rp`，检查建立/保持时间和PR比较后才生成候选位流。
结果写入 `build/rm/<target>`。对于保留原组件输出约定的BD生成器，中间文件还会写入相应模块的 `build` 目录；这些目录不入Git。

此最小包保留一个完整黄金配置用于PR比较。原五配置完整PR与板测证据属于冻结版本历史；新候选若要替换正式版本，应重新执行项目要求的完整验证。脚本不会自动安装候选或加载板卡。

# 完整表面数据与导航交接 R8 验证结果

已完成四种原始表面的八份完整包：四份 1 mm 弯曲约束路径和四份根点路径。每份同时绑定实际 PL C1 网格、原 Q5/Q6 标量、新路径、相机、分岔标签及同一路径的 HUD。Windows/ARM 的 C9 数据包字节一致，网格坐标与索引一致；路径/相机全量对照通过。

Windows 和 ARM 各通过 19 项绑定/交互队列测试、4 项便携读取误差边界测试，以及完整场景 worker 准备合同。严格相机轴逐位比较的跨平台浮点尾差保留在记录中；便携读取器只允许 1e-12 的方向尾差，相机位置仍完全一致。

八个 640×363、最多 1023 步的自动对齐/手动镜头在 ARM 上完成 PS1/PS4 对照，全部 64 位像素完全一致。PS4 调用中位数约 0.915—1.185 秒/帧，测试进程峰值 RSS 约 557.8 MiB。此数不是完整界面帧率、产品内存峰值或 PL 加速比。第一次参考脚本的语法失败保留；成功结果来自 reference_frames_r8b.py。

当前 HDMI 默认版本未替换，没有加载新的静态或部分位流。板卡当前启动仍是 starter-kit 外壳，医疗 UI 未运行。R8 是完成的数据准备与交接接口，原生 Qt 接入、当前启动上的实际 C9 同输入加速对照和实机交互验收仍未完成。

代码目录：本地 D:\Xilinx_Project\2026FPGA\kv260_system\modules\surface_route；板端 /home/ubuntu/jupyter_notebooks/KV260_System/modules/surface_route。

详细接口见 README_COMPLETE_SCENES_r8.md。便携读取使用 bundle_reader_r8b.py / compare_bundles_r8b.py；成功的 ARM 参考渲染入口为 reference_frames_r8b.py。最终状态及完整 SHA 绑定见 work_checkpoint_r8.json。所有场景、镜头和参考像素保留；本轮传输 ZIP 在两端校验负载后清除。

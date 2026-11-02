# 原概率/SDF 表面与导航：R6—R7

本地工程：`D:\Xilinx_Project\2026FPGA\kv260_system`。
板端工程：`/home/ubuntu/jupyter_notebooks/KV260_System`。
本批仍为独立候选，完整默认界面尚未接入这些表面。

## 本批修改

直接使用已与原 Python 算法逐体素对照的四份标量场：二值气道和网络概率各有 Q5、Q6 两档。原等方重采样、概率修正、轴向与 SDF 平滑、14 步全局体积偏移不变。C9 的远处负值压缩经过逐条零交叉边检查，不移动 MC 使用的边交点。

R6 在实板用现有 C1 提取每份 `q > 0` 的三角形，两次输出逐字节一致。PS 仅把 PL 边中点插值到同一标量场的零交叉位置，没有 PS Marching Cubes、补洞或新三角形。

R6 发现三个模型各有一条四面共边。原始 PL 二值拓扑正常；问题来自量化零点重合后，按坐标去重把不同的内部扇形连接环焊在一起。R7 按原 PL 三角形的有向环保留各环的中心索引，再分开互不连接的顶点邻域。

每个保留三角形的三个有序坐标与 R6 完全相同；标量场、面数、面方向和原先的零面积三角形删除结果不变。所有顶点邻域必须是闭环或开放扇形，并再次通过未修改的 `MeshRegion` 检查。几何上的自接触仍保留，不能把索引检查解释成消除了自交或获得临床安全证明。

| 标量场 | 精度 | 保留三角形 | 新增重合索引 |
|---|---|---:|---:|
| 二值气道 | Q5 | 91,063 | 2 |
| 二值气道 | Q6 | 91,617 | 4 |
| 网络概率 | Q5 | 89,553 | 3 |
| 网络概率 | Q6 | 90,118 | 0 |

## 导航约束

仍使用原始中心线森林、目标选择、加权 Dijkstra、80%/最多 8 次前缀策略、物理弧长平滑和相机规则。部分无关分支点在新表面外不会拒绝整个模型；每条候选边和最终曲线都必须重新通过实际三角形管壁、裁剪面及源气道掩膜区间检查。

四组表面各测试 0、1、10 mm 弯曲约束，共 12 组。1 mm 档的路径为 891 点、169.439660 mm，末端距选定候选区域约 79.370953 mm，仍是有限到达。可行路径保留三个选定出口，根点路径不生成前进标记。引导标签严格绑定本份标量场，目标分支选择与更新后路径一致。

## PS/PL 分工与时间范围

* PL：R6 实板 C1 的二值拓扑提取；复用现有位流，没有新硬件资源变化。
* PS：标量边插值、精确重合点索引、一次性几何审核、稀疏路径规划、相机和引导标签准备。
* 现有 C9：可消费相同 Q5/Q6 标量；这批新表面与新路径的完整界面及实际逐帧 PS/PL 对照仍需完成。

R6 四组暖态 C1 核心约 70.1—77.0 ms，完整 C1 主机调用约 134.2—148.1 ms。此数不包含字段生成、R7 索引检查、路径准备或 UI，不是新的完整流程加速比。R7 检查包含文件绑定及两次完整顶点邻域审核，属于准备阶段，不应放入每帧循环；后续仍应优化其准备开销。

## 代码与验收证据

* `modules/surface_quality/scalar_mesh_r7.py`：保持原插值，加入索引处理。
* `modules/surface_quality/scalar_mesh_indexing_r7.py`：PL 扇形环及顶点邻域。
* `modules/surface_quality/test_scalar_mesh_indexing_r7.py`：六组正常、重合与拒绝测试。
* `modules/surface_route/original_surface_mesh_r6.py`：实板 C1 提取与完整输入绑定。
* `modules/surface_route/diagnose_original_mesh_r6.py`：区分原 PL 与插值后拓扑。
* `modules/surface_route/original_mesh_indexing_trial_r7.py`：四组原表面的精确几何检查。
* `modules/surface_route/original_surface_replan_r7.py`：四组表面的新路径、相机和引导。
* `modules/surface_route/compare_original_surfaces_r7b.py`：Windows/ARM 全量对照。
* `modules/surface_route/work_checkpoint_r7.json`：最终状态及源码、证据绑定。

R6 原始板端提取证据位于 `modules/surface_route/results/original_surface_mesh_ARM_r6`。R7 网格证据分别位于 `original_mesh_indexing_Windows_r7` 与 `original_mesh_indexing_ARM_r7`；路径证据位于 `original_surface_replan_Windows_r7` 与 `original_surface_replan_ARM_r7b`。中断的首次 ARM 路径输出保留为 `original_surface_replan_ARM_r7`，没有完成声明。

## 后续接入

把同一标量、完整 PL 网格、受约束路径、相机和引导作为一个完整包交给界面；不能混用旧模型与新路径。随后补齐新包的实际 C9/PS 同输入逐帧验证、原生界面回归与实机交互验收。原 Python 的其他显示及导出缺口、profile 和平滑核心的完整 API 性能目标仍在总任务范围内。

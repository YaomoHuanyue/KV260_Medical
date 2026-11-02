# 软件与部署

## 系统依赖

目标为aarch64 Ubuntu 24.04，原验证环境使用g++13.3、Qt5.15、XRT及Mali驱动。
Python运行依赖见根目录 `requirements.txt`。创建自己的Python虚拟环境，不复制开发电脑/板卡的 `.venv`。
本机ARM库编译还需要XRT开发头文件和 `libxrt_coreutil`。

## 原生程序

```bash
python3 scripts/build_software.py --jobs 2
python3 scripts/build_native.py --list
```

前端构建同时执行控件检查和181项手柄/镜头断言。测试使用offscreen和测试数据，不加载PL或占用真实手柄。
本机库入口按已保留的真实g++记录构建候选，输出在 `build/native`，不会覆盖当前通过SHA绑定的ARM库。

后端检查在装有Python依赖的环境中执行：

```bash
python scripts/check_backend.py
```

这是调度和准入读取验证，不执行CT计算、不创建XRT Session。

## 实机部署

正式运行需要已验收的静态平台、局部位流、XRT与Mali环境。`dfx/medical/release`及模块各自release目录保存必要固件和对应清单，均通过LFS取得。
保留的原生库是已验收版本；构建新的库后需要按对应模块完成验收，再更新发布绑定。

既有系统的固定安装位置为 `/home/ubuntu/jupyter_notebooks/KV260_System`。硬件安装/系统服务脚本中的这个位置属于板端部署约定，不能当作另一份源码目录依赖。
源码构建与本次隔离验证均可在其他目录完成。部署时可先生成完整安装目录，再在维护窗口替换正式版本。

先将自己的CT放入 `data/`，执行 `python scripts/configure_case.py --ct data/CT.nrrd`，生成本机启动配置并建立运行锁目录。示例配置见 `system/autostart/profile.example.json`。不要直接复用历史病例路径。

选择V3前端，并提供自己的CT：

```bash
sudo .venv/bin/python -B ui/v3/runtime.py --input /absolute/path/inside/project/data/CT.nrrd
```

启动器要求输入在项目目录内。新工程不带原始CT及旧病例结果，应先复制CT到被Git忽略的 `data/`，首次进入后执行完整处理。
开机服务管理代码保留在 `system/autostart`。服务配置中的输入、结果目录和SHA应按实际病例生成，不复用开发板旧病例路径。

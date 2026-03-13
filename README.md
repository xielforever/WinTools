# WinTools

WinTools 是一个基于 Python + tkinter + ttk 的 Windows 桌面工具集。
当前已实现可扩展主框架、分类导航与模块状态占位，并上线 2 个可用模块。

## 文档

- 设计文档：[docs/设计文档.md](docs/设计文档.md)
- 进度跟踪：[docs/进度跟踪.md](docs/进度跟踪.md)
- 发布说明：[docs/发布说明.md](docs/发布说明.md)

## 运行环境

- Windows
- Python 3.13+

## 启动方式

```bash
python main.py
```

## 当前状态（v0.1.2）

- 左侧分类导航（文件管理 / 网络工具 / 安全工具 / 系统维护 / 效率辅助）
- 模块状态标识（`[可用]` / `[规划-P1/P2]` / `[Beta]`）
- 规划模块占位页（点击后展示目标能力、阶段与典型场景）
- 分类展开/收起状态记忆与上次模块选择记忆（运行时保存）
- 底部状态栏显示运行状态
- 伪玻璃主题（轻透明窗口 + 浅色叠层卡片）

## 已实现模块

### 文件管理

1. 目录大小统计
- 仅展示当前层级（根目录 + 直接子目录）
- 每行大小按递归总大小计算，结果按大小降序
- 后台线程扫描，不阻塞 UI，支持手动停止
- 支持多结果页、右键深入扫描、打开位置、历史趋势分析
- 每次扫描写入 SQLite：`data/dir_size_history.db`

2. 大文件定位与清理
- 按阈值扫描大文件，支持实时命中刷新
- 基于目录大小快照进行可靠剪枝（有快照才剪枝，无快照不漏检）
- 状态栏显示扫描文件数 / 命中数 / 剪枝目录数 / 异常数

## 分类规划（占位已接入）

- 文件管理：重复文件检测（P1）、空目录清理（P1）、下载目录归档（P2）
- 网络工具：网络连通诊断（P1）、端口检测（P1）、网络快照对比（P2）、代理/Hosts 切换（P2）
- 安全工具：启动项与计划任务巡检（P1）、可疑文件扫描（P1）、系统加固检查（P2）、进程外联巡检（P2）
- 系统维护：临时文件清理（P1）、服务状态检查（P2）、磁盘健康预警（P2）
- 效率辅助：结果导出（P1）、任务模板（P2）、一键诊断报告（P2）

## 数据持久化说明

当前持久化后端为 SQLite，主要数据表：

- `scan_runs`：记录每次扫描的根目录信息、扫描时间、总大小等
- `scan_top_dirs`：记录每次扫描结果中的目录行（根目录 + 直接子目录），用于趋势分析

说明：

- 历史 `jsonl` 文件保留，但不再作为读写数据源
- 趋势分析基于 SQLite 历史数据进行查询

## 打包与发布（Windows）

### 本地构建（同时产出 OneDir ZIP + OneFile EXE）

```powershell
./scripts/build.ps1 -Version v0.1.2
```

产物位置：

- `dist/WinTools-v0.1.2-windows-onedir.zip`
- `dist/WinTools-v0.1.2-windows-onefile.exe`

### GitHub Release

- 自动触发：推送标签 `vMAJOR.MINOR.PATCH`（例如 `v0.1.2`）
- 手动触发：Actions -> `Release` -> `Run workflow`，输入 `version_tag`
- 版本真源：Git Tag（仅允许 `vMAJOR.MINOR.PATCH`）
- 最新发布：`v0.1.2`

## 后续扩展方式

1. 在 `modules/<new_module>/` 下新增 `ui.py` 与 `core.py`
2. 在 `wintools/module_registry.py` 中注册模块
3. 模块实现 `wintools/base.py` 的 `BaseModule` 接口

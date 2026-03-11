# WinTools

WinTools 是一个基于 Python + tkinter + ttk 的 Windows 桌面工具集。
当前已实现可扩展主框架，以及第一个模块：目录大小统计。

## 运行环境

- Windows
- Python 3.13+

## 启动方式

```bash
python main.py
```

## 当前功能

- 左侧模块导航 + 右侧功能区
- 左侧显示当前工具说明
- 底部状态栏显示运行状态
- 目录大小统计（仅展示当前层级：根目录 + 直接子目录）
- 每行大小按递归总大小计算
- 结果按大小默认降序
- 扫描在后台线程执行，不阻塞 UI
- 支持手动停止扫描
- 支持右键深入扫描子目录
- 支持右键打开目录所在位置
- 支持右键分析目录历史趋势（弹窗显示折线图和明细）
- 支持多结果页（选项卡）查看与关闭管理
- 每次扫描结果写入 SQLite：`data/dir_size_history.db`

## 数据持久化说明

当前持久化后端为 SQLite，主要数据表：

- `scan_runs`：记录每次扫描的根目录信息、扫描时间、总大小等
- `scan_top_dirs`：记录每次扫描的 Top 子目录数据（默认前 20）

说明：

- 历史 `jsonl` 文件保留，但不再作为读写数据源
- 趋势分析基于 SQLite 历史数据进行查询

## 后续扩展方式

1. 在 `modules/<new_module>/` 下新增 `ui.py` 与 `core.py`
2. 在 `wintools/module_registry.py` 中注册模块
3. 模块实现 `wintools/base.py` 的 `BaseModule` 接口
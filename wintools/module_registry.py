from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Literal, Optional, Type

from modules.dir_size.ui import DirSizeModule
from modules.large_files.ui import LargeFilesModule
from wintools.base import BaseModule

ModuleStatus = Literal["available", "planned", "beta"]
ModulePriority = Literal["available", "P1", "P2"]


@dataclass(frozen=True)
class ModuleMeta:
    id: str
    name: str
    category: str
    status: ModuleStatus
    priority: ModulePriority
    description: str
    module_cls: Optional[Type[BaseModule]] = None
    tags: tuple[str, ...] = ()
    audience: Literal["personal", "enterprise", "both"] = "both"
    available: bool = False
    scenarios: tuple[str, ...] = field(default_factory=tuple)
    sort_order: int = 0


def get_module_catalog() -> list[ModuleMeta]:
    # Declaration order controls rank when priority is the same.
    return [
        # 文件管理
        ModuleMeta(
            id="dir-size",
            name=DirSizeModule.name,
            category="文件管理",
            status="available",
            priority="available",
            description=DirSizeModule.description,
            module_cls=DirSizeModule,
            available=True,
            scenarios=("快速识别空间占用热点", "对比同目录历史增长趋势"),
            sort_order=1,
        ),
        ModuleMeta(
            id="large-files",
            name=LargeFilesModule.name,
            category="文件管理",
            status="available",
            priority="available",
            description=LargeFilesModule.description,
            module_cls=LargeFilesModule,
            available=True,
            scenarios=("定位阈值以上的大文件", "结合目录快照减少无效扫描"),
            sort_order=2,
        ),
        ModuleMeta(
            id="dup-files",
            name="重复文件检测",
            category="文件管理",
            status="planned",
            priority="P1",
            description="按内容哈希识别重复文件，支持按目录/类型筛选并生成清理建议。",
            scenarios=("释放冗余存储空间", "归档前去重"),
            sort_order=3,
        ),
        ModuleMeta(
            id="empty-dir-cleaner",
            name="空目录清理",
            category="文件管理",
            status="planned",
            priority="P1",
            description="扫描并清理空目录，支持白名单和预览删除清单。",
            scenarios=("清理构建残留目录", "规范工程目录结构"),
            sort_order=4,
        ),
        ModuleMeta(
            id="downloads-organizer",
            name="下载目录归档",
            category="文件管理",
            status="planned",
            priority="P2",
            description="按类型/时间自动整理下载目录，支持归档规则模板。",
            scenarios=("减少下载目录混乱", "按周期归档文件"),
            sort_order=5,
        ),
        # 网络工具
        ModuleMeta(
            id="net-diagnose",
            name="网络连通诊断(Ping/DNS/路由)",
            category="网络工具",
            status="planned",
            priority="P1",
            description="一键诊断连通性、DNS 解析和路由路径，输出可读报告。",
            scenarios=("排查无法访问网站", "定位 DNS 或网关问题"),
            sort_order=1,
        ),
        ModuleMeta(
            id="port-inspector",
            name="端口检测与占用分析",
            category="网络工具",
            status="planned",
            priority="P1",
            description="检测端口连通与本机占用进程，帮助快速定位冲突服务。",
            scenarios=("端口被占用排查", "服务监听状态检查"),
            sort_order=2,
        ),
        ModuleMeta(
            id="net-snapshot",
            name="网络配置快照与对比",
            category="网络工具",
            status="planned",
            priority="P2",
            description="保存网卡、路由、DNS 配置快照并支持差异比对。",
            scenarios=("升级前后网络配置核对", "故障回溯"),
            sort_order=3,
        ),
        ModuleMeta(
            id="proxy-hosts-switch",
            name="代理/Hosts 快速切换",
            category="网络工具",
            status="planned",
            priority="P2",
            description="集中管理代理与 Hosts 配置，支持一键切换场景模板。",
            scenarios=("开发/测试环境切换", "临时代理启停"),
            sort_order=4,
        ),
        # 安全工具
        ModuleMeta(
            id="startup-task-audit",
            name="启动项与计划任务巡检",
            category="安全工具",
            status="planned",
            priority="P1",
            description="巡检开机启动项与计划任务，识别异常来源并给出处置建议。",
            scenarios=("排查开机变慢", "识别可疑持久化项"),
            sort_order=1,
        ),
        ModuleMeta(
            id="suspicious-file-scan",
            name="可疑大文件与高风险扩展名扫描",
            category="安全工具",
            status="planned",
            priority="P1",
            description="扫描大体积可疑文件和高风险扩展名，聚焦快速初筛。",
            scenarios=("下载后风险初筛", "盘点潜在威胁文件"),
            sort_order=2,
        ),
        ModuleMeta(
            id="hardening-check",
            name="常见系统加固检查",
            category="安全工具",
            status="planned",
            priority="P2",
            description="检查基础安全配置并输出加固建议清单。",
            scenarios=("基础安全体检", "上机前加固核对"),
            sort_order=3,
        ),
        ModuleMeta(
            id="process-network-audit",
            name="外联地址与进程关联巡检",
            category="安全工具",
            status="planned",
            priority="P2",
            description="关联进程与网络外联地址，支持按风险规则筛选。",
            scenarios=("可疑外联排查", "进程网络行为审计"),
            sort_order=4,
        ),
        # 系统维护
        ModuleMeta(
            id="temp-cleaner",
            name="临时文件与缓存清理",
            category="系统维护",
            status="planned",
            priority="P1",
            description="扫描系统与应用缓存，支持安全清理与空间回收预估。",
            scenarios=("系统瘦身", "缓存暴涨排查"),
            sort_order=1,
        ),
        ModuleMeta(
            id="service-check",
            name="服务状态检查与一键修复建议",
            category="系统维护",
            status="planned",
            priority="P2",
            description="检查关键系统服务状态，输出可执行修复建议。",
            scenarios=("服务异常恢复", "开机服务健康巡检"),
            sort_order=2,
        ),
        ModuleMeta(
            id="disk-health",
            name="磁盘健康与空间预警",
            category="系统维护",
            status="planned",
            priority="P2",
            description="监控磁盘健康指标与容量阈值，提供预警和建议。",
            scenarios=("提前发现磁盘风险", "容量阈值监控"),
            sort_order=3,
        ),
        # 效率辅助
        ModuleMeta(
            id="result-export",
            name="扫描结果导出（CSV/Markdown）",
            category="效率辅助",
            status="planned",
            priority="P1",
            description="将扫描结果导出为 CSV/Markdown，便于汇报和留档。",
            scenarios=("输出周报", "问题复盘留档"),
            sort_order=1,
        ),
        ModuleMeta(
            id="task-templates",
            name="任务模板（定时/批量）",
            category="效率辅助",
            status="planned",
            priority="P2",
            description="保存常用扫描任务模板，支持定时执行和批量目录处理。",
            scenarios=("固定周期巡检", "批量任务执行"),
            sort_order=2,
        ),
        ModuleMeta(
            id="one-click-report",
            name="一键诊断报告",
            category="效率辅助",
            status="planned",
            priority="P2",
            description="聚合多模块结果，生成统一诊断报告。",
            scenarios=("快速交付诊断结论", "标准化报告输出"),
            sort_order=3,
        ),
    ]


def sort_module_catalog(catalog: Iterable[ModuleMeta]) -> list[ModuleMeta]:
    priority_rank = {"available": 0, "P1": 1, "P2": 2}
    return sorted(catalog, key=lambda x: (x.category, priority_rank.get(x.priority, 9), x.sort_order))


def get_module_registry() -> Dict[str, Type[BaseModule]]:
    """Backward-compatible registry for implemented modules only."""
    return {
        item.name: item.module_cls
        for item in get_module_catalog()
        if item.module_cls is not None and item.status in ("available", "beta")
    }

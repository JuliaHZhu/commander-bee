"""Todo Ball Machine — embedded tool for worker-bee.

调用极简引擎 engine.py，单文件持久化状态。
"""
import os
import sys
import threading
from datetime import date
from pathlib import Path
from typing import Optional

from agent.registry import registry

_DATA_DIR = Path(__file__).parent.parent / "todo_ball_machine"
os.environ["ENTP_BASE_PATH"] = str(_DATA_DIR)

# 动态导入 engine（避免启动时就 import）
_engine = None
_engine_lock = threading.Lock()


def _eng():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:  # double-checked locking
                sys.path.insert(0, str(_DATA_DIR))
                from engine import Engine
                _engine = Engine(_DATA_DIR)
    return _engine


# ---------------------------------------------------------------------------
# 格式化帮助
# ---------------------------------------------------------------------------
_STATUS_EMOJI = {
    "completed": "✅", "planned": "📋",
    "pending": "⏳", "cancelled": "❌",
}
_SESSION_LABEL = {
    "morning": "上午场", "afternoon": "下午场",
    "evening": "晚间场", "overtime": "加班场",
}


def _fmt_block(block: dict) -> str:
    box = block.get("box", "")
    status = block.get("status", "unknown")
    # 自由/特殊记账不在 boxes 中，给个通用 emoji
    emoji_map = {"自由": "✨"}
    emoji = emoji_map.get(box, _eng().status()["boxes"].get(box, {}).get("emoji", "🔴"))
    return (
        f"{_STATUS_EMOJI.get(status, '❓')} "
        f"{emoji} "
        f"{block.get('content', '无内容')} "
        f"[{box}]"
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def _action_dashboard() -> str:
    s = _eng().status()
    lines = ["═══ Todo Ball Machine 仪表盘 ═══", ""]
    lines.append(f"📅 今日: {date.today()}")
    remaining = 4 - len(s["today"])
    lines.append(f"⏳ 剩余场次: {max(0, remaining)}")
    lines.append(f"📊 周期进度: {s['cycle_progress']}%")
    lines.append("")
    lines.append("━ 今日安排 ━")
    if s["today"]:
        for b in s["today"]:
            sess = b.get("session", "")
            lines.append(f"  • {_SESSION_LABEL.get(sess, sess)}: {_fmt_block(b)}")
    else:
        lines.append("  （暂无安排）")
    lines.append("")
    lines.append("━ 盒子配额 ━")
    for key, info in sorted(s["boxes"].items()):
        lines.append(
            f"  {info['emoji']} ({key}): "
            f"{info['used']}/{info['total']} 已用, 剩{info['remaining']}"
        )
    return "\n".join(lines)


def _action_today() -> str:
    t = _eng().today()
    lines = [f"═══ 今日场次 ({t['date']}) ═══", ""]
    for key in ("morning", "afternoon", "evening", "overtime"):
        label = _SESSION_LABEL.get(key, key)
        sess = t["sessions"].get(key)
        if sess:
            lines.append(f"  {label}: {_fmt_block(sess)}")
        else:
            extra = "（可选）" if key == "overtime" else ""
            lines.append(f"  {label}: 待抽取{extra}")
    return "\n".join(lines)


def _action_draw(session: str) -> str:
    if not session:
        return "❌ 请提供 session"
    r = _eng().draw(session)
    if not r["ok"]:
        return f"❌ {r['error']}"
    blk = r["block"]
    return (
        f"✅ {r['message']}\n"
        f"  {_fmt_block(blk)}\n"
        f"  时长: {blk.get('duration', '?')}h"
    )


def _action_quick_draw() -> str:
    r = _eng().quick_draw()
    if not r["ok"]:
        return f"❌ {r['error']}"
    lines = [f"✅ {r['message']}", ""]
    for b in r["blocks"]:
        lines.append(f"  • {_SESSION_LABEL.get(b.get('session',''), b.get('session',''))}: {_fmt_block(b)}")
    return "\n".join(lines)


def _action_complete(session: str) -> str:
    if not session:
        return "❌ 请提供 session"
    r = _eng().complete(session)
    return f"✅ {r['message']}" if r["ok"] else f"❌ {r['error']}"


def _action_edit(session: str, content: str) -> str:
    if not session or not content:
        return "❌ 需要 session 和 content"
    r = _eng().edit(session, content)
    return f"✅ {r['message']}" if r["ok"] else f"❌ {r['error']}"


def _action_redraw(session: str) -> str:
    if not session:
        return "❌ 请提供 session"
    r = _eng().redraw(session)
    if not r["ok"]:
        return f"❌ {r['error']}"
    blk = r.get("block", {})
    return (
        f"🔄 重抽完成\n"
        f"  {_fmt_block(blk)}\n"
        f"  时长: {blk.get('duration', '?')}h"
    )


def _action_fill(session: str, content: str) -> str:
    if not session or not content:
        return "❌ 需要 session 和 content (格式: 盒子名|内容)"
    # Parse box|content — 支持 | 或 中/英文冒号
    if "|" in content:
        box, text = content.split("|", 1)
    elif "：" in content:
        box, text = content.split("：", 1)
    elif ":" in content:
        box, text = content.split(":", 1)
    else:
        return "❌ content 格式应为: 盒子名|内容 (如: 治愈|妈妈说话)"
    box = box.strip()
    text = text.strip()
    r = _eng().fill(session, box, text)
    if not r["ok"]:
        return f"❌ {r['error']}"
    return (
        f"✅ {r['message']}\n"
        f"  {_fmt_block(r['block'])}"
    )


def _action_log(session: str, content: str) -> str:
    if not session or not content:
        return "❌ 需要 session 和 content"
    r = _eng().log(session, content)
    if not r["ok"]:
        return f"❌ {r['error']}"
    return (
        f"✅ {r['message']}\n"
        f"  {_fmt_block(r['block'])}"
    )


def _action_box_list() -> str:
    s = _eng().status()
    lines = ["═══ 盒子配额 ═══", ""]
    for key, info in sorted(s["boxes"].items()):
        lines.append(
            f"  {info['emoji']} ({key}): "
            f"{info['total']}总 | {info['used']}用 | {info['remaining']}剩"
        )
    return "\n".join(lines)


def _action_cycle_status() -> str:
    s = _eng().status()
    boxes = s["boxes"]
    total_used = sum(v["used"] for v in boxes.values())
    total_quota = sum(v["total"] for v in boxes.values())
    c = s["cycle"]
    return (
        "═══ 周期状态 ═══\n\n"
        f"  周期: {c['name']}\n"
        f"  起止: {c['start']} → {c['end']}\n"
        f"  完成度: {s['cycle_progress']}% ({total_used}/{total_quota})"
    )


def _action_new_cycle(name: str = None) -> str:
    today = date.today()
    name = name or f"{today.year}年{today.month:02d}月周期"
    start = str(today)
    end = str(today + __import__("datetime").timedelta(days=29))
    r = _eng().new_cycle(name, start, end)
    return f"✅ {r['message']}" if r["ok"] else f"❌ {r['error']}"


def _action_history(content: str = None) -> str:
    n = 7
    if content and content.isdigit():
        n = int(content)
    days = _eng().history(n)
    if not days:
        return "📭 近期无记录"
    lines = [f"═══ 最近 {len(days)} 天历史 ═══", ""]
    for d in days:
        lines.append(f"📅 {d['date']}")
        for sess in ("morning", "afternoon", "evening", "overtime"):
            s = d["sessions"].get(sess)
            if s:
                lines.append(f"  {_SESSION_LABEL.get(sess, sess)}: {_fmt_block(s)}")
        lines.append("")
    return "\n".join(lines)


def _action_day(content: str = None) -> str:
    target = content or str(date.today())
    d = _eng().day_detail(target)
    lines = [f"═══ {d['date']} 场次 ═══", ""]
    has_any = False
    for sess in ("morning", "afternoon", "evening", "overtime"):
        s = d["sessions"].get(sess)
        if s:
            has_any = True
            lines.append(f"  {_SESSION_LABEL.get(sess, sess)}: {_fmt_block(s)}")
    if not has_any:
        lines.append("  （无记录）")
    return "\n".join(lines)


def _action_stats(content: str = None) -> str:
    n = 7
    if content and content.isdigit():
        n = int(content)
    s = _eng().stats(n)
    lines = ["═══ 统计报告 ═══", ""]

    # 周期概览
    c = s["cycle"]
    lines.append(f"📊 {c['name']}  ({c['start']} → {c['end']})")
    lines.append(f"   总体完成率: {s['overall_rate']}%  ({s['total_completed']}/{s['total_drawn']})")
    lines.append(f"   连续完成天数: {s['streak']} 天 🔥")
    lines.append("")

    # 盒子统计
    lines.append("━ 盒子完成率 ━")
    for name, info in sorted(s["box_stats"].items()):
        bar = "█" * (info["completion_rate"] // 10) + "░" * (10 - info["completion_rate"] // 10)
        lines.append(
            f"  {info['emoji']} {name:4s} {bar} {info['completion_rate']:3d}%  "
            f"({info['completed']}/{info['used']})")
    lines.append("")

    # 每日趋势
    lines.append(f"━ 最近 {len(s['daily_stats'])} 天每日完成率 ━")
    for d in s["daily_stats"]:
        bar = "█" * (d["rate"] // 10) + "░" * (10 - d["rate"] // 10)
        lines.append(
            f"  {d['date']}  {bar} {d['rate']:3d}%  "
            f"({d['completed']}/{d['drawn']})")
    return "\n".join(lines)


def _action_help() -> str:
    return (
        "═══ Todo Ball Machine 帮助 ═══\n\n"
        "用法: todo_ball_machine(action='...', [session=..., content=...])\n\n"
        "  dashboard     — 系统仪表盘\n"
        "  today         — 今日场次状态\n"
        "  draw          — 抽取指定场次 (session)\n"
        "  quick_draw    — 快速抽取三场\n"
        "  complete      — 完成场次 (session)\n"
        "  edit          — 编辑场次内容 (session + content)\n"
        "  redraw        — 重抽指定场次 (session)\n"
        "  fill          — 退弹重填: 从box消耗球并自定义内容 (session + content='box|内容')\n"
        "  log           — 另外记账: 旅行/休假/特殊活动，不占box配额 (session + content='...')\n"
        "  box_list      — 盒子配额列表\n"
        "  cycle_status  — 周期状态\n"
        "  new_cycle     — 开启新周期\n"
        "  history       — 历史记录 (content=N 天, 默认7)\n"
        "  day           — 指定日期详情 (content=YYYY-MM-DD, 默认今天)\n"
        "  stats         — 统计报告 (content=N 天, 默认7)\n"
        "  help          — 显示本帮助"
    )


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------
def todo_ball_machine(
    action: str,
    session: Optional[str] = None,
    content: Optional[str] = None,
) -> str:
    """Todo Ball Machine tool.

    Args:
        action: 操作类型
        session: 场次名 (morning/afternoon/evening/overtime)
        content: 编辑内容 / 日期 / 天数
    """
    action = action.lower().strip()
    dispatch = {
        "dashboard": lambda: _action_dashboard(),
        "today": lambda: _action_today(),
        "draw": lambda: _action_draw(session or ""),
        "quick_draw": lambda: _action_quick_draw(),
        "quick": lambda: _action_quick_draw(),
        "complete": lambda: _action_complete(session or ""),
        "edit": lambda: _action_edit(session or "", content or ""),
        "redraw": lambda: _action_redraw(session or ""),
        "fill": lambda: _action_fill(session or "", content or ""),
        "log": lambda: _action_log(session or "", content or ""),
        "box_list": lambda: _action_box_list(),
        "box": lambda: _action_box_list(),
        "cycle_status": lambda: _action_cycle_status(),
        "cycle": lambda: _action_cycle_status(),
        "new_cycle": lambda: _action_new_cycle(content),
        "history": lambda: _action_history(content),
        "day": lambda: _action_day(content),
        "stats": lambda: _action_stats(content),
        "help": lambda: _action_help(),
    }
    handler = dispatch.get(action)
    if not handler:
        return f"❌ 未知 action: {action}\n可用: {', '.join(dispatch.keys())}"
    try:
        return handler()
    except Exception as e:
        return f"❌ 执行失败: {e}"


registry.register(
    name="todo_ball_machine",
    description=(
        "Todo Ball Machine — 人生任务管理系统。\n"
        "支持抽球机制、场次管理、配额追踪。\n"
        "Actions: dashboard, today, draw, quick_draw, complete, edit, redraw, box_list, cycle_status, new_cycle, history, day, stats, help"
    ),
    parameters={
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型",
                "enum": [
                    "dashboard", "today", "draw", "quick_draw",
                    "complete", "edit", "redraw", "fill", "log",
                    "box_list", "cycle_status",
                    "new_cycle", "history", "day", "stats", "help"
                ]
            },
            "session": {
                "type": "string",
                "description": "场次名: morning, afternoon, evening, overtime",
                "enum": ["morning", "afternoon", "evening", "overtime"]
            },
            "content": {
                "type": "string",
                "description": "编辑内容 / 日期(YYYY-MM-DD) / 天数"
            }
        },
        "required": ["action"]
    },
    handler=todo_ball_machine,
    tags=["todo", "productivity", "life-system"],
    category="productivity"
)

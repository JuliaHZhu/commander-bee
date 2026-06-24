#!/usr/bin/env python3
"""Todo Ball Machine — 每日早报脚本。

由 cron 调用，stdout 即为推送内容。
"""
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from todo_ball_machine.engine import Engine  # noqa: E402


def main():
    eng = Engine(ROOT / "todo_ball_machine")
    today = eng.today()
    c = eng.state["cycle"]

    lines = []
    lines.append("🌅 Todo Ball Machine 早报")
    lines.append("")
    lines.append(f"📅 {today['date']}  |  {c['name']}")
    lines.append("")

    # ---- 今日安排 ----
    lines.append("━ 今日安排 ━")
    has_plan = False
    for sess in eng.SESSIONS:
        label = eng.DISPLAY[sess]
        s = today["sessions"].get(sess)
        if s:
            has_plan = True
            status = "✅" if s["status"] == "completed" else "📋"
            box = s["box"]
            emoji = eng.state["boxes"][box]["emoji"]
            lines.append(f"  {status} {label}: {emoji} {s['content']} [{box}]")
        else:
            extra = "（可选）" if sess == "overtime" else ""
            lines.append(f"  ⏳ {label}: 待抽取{extra}")
    if not has_plan:
        lines.append("  （暂无安排，用 quick_draw 快速抽取）")
    lines.append("")

    # ---- 盒子剩余 ----
    lines.append("━ 盒子剩余 ━")
    for name, box in sorted(eng.state["boxes"].items()):
        rem = len(box["stack"])
        used = len(box["used"])
        total = rem + used
        pct = int(used / total * 100) if total else 0
        lines.append(f"  {box['emoji']} {name:4s} {rem:2d}/{total:2d}  已用{pct:2d}%")
    lines.append("")

    # ---- 昨日回顾 ----
    lines.append("━ 昨日回顾 ━")
    yesterday = str(date.today() - timedelta(days=1))
    yday = eng.state["days"].get(yesterday)
    if yday:
        drawn = len([s for s in yday.values() if s])
        completed = len([s for s in yday.values() if s and s.get("status") == "completed"])
        rate = int(completed / drawn * 100) if drawn else 0
        lines.append(f"  {yesterday}: 完成 {completed}/{drawn}  ({rate}%)")
    else:
        lines.append(f"  {yesterday}: 无记录")

    # ---- 连续完成天数 ----
    streak = 0
    for i in range(365):
        d = str(date.today() - timedelta(days=i + 1))
        day_data = eng.state["days"].get(d, {})
        drawn = len([s for s in day_data.values() if s])
        completed = len([s for s in day_data.values() if s and s.get("status") == "completed"])
        if drawn > 0 and completed == drawn:
            streak += 1
        else:
            break
    if streak:
        lines.append(f"\n🔥 连续完美完成 {streak} 天")

    print("\n".join(lines))


if __name__ == "__main__":
    main()

"""Todo Ball Machine — 极简引擎。

核心概念：
  装填(Fill)  → 彩球 shuffle 后压栈
  抽取(Draw)  → 随机选盒子 → pop
  完成(Done)  → 标记状态
  重抽(Redraw) → push 回栈顶 → 再抽

状态文件 state.json：
{
  "cycle": {"name": "...", "start": "...", "end": "..."},
  "boxes": {
    "学习": {"emoji": "📚", "stack": [...], "used": [...]},
    ...
  },
  "days": {
    "2026-05-22": {
      "morning":   {"box": "...", "content": "...", "status": "planned", "ball_id": "..."},
      "afternoon": null,
      ...
    }
  }
}
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path


class Engine:
    SESSIONS = ["morning", "afternoon", "evening", "overtime"]
    DISPLAY = {
        "morning": "上午场",
        "afternoon": "下午场",
        "evening": "晚间场",
        "overtime": "加班场",
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.state_path = data_dir / "state.json"
        self.balls_path = data_dir / "balls.json"
        self.config_path = data_dir / "config.json"
        self.state = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if not self.state_path.exists():
            return self._init()
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Archive corrupted state with timestamp so user can inspect it
            import time
            corrupted = self.state_path.parent / f"{self.state_path.stem}.json.corrupted.{int(time.time())}"
            try:
                self.state_path.rename(corrupted)
            except OSError:
                pass
            # Try backup recovery
            backup = self.state_path.with_suffix(".json.bak")
            if backup.exists():
                try:
                    data = json.loads(backup.read_text(encoding="utf-8"))
                    self.state_path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    return data
                except (json.JSONDecodeError, OSError):
                    pass
            return self._init()

    def _init(self) -> dict:
        cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
        balls = json.loads(self.balls_path.read_text(encoding="utf-8"))
        state = {
            "cycle": {
                "name": cfg["cycle_name"],
                "start": cfg["cycle_start"],
                "end": cfg["cycle_end"],
            },
            "boxes": {},
            "days": {},
        }
        for name, info in balls["boxes"].items():
            stack = [b["id"] for b in info["balls"]]
            random.shuffle(stack)
            state["boxes"][name] = {
                "emoji": info["emoji"],
                "stack": stack,
                "used": [],
            }
        return state

    def _save(self):
        data = json.dumps(self.state, ensure_ascii=False, indent=2)
        tmp = self.state_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(data, encoding="utf-8")
            # Rotate backup before replacing current state
            if self.state_path.exists():
                try:
                    bak = self.state_path.with_suffix(".json.bak")
                    bak.write_text(self.state_path.read_text(encoding="utf-8"), encoding="utf-8")
                except OSError:
                    pass
            tmp.rename(self.state_path)
        except OSError:
            # Fallback: direct write if atomic rename fails
            try:
                self.state_path.write_text(data, encoding="utf-8")
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _ball_lookup(self, box: str, ball_id: str) -> dict:
        balls = json.loads(self.balls_path.read_text(encoding="utf-8"))
        for b in balls["boxes"][box]["balls"]:
            if b["id"] == ball_id:
                return b
        return {"content": "未知任务", "difficulty": "medium"}

    def _today(self) -> str:
        return str(date.today())

    def _day(self) -> dict:
        return self.state["days"].setdefault(self._today(), {})

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def draw(self, session: str, box: str = None) -> dict:
        day = self._day()
        if session in day:
            return {"ok": False, "error": f"{self.DISPLAY.get(session, session)} 已抽取"}

        candidates = []
        if box:
            if box not in self.state["boxes"]:
                return {"ok": False, "error": f"盒子 '{box}' 不存在"}
            candidates = [box]
        else:
            candidates = [n for n, b in self.state["boxes"].items() if b["stack"]]
            if not candidates:
                return {"ok": False, "error": "所有盒子已空，请开启新周期"}

        selected = random.choice(candidates)
        ball_id = self.state["boxes"][selected]["stack"].pop()
        self.state["boxes"][selected]["used"].append(ball_id)

        ball_info = self._ball_lookup(selected, ball_id)
        day[session] = {
            "box": selected,
            "content": ball_info["content"],
            "status": "planned",
            "ball_id": ball_id,
        }
        self._save()
        return {
            "ok": True,
            "message": f"✅ 成功抽取 {self.DISPLAY.get(session, session)}",
            "session": session,
            "block": {
                **day[session],
                "difficulty": ball_info.get("difficulty", "medium"),
                "duration": {"hard": 3.0, "medium": 2.5, "easy": 2.0}.get(
                    ball_info.get("difficulty", "medium"), 2.5
                ),
            },
        }

    def quick_draw(self) -> dict:
        drawn = []
        for s in ["morning", "afternoon", "evening"]:
            if s not in self.state["days"].get(self._today(), {}):
                r = self.draw(s)
                if r["ok"]:
                    drawn.append(r)
        return {
            "ok": True,
            "message": f"✅ 快速抽取完成，共 {len(drawn)} 场",
            "blocks": [d["block"] for d in drawn],
        }

    def complete(self, session: str) -> dict:
        day = self.state["days"].get(self._today(), {})
        if session not in day:
            return {"ok": False, "error": f"{session} 未抽取"}
        day[session]["status"] = "completed"
        self._save()
        return {"ok": True, "message": f"✅ {self.DISPLAY.get(session, session)} 已完成"}

    def edit(self, session: str, content: str) -> dict:
        day = self.state["days"].get(self._today(), {})
        if session not in day:
            return {"ok": False, "error": f"{session} 未抽取"}
        day[session]["content"] = content
        self._save()
        return {"ok": True, "message": f"✅ {self.DISPLAY.get(session, session)} 已更新"}

    def redraw(self, session: str) -> dict:
        day = self.state["days"].get(self._today(), {})
        if session not in day:
            return {"ok": False, "error": f"{session} 未抽取，无需重抽"}

        old = day[session]
        box = old["box"]
        ball_id = old["ball_id"]
        # Return to top of stack
        self.state["boxes"][box]["stack"].append(ball_id)
        if ball_id in self.state["boxes"][box]["used"]:
            self.state["boxes"][box]["used"].remove(ball_id)
        del day[session]
        self._save()
        return self.draw(session)

    def fill(self, session: str, box: str, content: str) -> dict:
        """退弹重填 — 消耗指定box的一个ball，但内容自定义。"""
        if box not in self.state["boxes"]:
            return {"ok": False, "error": f"盒子 '{box}' 不存在"}
        box_data = self.state["boxes"][box]
        if not box_data["stack"]:
            return {"ok": False, "error": f"盒子 '{box}' 已空，请换盒子或开启新周期"}

        # 消耗一个球（从stack pop，放入used）
        ball_id = box_data["stack"].pop()
        box_data["used"].append(ball_id)

        day = self._day()
        day[session] = {
            "box": box,
            "content": content,
            "status": "completed",
            "ball_id": ball_id,
        }
        self._save()
        return {
            "ok": True,
            "message": f"✅ {self.DISPLAY.get(session, session)} 已记录",
            "block": day[session],
        }

    def log(self, session: str, content: str) -> dict:
        """另外记账 — 旅行/休假/特殊活动，不消耗任何 box 彩球。"""
        day = self._day()
        day[session] = {
            "box": "自由",
            "content": content,
            "status": "completed",
            "ball_id": "",
        }
        self._save()
        return {
            "ok": True,
            "message": f"✅ {self.DISPLAY.get(session, session)} 已记账（不占配额）",
            "block": day[session],
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def status(self) -> dict:
        boxes = {}
        total_used = total_quota = 0
        for name, box in self.state["boxes"].items():
            used = len(box["used"])
            quota = used + len(box["stack"])
            total_used += used
            total_quota += quota
            boxes[name] = {
                "emoji": box["emoji"],
                "used": used,
                "total": quota,
                "remaining": len(box["stack"]),
            }

        today = self._today()
        day = self.state["days"].get(today, {})

        # Format today's blocks for display
        today_blocks = []
        for sess in self.SESSIONS:
            if sess in day:
                b = day[sess]
                today_blocks.append({
                    "session": sess,
                    "box": b["box"],
                    "content": b["content"],
                    "status": b["status"],
                    "ball_id": b["ball_id"],
                })

        return {
            "today": today_blocks,
            "boxes": boxes,
            "cycle": self.state["cycle"],
            "cycle_progress": int(total_used / total_quota * 100) if total_quota else 0,
        }

    def today(self) -> dict:
        today = self._today()
        day = self.state["days"].get(today, {})
        result = {}
        for sess in self.SESSIONS:
            if sess in day:
                result[sess] = day[sess]
            else:
                result[sess] = None
        return {"date": today, "sessions": result}

    def history(self, n_days: int = 7) -> list:
        result = []
        today = date.today()
        for i in range(n_days):
            d = str(today - timedelta(days=i))
            if d in self.state["days"]:
                result.append({"date": d, "sessions": self.state["days"][d]})
        return result

    def day_detail(self, target_date: str) -> dict:
        day = self.state["days"].get(target_date, {})
        sessions = {}
        for sess in self.SESSIONS:
            sessions[sess] = day.get(sess)
        return {"date": target_date, "sessions": sessions}

    def stats(self, n_days: int = 7) -> dict:
        """统计报告：盒子完成率、每日趋势、连续完成天数。"""
        # ---- 盒子统计 ----
        box_stats = {}
        for name, box in self.state["boxes"].items():
            completed = 0
            for day in self.state["days"].values():
                for sess in day.values():
                    if sess and sess.get("box") == name and sess.get("status") == "completed":
                        completed += 1
            used = len(box["used"])
            total = used + len(box["stack"])
            box_stats[name] = {
                "emoji": box["emoji"],
                "used": used,
                "total": total,
                "completed": completed,
                "completion_rate": int(completed / used * 100) if used else 0,
            }

        # ---- 每日统计 ----
        daily_stats = []
        today = date.today()
        for i in range(n_days):
            d = str(today - timedelta(days=i))
            day_data = self.state["days"].get(d, {})
            drawn = len([s for s in day_data.values() if s])
            completed = len([s for s in day_data.values() if s and s.get("status") == "completed"])
            daily_stats.append({
                "date": d,
                "drawn": drawn,
                "completed": completed,
                "rate": int(completed / drawn * 100) if drawn else 0,
            })

        # ---- 连续完成天数 ----
        streak = 0
        for i in range(365):
            d = str(today - timedelta(days=i))
            day_data = self.state["days"].get(d, {})
            drawn = len([s for s in day_data.values() if s])
            completed = len([s for s in day_data.values() if s and s.get("status") == "completed"])
            if drawn > 0 and completed == drawn:
                streak += 1
            else:
                break

        # ---- 总体（仅统计当前周期）----
        cycle_start = self.state["cycle"]["start"]
        total_drawn = 0
        total_completed = 0
        for d, day in self.state["days"].items():
            if d < cycle_start:
                continue
            for sess in day.values():
                if sess:
                    total_drawn += 1
                    if sess.get("status") == "completed":
                        total_completed += 1

        return {
            "box_stats": box_stats,
            "daily_stats": daily_stats,
            "streak": streak,
            "cycle": self.state["cycle"],
            "total_drawn": total_drawn,
            "total_completed": total_completed,
            "overall_rate": int(total_completed / total_drawn * 100) if total_drawn else 0,
        }

    def new_cycle(self, name: str, start: str, end: str) -> dict:
        """开启新周期 — 重新装填所有彩球。"""
        self.state["cycle"] = {"name": name, "start": start, "end": end}
        self.state["days"] = {}
        balls = json.loads(self.balls_path.read_text(encoding="utf-8"))
        for name, info in balls["boxes"].items():
            stack = [b["id"] for b in info["balls"]]
            random.shuffle(stack)
            self.state["boxes"][name] = {
                "emoji": info["emoji"],
                "stack": stack,
                "used": [],
            }
        self._save()
        return {"ok": True, "message": f"✅ 新周期 '{name}' 已开启"}

# 08 — StrategicBee

> 独立日程安排软件。不是 Hermes Skill，不内嵌 script——是一个独立程序，暴露 Tool 接口挂进注册表。

---

## 一、定位

StrategicBee 是一个**日程安排和轻重缓急判断工具**。

它不是战略分析引擎——那些分析（五工具流水线、案例拆解）是你做的事，不是工具做的事。StrategicBee 只做一件事：**帮你判断今天应该先做什么、后做什么，什么可以放一放。**

球机解决"选哪个"——从已有的任务池里随机抛。StrategicBee 解决"排先后"——给任务池排优先级。

---

## 二、核心假设

操作员就是棋子。

一个日程安排工具如果假设操作员精力无限、时间无限、状态恒定——那就是废物。StrategicBee 假设：

- 今天已经做了几个小时了？
- 上一个任务是什么类型的？（分析型/执行型/社交型）
- 还剩多少精力预算？
- 本周的硬 deadlines 是什么？

它不是帮你做战略分析——是帮你**在精力有限的情况下，把最重要的几件事排进今天的时间窗口**。

---

## 三、作为独立软件

```
StrategicBee/
├── strategic_bee.py     # 主程序
├── config.yaml           # 优先级规则
└── tools/
    └── registry_entry.py # 注册为 Tool：strategy_schedule
```

**暴露的 Tool 接口**：

```
strategy_schedule(agenda_items, energy_budget, deadlines) → prioritized_list
```

---

## 四、与球机的关系

球机和 StrategicBee 是并列的独立软件：

| | 球机 | StrategicBee |
|--|------|-------------|
| 输入 | 任务池 | 任务池 + 时间约束 + 精力状态 |
| 输出 | 随机一个任务 | 排好优先级的一天 |
| 策略 | 随机（降低决策成本） | 规则（轻重缓急判断） |
| 关系 | 平级 | 平级 |

操作员可以选择今天用哪个——精力充沛用球机随缘抛，事情太多用StrategicBee排优先级。两者不互斥。

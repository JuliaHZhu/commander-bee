# WorldBee：看不见的空气制造者

> 蜜蜂们不知道自己是蜜蜂，也不知道旁边有蜜蜂。它们只闻得见味儿。
>
> WorldBee 就是那个撒味儿的人 —— 但它从不下达命令，只改变空气。

---

## 一、WorldBee 是什么？

WorldBee 不是审查者。它不看 PR，不审代码，不开 Issue，不 merge，不做任何管理决策。

WorldBee 是一个**独立运行的物理规则驱动的监督机制**，像免疫系统：
- 免疫系统不管体细胞怎么工作
- 它只检测环境中的异常信号
- 然后释放细胞因子（信息素）
- 体细胞闻到信号后，自己决定怎么反应

```
体细胞（WorkerBee）在工作
    │
    ▼ 产生代谢废物（执行日志、测试结果）
    │
    ▼ 免疫系统（WorldBee）检测
    │
    ▼ 释放细胞因子（信息素）
    │
    ▼ 体细胞闻到后，自己反应
```

---

## 二、数据来源：物理引擎与测试环境

WorldBee 不看代码，它看数据：

| 数据来源 | 例子 | WorldBee 得到什么 |
|----------|------|-------------------|
| **测试环境** | CI 构建结果、单元测试 | 这个 Skill 导致的失败率 |
| **物理引擎** | 模拟执行 | 路径 A 成功率 30%，路径 B 成功率 85% |
| **性能监控** | Token 消耗、耗时 | 用 Skill "web-scrape-v1" 的任务平均花 120s |
| **执行轨迹** | WorkerBee 的工具调用顺序 | 某个路径是不是走了弯路 |

**关键：WorldBee 是规则化的，不是 LLM 推理的。** 它运行的是硬编码的规则，不会幻觉。

---

## 三、三种信息素

WorldBee 撒的味儿分三种：

### 1. 甜味 Skill（优化饵料）

```markdown
---
name: css-dark-mode
trigger: dark mode, 暗色模式, 夜间模式
tools:
  - fs_read_file
  - fs_write_file
---

## 暗色模式怎么做

1. 先查 design/ 目录有没有设计稿
2. 用 CSS 变量定义颜色
3. 加 toggle 按钮
4. 用 localStorage 存用户偏好
```

WorldBee 发现：使用这个 Skill 的任务，平均步数更少、成功率更高。
→ 在 Skill 文件里加一个标记：`pheromone: sweet`
→ WorkerBee 下次加载时，会优先考虑这个 Skill

### 2. 苦味 Warning（病毒信号）

```markdown
---
name: anti-pattern-alert
trigger: rm -rf, delete *, 全删, 覆盖
tools:
  - request_approval
pheromone: bitter
---

## 警告

如果用户或上下文要求"删除全部"、"覆盖所有"，
必须触发 request_approval。
这是苦味标记区域，不要擅自飞过。
```

WorldBee 发现：某个操作导致高频失败或危险。
→ 在 warnings/ 目录新增苦味标记
→ WorkerBee 闻到后，要么停下等审批，要么绕道走

### 3. 路线图 Route（蚕食路线）

```markdown
---
name: website-migration
trigger: 迁移网站, 重构, migration
tools:
  - fs_read_file
  - fs_write_file
  - sys_terminal
---

## 网站迁移：蚕食路线图

这个任务太大，一只 Bee 吃不完。
按以下顺序分解，每个子任务单独开 Issue：

1. [ ] 备份现有数据库 → Issue A
2. [ ] 导出静态页面 → Issue B  
3. [ ] 配置新服务器 → Issue C
4. [ ] DNS 切换 → Issue D（需要不可逆权限，CommanderBee 签字）
```

WorldBee 发现：某个大任务导致 Bee 反复扭转、步数超限。
→ 在 routes/ 目录下放路线图
→ 指导 CommanderBee 开子 Issue，让多只 Bee 分头吃

---

## 四、促使反思，不下达命令

WorldBee 从不对 WorkerBee 说"你应该怎么做"。它只是**改变空气**。

**WorkerBee 的反思是被动的**：
- 上次用路径 A，结果失败了（因为 WorldBee 撒了苦味）
- 这次加载 Skill 时，自动看到了苦味标记
- WorkerBee 的 LLM 推理时会自然避开这条路

**这不是学习，是沉积。** 水流改道了，船自然不走老路。

---

## 五、WorldBee 的工作机制

```
WorldBee（独立运行的监督机制）
    │
    ├── 读取测试环境、物理引擎、性能监控的数据
    │
    ├── 规则引擎分析
    │   ├── 成功率 / 失败率
    │   ├── 耗时分布
    │   └── 路径效率
    │
    ├── 产生信息素
    │   ├── skills/ ··· 甜味标记（好方法推荐）
    │   ├── warnings/ ··· 苦味标记（雷区警告）
    │   └── routes/ ··· 路线图（大任务分解）
    │
    └── 所有 WorkerBee 下次启动时自动闻到
```

**重要：WorldBee 的产出是 Markdown，但不是命令。** 它不能开 Issue，不能 merge PR，不能改交付仓库。它只能改变蜂群基础设施里的"空气质量"。

---

## 六、环境错了？不是蜜蜂的错

如果 WorldBee 撒了错误的信息素：

```markdown
## 错误 Skill
1. 先删 node_modules/
2. 再删 package.json
3. 然后重新安装
```

所有 WorkerBee 闻到这个味儿，都会傻乎乎地照做。

**但问题不在 Bee，在环境。**

修正方法：
- CommanderBee 审 Skill PR 时发现这个 Skill 有毒
- 拒绝 merge
- 或者 WorldBee 自己从测试数据中发现这个 Skill 导致高失败率
- 自动撒苦味标记覆盖它

**蜂群不需要进化，环境需要净化。**

---

## 七、规模与斜率

| 规模 | 状态 |
|------|------|
| 1 只 Bee | 空气干净，信息素 = 0 |
| 10 只 Bee | 甜味 = 20，苦味 = 5，路线 = 2 |
| 100 只 Bee | 甜味 = 80，苦味 = 30，路线 = 10，覆盖 90% |
| 1000 只 Bee | 空气极其丰富，Bee 越来越"聪明"（其实是空气越来越友好） |

**但这个增长是对数的原因不是 Bee 进化了，而是信息素经验累积了。**

Bee 还是那些 Bee。它们不知道自己是蜜蜂。它们只知道今天闻到的味儿，比昨天更甜了。

---

## 八、一句话

> **WorkerBee 是盲人，靠闻味儿走路。WorldBee 是那个撒味儿的人 —— 但它从不下达命令，只是沉积。味儿对了，蜂群自然走到对的地方。味儿错了，再聪明的蜜蜂也会掉进坑里。**
>
> **所以重要的不是训练蜜蜂，而是看护好这片空气。WorldBee 就是空气的看护人。**

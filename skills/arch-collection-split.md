---
name: arch-collection-split
description: 拆分长篇/合集为自然段落后逐段分析。双模式：短篇集→拆单篇 + 侦探长篇→案件阶段（案发→初查→线索→误导→突破→对峙→收束）。
trigger: 拆短篇集, 拆合集, 拆集子, 拆长篇, 拆侦探, 分阶段, 拆案件, collection split, 拆段
tools:
  - fs_read_file
  - fs_write_file
  - fs_search_files
category: architecture
---

# 段拆分——合集 & 侦探长篇

把大作品拆成自然叙事段。两个模式：

**A. 短篇集** → 每篇一个段
**B. 侦探长篇** → 每个案件阶段一个段（案发→初查→线索→误导→突破→对峙→收束）

段是跑 `arch-novel-split`（原子化）前的正确粒度。

## 存储位置

**Step 0**: 把下载的原始文本放到 `~/.worker-bee/arch/texts/<作品名>/source.md`。
**Step 1**: 跑 arch-collection-split → 读 source.md → 拆段 → 写每段 `<slug>/source.md` + index.md。
**Step 2**: 跑 arch-novel-split 逐段 → 读 `<slug>/source.md` → 写 `<slug>/atoms.md`。

```
~/.worker-bee/arch/texts/<作品名>/
├── source.md              ← 原始文本放这里
├── index.md               ← 段列表（自动生成）
├── <段-slug>/
│   ├── source.md          ← 该段文本
│   └── atoms.md           ← arch-novel-split 产出
├── <段-slug>/
│   ├── source.md
│   └── atoms.md
└── ...
```

## 模式 A: 短篇集 → 拆单篇

按篇目标题、编号、故事结尾+新开头拆分。

index.md 示例：

```markdown
# 合集: 福尔摩斯探案全集
## 模式: collection
## 段数: 56
## 已分析: 0/56

| # | 篇名 | slug | 字数 | 状态 |
|---|------|------|------|------|
| 1 | 血字的研究 | study-in-scarlet | 42,000 | pending |
| 2 | 四签名 | sign-of-four | 38,000 | pending |
| ... | ... | ... | ... | ... |
```

## 模式 B: 侦探长篇 → 案件阶段

按**案件推进**拆，不按章节拆。一本 200 页长篇可能只有 6-8 个段。

### 标准阶段模板

| # | 阶段 | slug | 发生什么 | 典型信号 |
|---|------|------|---------|---------|
| 1 | 案发 | crime | 犯罪发现、案发现场、受害者出现 | 尸体被发现、案件报告 |
| 2 | 初查 | initial-investigation | 侦探到达、基本情况、关键人物出场 | 开始询问、勘察现场 |
| 3 | 线索 | clue-gathering | 收集证据、证人问询、初步推理 | 走访地点、搜集物品 |
| 4 | 误导 | red-herring | 错误方向、错误嫌疑人、紧张感 | 怀疑落在无辜者身上 |
| 5 | 突破 | breakthrough | 关键洞察、转折点、拼图合拢 | 侦探"原来如此"时刻 |
| 6 | 对峙 | confrontation | 面对真凶、高潮、风险最大化 | 侦探与嫌疑人正面对峙 |
| 7 | 收束 | resolution | 案件解释、填坑、回扣 | 侦探解释全案 |

**不是每本都有 7 个阶段。** 有的合并、有的跳过、有的回环。按实际文本调整——模板是参考，不是紧箍咒。

如果某个阶段特别长（如线索阶段横跨 80 页），进一步拆分：`clue-gathering-1`、`clue-gathering-2`。

### index.md 示例

```markdown
# 长篇: 巴斯克维尔的猎犬
## 模式: detective-novel
## 段数: 6

| # | 阶段 | slug | 字数 | 章节 | 状态 |
|---|------|------|------|------|------|
| 1 | 案发 | crime | 6,200 | Ch.1-2 | pending |
| 2 | 初查 | initial-investigation | 11,000 | Ch.3-5 | pending |
| 3 | 线索 | clue-gathering | 18,000 | Ch.6-9 | pending |
| 4 | 突破 | breakthrough | 8,500 | Ch.10-12 | pending |
| 5 | 对峙 | confrontation | 9,300 | Ch.13-14 | pending |
| 6 | 收束 | resolution | 6,000 | Ch.15 | pending |
```

## 拆完后

每段跑 `arch-novel-split`（原子化）→ `arch-novel-tag`（打标签）。更新 index.md 状态：`pending` → `atoms-ready` → `tagged`。

## 跨段分析

标完后跨段对比：

```
线索密度按阶段：
  案发: 12%  初查: 22%  线索: 38%  突破: 15%  对峙: 5%  收束: 8%

张力峰值: 对峙（68% 原子标了 [张力]）
误导全集中在: 线索阶段
```

跨篇：
```
56篇合集: 线索密度区间 8%~35%，转折频率 0.3次/篇
```

## 约束

- 每段独立目录
- 侦探长篇按实际文本调整 7 阶段模板——不存在的阶段不要硬造
- 极短段（<2,000字、<15原子）可合并到相邻段
- index.md 追踪一切，每次操作后更新

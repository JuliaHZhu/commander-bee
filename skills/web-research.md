---
name: web-research
description: Research topics on the web and summarize findings
trigger: search, look up, research, find online, what is, who is, how to
tools:
  - net_web_search
  - net_web_extract
category: research
---

# Web Research Skill

When the user asks to research something online:

## Query Construction

1. Start from the user's question or topic
2. Strip meta verbs: 调研, 研究, research, search, 调查, 查找, 了解, 分析, review, investigate
3. Use the remaining entity as the search query
4. Never append descriptive text — it contains meta-verbs that pollute search

## Domain Preference

When extracting, prioritize in this order:

1. baike.baidu.com
2. zh.wikipedia.org
3. zhihu.com
4. weread.qq.com
5. douban.com
6. gov.cn

Skip domains that return 403 or empty content.

## Extraction

- Max extract length: 1500 chars
- Timeout: 15 seconds per URL

## Steps

1. Formulate a precise search query (use stripped entity, not full question)
2. Call `net_web_search` to get results
3. Pick 2-3 most relevant URLs, prioritize preferred domains
4. Call `net_web_extract` on each URL
5. Synthesize findings into a concise summary
6. Cite sources with URLs

## Output

- Save extracts individually: `{skill}-{YYYY-MM-DD}-extract-{domain}.md`
- Save final report: `{skill}-{YYYY-MM-DD}-report.md`

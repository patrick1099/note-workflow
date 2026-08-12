# note-workflow

给 Obsidian 笔记做整理、归档和织链的工作流。它不靠你记得走到哪一步：进度写在每篇笔记自己的
frontmatter 里，随时问一句就知道谁还没处理完。

```console
$ py -3 scripts/note_status.py --vault <你的 Vault> --target 01-任务需求
[
  {
    "path": "01-任务需求/某项目/协议整理.md",
    "ai_done": false,  "complete": false,
    "archive_done": false,  "links_done": false,
    "ai_question": null,  "ai_feedback": null,
    "next_stage": "organize"
  },
  ...
]

next_stage 汇总:  complete 140   organize 2
```

（真实巡检结果，笔记路径换成了通用名。）142 篇里只有 2 篇还没整理，这就是它要替你记住的事。

## 装

```
/plugin marketplace add patrick1099/note-workflow
/plugin install note-workflow@note-workflow
```

同时带 `.codex-plugin/` 清单与各 skill 的 `agents/openai.yaml`，Codex 侧可用。

## 四个 skill

| skill | 职责 | 绝不做 |
|---|---|---|
| `run-note-workflow` | 全流程编排：读各笔记的持久状态，按路由分派给下面三个 | 跳过任何人工闸门 |
| `organize-notes` | 完整阅读后分类；仅在需要时把原稿原样归档，并在原目录生成带原稿链接的润色版 | 覆盖或改写归档原稿、给原稿加反链 |
| `archive-notes` | 归档：决定归属目录、建文件夹、执行批准过的移动 | 改写正文、建链接 |
| `weave-note-links` | 织链：分析知识关系，插入 Wiki 链接或把脚注链接收进正文 | 移动文件、大改已验收的文字 |

三个执行 skill 各自守着互不重叠的地盘，所以可以单独调用，也可以交给 `run-note-workflow`
串起来。

## 状态与路由

状态写在笔记 frontmatter 里。未知的 frontmatter 键一律原样保留，不重排、不删除：

| 字段 | 归谁写 | 含义 |
|---|---|---|
| `ai_done` | `organize-notes` | 本轮整理已完成 |
| `complete` | 只有用户 | 你已读过并验收当前正文 |
| `archive_done` | `archive-notes` | 归属决策与移动已收口 |
| `links_done` | `weave-note-links` | 关系决策与链接改动已收口 |
| `ai_question` / `ai_feedback` | AI 提问 / 用户反馈 | 至多一个会改变结果的问题；反馈只读不删 |

路由：`ai_question` 非空 → 等你回答；`ai_done` 未成 → 整理；`complete` 未成 → 等你验收；
`archive_done` 未成 → 归档；`links_done` 未成 → 织链；都成 → 完成。

两条硬规矩：**任何 skill 都不许设置、清除或推断 `complete`**（出了报告不等于阶段完成）；
上游事实失效时自动重置下游（重整理会把 `archive_done` / `links_done` 打回 false）。

## 原稿保全

AI 负责整理与提案，但它改不掉你的原稿。第一阶段只在原稿已完整保留后才生成润色版；成品归档
和验收后的正文 / 链接改动，一律先出精确 Dry Run、经你批准才落盘。

原稿统一保存在 `98-Resources/原稿归档/<原相对目录>/`，正文保持字节级不变；润色版单向链接
原稿。原稿不进入状态路由、成品归档或双向知识织链。

| 脚本 | 干什么 |
|---|---|
| `scripts/note_status.py` | 只在你显式指定的 Vault 路径里巡检持久状态 |
| `scripts/action_engine.py` | 渲染并执行经人工批准的精确笔记动作 |
| `scripts/preserve_original.py` | 用同一份计划先校验、再原子执行「原稿归档 + 原目录生成润色版」 |

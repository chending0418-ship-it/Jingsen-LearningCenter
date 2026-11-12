# 历史 PR 补录与生产发布规则（2026-10-22）

生产发布目标为 `deploy/tencent-learningcenter-path`，历史补录截至提交 `9181e9f`。原始提案见 [PR #9](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/9)。

## 补录边界

下列历史改动已经包含在发布分支。#1–#8 是以 `main` 或前一个功能分支为目标建立的追溯 PR，现已关闭，原差异保留供查阅。下表记录它们对应的提交范围。

此处按 Git 提交追溯当时的变更。历史代码已在发布分支，归档只更新文档，无需重新部署或重跑迁移。

## 历史清单

范围采用左开右闭：不包含起点，包含终点。下列 8 段覆盖 `c0822b7..9181e9f` 的全部 54 个提交（包含历史 merge commit）。

| 追溯 PR | 改动 | 提交范围 | 提交数 |
| --- | --- | --- | --- |
| [#1](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/1) | 基础升级、SQLite、Todo、英语 Skills、异步出题、首页/Gallery、Book Reading 与总结修复 | `c0822b7..c095c2d` | 38 |
| [#2](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/2) | 数学因式分解训练与独立后台历史 | `c095c2d..29e790d` | 2 |
| [#3](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/3) | 英语词库合并与来源状态控制 | `29e790d..6a8596a` | 2 |
| [#4](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/4) | 棒球家庭会议问卷与共同决策 | `6a8596a..2a16d02` | 3 |
| [#5](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/5) | 第二周因式分解与反向括号练习 | `2a16d02..c53dec9` | 4 |
| [#6](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/6) | Shoe Dog 十二节预习课、逐题标答与评估回看 | `c53dec9..41df06f` | 2 |
| [#7](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/7) | 老师讨论题仅展示英文 | `41df06f..e76c5b4` | 1 |
| [#8](https://github.com/chending0418-ship-it/Jingsen-LearningCenter/pull/8) | Reading 评估三卡片与大字号展示 | `e76c5b4..9181e9f` | 2 |

历史验证和发布信息以各提交中的 `CHANGELOG.md` 为准。归档时核对了 Git 祖先关系和提交范围的完整性。

## 此后发布

1. 从最新生产分支创建独立工作分支。
2. 完成代码与适当验证，同步更新 changelog。
3. 仅推送工作分支，PR base 明确选择 `deploy/tencent-learningcenter-path`。
4. 审核后通过 GitHub 合并；合并前不部署，禁止直接推送生产分支。
5. 明确待发布合并结果与范围，按 `updateNew.md` 做备份、发布、数据校验和健康检查。
6. 发布结果通过新的工作分支/PR 回写，不为记录发布结果绕过 PR。

GitHub 服务端分支保护需单独配置和验证。部署操作见 [线上安全更新](../updateNew.md)。

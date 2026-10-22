# 历史 PR 补录与生产发布规则（2026-10-22）

当前生产发布目标为 `deploy/tencent-learningcenter-path`，补录基线为 `9181e9f`。`main` 保持原状，不执行合并、重置或推送。

## 补录边界

下列历史改动已经包含在生产分支，不能再向该分支创建包含相同代码差异的有效功能 PR。此前创建的 #1–#8 是以 main 和前序功能分支串联的追溯 PR；现在关闭并保留原差异供查阅，不继续执行该串联合并方案。本次以新的文档 PR 向生产分支补录历史清单，并建立后续发布规范。

补录不表示过去经过 PR 审核，也不重新部署或重放迁移。本地未提交改动不在本次补录范围。`c0822b7` 及更早的 main 历史保持原记录，本次不改写其历史。

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

历史验证和发布信息以各提交对应的 `CHANGELOG.md` 为准。本次核对 Git 祖先关系、范围无重叠且无遗漏，不把过去的测试写成本次重新执行的结果，也未登录生产服务器核对运行状态。

## 此后发布

1. 从最新生产分支创建独立工作分支。
2. 完成代码与适当验证，同步更新 changelog。
3. 仅推送工作分支，PR base 明确选择 `deploy/tencent-learningcenter-path`。
4. 审核后通过 GitHub 合并；合并前不部署，禁止直接推送生产分支。
5. 明确待发布合并结果与范围，按 `updateNew.md` 做备份、发布、数据校验和健康检查。
6. 发布结果通过新的工作分支/PR 回写，不为记录发布结果绕过 PR。

本次只提交 PR，不执行合并或部署。仓库规范及 PR 模板不能替代 GitHub 分支保护；服务端保护是否启用须另行核实。

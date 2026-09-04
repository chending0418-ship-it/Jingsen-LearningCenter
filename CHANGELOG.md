# Jingsen Learning Center 更新日志与运维纪要

本文记录重要功能、数据架构和线上运维变更，供后续开发、部署、故障排查和恢复时查阅。

- 记录顺序：新记录在前。
- 代码依据：Git 提交、仓库文档及实际线上检查结果。
- 安全约定：不在本文记录密码、API Key、私钥或其他凭据。
- 维护约定：每次功能、修复、数据迁移、部署、基础设施或线上事故处理完成后，必须在同一任务内主动更新本文，无需用户再次提醒；单纯维护本文不递归生成新条目。
- 当前生产分支：`deploy/tencent-learningcenter-path`。
- 当前公网入口：`https://jingsen.cc/learningcenter/`。

## 2026-09-04：Book Reading Summary 证据约束修复（已上线）

### 问题与用户可见结果

- 线上复盘确认：一次 4 题阅读中，主回答和追问回答全部为 `test`，逐题等级均正确记录为 `needs_support`，但最终模型仍把“完成问题、持续尝试”列成优势，孩子端又会在 strengths 为空时补充默认表扬，导致 Summary 看起来敷衍且与真实回答不符。
- 修复后，`test`、`testing`、`asdf`、`qwerty`、`skip` 等明确占位回答会收到一次简短重试引导；第二次仍为占位回答时结束该题并记为 `needs_support`。这条确定性路径不会调用逐题评分模型，既避免虚假反馈也减少无效 Token。
- 如果整次阅读只有重复占位回答，最终 Summary 会明确说明无法从这些回答判断阅读理解、指出回答没有解释书中观点，并给出重新作答的具体方式；不会再把完成、参与、坚持或努力包装成“理解优势”。结果页标题会改为 `Let’s try that again.`，无可证实优势时显示 `What your answers showed`。

### 实现与评估约束

- 最终理解等级现在由逐题等级计算上限，模型只能保持或下调，不能把多数 `needs_support` 的会话提升为较高等级。
- Summary 提示必须引用本次实际理解点或具体缺口；后端继续过滤 engagement、attempt、completion、persistence 等非理解类 strengths。没有任何 `clear` 或 `mostly_clear` 题目时，strengths 强制为空。
- 非占位的简短回答仍会交给模型按语义评估，继续接受孩子自己的总结和转述，不使用死板字数、关键词或原文相似度判分。

### 验证与风险

- 全量自动测试通过：`48 passed`。新增覆盖连续 `test` 主回答和追问、零额外评分/总结模型调用、诚实的 `needs_support` Summary、空 strengths、证据化 strengths 过滤、泛化 Summary 确定性替换和逐题等级汇总上限；Python 编译、页面 JavaScript 语法及 Git 空白检查通过。
- 功能提交 `b47250d` 与措辞修正 `1dc8ba7` 已从 `devBookReading` 合并为生产提交 `8c99ecf`、`28afa60` 并发布。两轮安全更新分别创建快照 `/www/wwwroot/learningcenter/backups/releases/20260904-114924-525860` 与 `/www/wwwroot/learningcenter/backups/releases/20260904-115037-526321`，完整持久数据恢复和校验通过。
- 生产环境只读冒烟确认：`test` 会被识别为占位回答；泛化的“保持参与、继续努力”会被替换为基于具体问题的 `I couldn’t yet confirm...` 提示，单题措辞正确使用 `this answer`。服务保持 `enabled`、`active`，内部及公网健康、English、Reading 和公开书架 API 均返回 HTTP 200，Admin Reading 未登录时按预期返回 303，近十分钟无 Error、Traceback 或 Exception。
- 发布前后继续保持 1 本书、24 个章节、1 次历史阅读与 4 道历史问题；已上传《Shoe Dog》的 PDF（1,232,646 bytes，SHA-256 `9b95850b455c4cd36c3d66542711ce24bdf3af8c316fa13cf024a6e23b0e5cb7`）与封面（144,176 bytes，SHA-256 `6c1a5bbab4934f4abbe8bd6cfa2a4b686e3a704c40a140430f1bf5c7aab7660d`）均未变化，书籍仍为 Published。
- 历史阅读记录继续作为当时的原始审计记录保留，不自动重写；本修复应用于部署后新提交的回答和新完成的 Summary。

## 2026-09-04：Book Reading 题量与问题重点优化（已上线）

### 变更目的与用户可见结果

- 阅读开始前的问题数改为只显示 `3`、`4`、`5`，默认选择 4，不再使用 Quick、Balanced、Deep Dive 等容易与模型推理强度混淆的名称。
- 新增与问题数同级的 `Question focus` 选择：`Main Idea` 聚焦中心思想、重要事件、人物目标或变化；`Detail` 聚焦支持理解的动作、顺序、线索、描写和因果；`Mixed` 按题数同时覆盖大意与有意义的细节，默认选择 Mixed。
- 每道主问题仍最多追加一次追问；第二次提交同题追问会被后端明确拒绝，不会继续调用模型。
- 所有题型都鼓励孩子用自己的总结、转述和解释来回答。评估依据改为概念是否理解，不因措辞、拼写或语法与参考答案不同而扣分，也不把仅复制原文视为更好的理解证据。

### 实现与数据兼容

- 会话创建 API 新增受限字段 `question_focus=main_idea|detail|mixed`，题量服务端限制为 3–5；生成提示会根据选择应用独立的出题策略，并明确禁止要求孩子摘抄、背诵或复现原句。
- SQLite Schema 升级到 v4，在 `reading_sessions` 增加 `question_focus`；旧阅读记录无损保留并自动标记为 `mixed`。孩子进行中的阅读和 Admin 历史报告都会显示本次选择的问题重点。
- 本次变更不修改 `reading_books`、`reading_chapters` 或 `data/reading-books` 的结构与内容；生产发布继续通过 `update_safe.sh` 对完整 `data/` 和 `.env` 做发布前快照、恢复及清单校验。

### 验证

- 全量自动测试通过：`46 passed`。新增验证 3/4/5 页面选项、Main Idea 与 Detail 提示、Mixed 题目配比、6 题请求拒绝、一次追问上限，以及从 Schema v3 升级时旧阅读记录仍存在且默认 focus 为 Mixed。
- Python 编译、Git 空白检查以及 Reading 与 Reading Admin 页面内联 JavaScript 语法检查通过。
- 开发提交 `0b83f72` 已从 `devBookReading` 合并为生产提交 `ae6231c`；`update_safe.sh` 创建发布前快照 `/www/wwwroot/learningcenter/backups/releases/20260904-113357-521798`，持久数据清单与 SQLite 完整性检查通过，Schema 迁移 1/2/3/4 均已登记且无外键违规。
- 发布前后均为 1 本书、24 个章节、1 次阅读记录和 4 道历史问题；已上传《Shoe Dog》的 PDF（1,232,646 bytes）与封面（144,176 bytes）逐文件 SHA-256 完全一致，书籍保持 Published。公网 Reading 页面与书架 API 正常，页面已显示 3/4/5、Main Idea/Detail/Mixed，服务保持 `enabled`、`active` 且近五分钟无 warning。

### 后续风险

- Main Idea、Detail 与 Mixed 的实际问题质量仍受所选模型及 PDF 文字提取质量影响；发布后应使用线上已上传书籍各生成一次，观察模型是否稳定遵循问题重点和自主表达规则。

## 2026-09-04：Book Reading 引导式阅读首版（已上线）

### 变更目的与用户可见结果

- 在 English 首页新增独立的 `Book Reading` 入口。孩子可从家长发布的书架中选择一本书及刚读完的 1–3 个章节，接受 3–6 个围绕所选内容即时生成的问题。
- 提问策略混合情节回忆、因果、人物动机、推理、基于线索的预测和适度想象，不使用固定关键词简单判对错；回答需要补充时最多追加一次有针对性的温和追问。
- 孩子当前使用键盘输入回答。语音入口在上线前验证中发现供应商转写接口不可用，按确认暂时移除，避免向孩子展示无法完成的操作。
- 完成后展示理解层级和鼓励性总结。家长在 `/admin/learningcenter/reading` 可查看每次阅读的完整问题、首次回答、追问与补充回答、即时反馈、参考理解、页内证据、逐题家长备注和整体评估。
- Audio Book 与开放式自由对话模式继续保持 Pending，本版没有加入对应入口或数据结构。

### 实现与数据

- Admin 支持上传不超过 80MB 的 PDF 和可选 JPG/PNG/WebP 封面、搜索书名/作者、编辑资料、修正章节页码、发布或归档。书籍上传后默认是草稿，必须由家长核对章节后再发布。
- 章节识别依次使用 PDF 书签目录、页首 Chapter/Part 标题和当前 AI 模型的保守辅助判断；无法识别时提供整本书范围供家长修改。当前要求 PDF 自带可选择文字层，扫描图片型 PDF 会标记为需要 OCR 并阻止发布。
- 修复 OpenAI 兼容接口把有效结果包在 Markdown JSON 代码块时被误判为空的问题；公共 AI 解析层现在兼容严格 JSON、Markdown fenced JSON 和带简短说明前缀的 JSON。目录请求改为只发送目录页与候选章节页，阅读问题按章节抽取首、中、尾片段并在失败时用更短上下文重试，避免长请求导致问题无法生成。
- Reading Admin 增加“用线上模型重新识别”操作；识别失败不再静默覆盖为 `Whole Book`，而是显示明确状态并保留原章节。重新识别成功后书籍回到草稿，要求家长核对后重新发布。
- 问题生成只发送所选章节的限量文字上下文，并要求不得剧透后续章节、不得向孩子索取个人隐私。孩子端使用随机访问凭证恢复进行中的阅读，数据库仅保存其 SHA-256 哈希；参考答案、证据和家长备注不会返回孩子端。
- SQLite Schema 升级到 v3，新增 `reading_books`、`reading_chapters`、`reading_sessions`、`reading_session_questions` 四张表。PDF 与封面保存到 `data/reading-books/<book-id>/`，现有全量 `data/` 快照和持久数据清单会自动保护这些资源。
- SQLite 首次建表遇到多 worker 同时切换 WAL 的短暂锁冲突时会做有限退避重试，避免 Schema v3 首次上线时因并发启动偶发失败。
- 新增根路径和 `/learningcenter` 前缀兼容的 Reading API；回答接口当前只接受文字输入。
- 性能与上下文边界进一步收紧：目录识别只发送聚焦片段，问题生成最多使用 16,000 字符并支持 7,000 字符降级重试，每次回答限制 1,500 字符，最终汇总最多使用 20,000 字符；书籍和阅读记录列表改为批量读取，消除逐条数据库查询。

### 验证

- 全量自动测试通过：`44 passed`，覆盖 Admin 会话保护、上传/识别/发布、公开书架、随机凭证、问题与追问、文字答案、完成评估、家长报告、聚焦目录请求和兼容接口 JSON 代码块解析。
- 使用真实三页 PDF 检查书签目录与文字提取，正确得到 `Chapter One`（第 1–2 页）和 `Chapter Two`（第 3 页）。
- 使用开发环境当时配置的兼容模型 `claude-opus-4-6-medium` 对实际上传的 320 页 PDF 验证：从第 5 个 PDF 页面中的 Table of Contents 正确识别出 24 个章节，并成功基于抽样后的所选内容生成 3 个理解/发散问题；已将该书的目录更新为 24 项并转回草稿。
- Python 编译、Git 空白检查以及 Reading、Reading Admin、English、Learning Admin 四个页面的内联 JavaScript 语法检查均通过。
- 生产分支发布提交为 `5fb3574`；`update_safe.sh` 创建发布前快照 `/www/wwwroot/learningcenter/backups/releases/20260904-111842-517732`，恢复后确认 48 个词库、3457 个词条、635 条 Skills、207 份练习报告、1133 个 Todo 任务、2833 条 Todo 历史及 2 条积分流水仍在，SQLite 完整性检查为 `ok`。
- 重启 `learningcenter.service` 后服务保持 `enabled`、`active` 且近五分钟无 warning；Schema 迁移 1/2/3 均已登记，四张 Reading 表存在，`pypdf 6.16.2` 可用。公网健康、English、Reading 页面与公开书架 API 均返回 HTTP 200，Admin 页面未登录时 303 跳转登录，Admin API 返回 401。生产健康接口当前报告模型为 `gpt-5.4-nano`。

### 后续风险

- 本次变更先在独立 `devBookReading` 分支开发和验证，随后按确认合并到 `deploy/tencent-learningcenter-path`、推送远端并通过 `update_safe.sh` 发布；发布过程继续先快照并恢复服务器原有 `data/` 和 `.env`，不会用本地测试书籍覆盖线上数据。
- 扫描图片型 PDF 尚未接 OCR/Vision；正式使用中仍需继续观察不同排版书籍的目录准确度、模型费用与延迟。
- 当前配置的 OpenAI 兼容服务已验证可完成目录识别、问题生成和回答评估，但其 `/audio/transcriptions` 接口返回 HTTP 403，因此语音相关页面、接口和配置已在本次上线前暂时移除；以后接入可用的独立转写服务后再恢复。
- 当前按一次阅读生成并保存完整问题集；较长章节会对文字做首、中、尾抽样以控制上下文和费用，极长章节的细节覆盖需要通过实际书目继续校准。

## 2026-09-03：Jingsen.cc 首页与 Learning Center 视觉重构上线

### 变更目的与用户可见结果

- 将本日完成的个人首页、统一 Admin、Gallery 瀑布流、Learning Center 门户、English、Learning Todo 与 Learning Admin 视觉重构正式发布到生产环境。
- 根域名 `https://jingsen.cc/` 从宝塔默认站点页切换为新的个人主页，`/admin`、`/gallery` 与 `/baseball` 同时成为可直接访问的全站一级路径。
- `https://jingsen.cc/learningcenter/portal` 的地址和“Learning Center 课程选择入口”职责保持不变；页面内容更新为本次确认的新版视觉，现有 English、Todo 与 Admin 入口继续使用原路径。
- Chinese 与 Math 暂时展示风格一致的“正在建设中”页面；English、Todo 及其后台数据和功能继续保留。

### 发布、回档与数据保护

- 功能版本提交为 `672a363`，生产分支为 `deploy/tencent-learningcenter-path`。
- 发布前线上实际代码 `f28e946` 已建立并推送标签 `rollback-pre-redesign-20260903`，作为本次视觉重构的代码回档点。
- `update_safe.sh` 在同步代码前完成 `data/`、一致性 SQLite 和 `.env` 快照；首轮发布快照位于 `/www/wwwroot/learningcenter/backups/releases/20260903-152654-229698`。
- 原 Nginx 站点配置备份为 `/www/server/panel/vhost/nginx/jingsen.cc.conf.pre-redesign-20260903`。新增根路径与 `/static/` 反向代理，同时保留 `/learningcenter/` 前缀代理和 `/learningcenter` 到 `/learningcenter/` 的兼容跳转。
- 修正 `update_safe.sh` 的词库专项凭据：凭据现在始终记录 `library_registry.json` 与 `library_archive.json`，不再把运行后会发生正常页级变化的整个 SQLite 文件误当作词库哈希，避免发布后产生数据丢失的假告警；完整数据清单仍在迁移前验证 SQLite 原样恢复。

### 验证

- 发布前全量测试通过：`40 passed`；14 段静态页面内联脚本通过语法检查，`git diff --check` 通过。
- 安全发布脚本确认快照与恢复后的持久数据清单一致；SQLite 快照与运行库均通过 `integrity_check` 和外键检查。
- 发布后快照库与运行库的主要业务表记录数完全一致：48 个词库、3457 个词条、635 条 Skills、205 份练习报告、1128 个 Todo 任务、2818 条 Todo 历史和 2 条积分流水；词条按“词库、内容、规范化内容、顺序”计算的语义哈希一致。
- 公网逐项检查首页、Learning Center 门户、English、Chinese、Math、Todo、Gallery、Baseball、Admin、共享样式与公开 API，均返回 HTTP 200；浏览器实际检查首页、`/learningcenter/portal`、Todo 和 Admin 登录页正常渲染。
- Nginx 配置在替换前后均通过 `nginx -t`，`learningcenter.service` 保持 active，内部与公网健康接口正常。

### 后续风险

- 代码回档时需同时恢复上述 Nginx 备份，才能让根域名重新回到发布前的宝塔静态站点行为；服务器持久数据应优先使用发布快照恢复，禁止用 Git 中的数据覆盖。
- SQLite 服务启动可能在不改变词条内容和顺序的情况下重写内部自增 ID 与时间戳，因此发布后使用专项 JSON 凭据与业务记录比对验收，不使用整个运行中 SQLite 文件的 SHA-256 作为唯一判断。

## 2026-09-03：Learning Center 前后台视觉统一与 English 重构（已上线）

### 变更目的

- 统一 Learning Center 前后台的字体、文字颜色、导航和紧凑信息密度，尤其确保中文内容始终使用无衬线字体。
- 将 English 学习区从圆角玻璃拟态界面适配为与个人主页一致的编辑感设计，同时完整保留现有练习能力。
- 在 Chinese 与 Math 内容继续开发期间提供明确、统一的建设中状态页。

### 用户可见结果

- Learning Admin 六类页面统一采用 `Manrope + Noto Sans SC` 字体栈；蓝色面板中的主要数字和说明改为白色高对比文字，浅色面板继续使用黑色或深灰文字。
- “新增词库”“刷新词库”从后台页头移至四个管理模块下方的“词库操作”区域，操作层级更清晰。
- Learning Admin 首页、新建词库、词库详情、Skills、Todo 和模型选择六类页面的首行导航统一为单行 `BACK2ADMIN | Learning Center`；`BACK2ADMIN` 返回全站 Admin，`Learning Center` 返回 Learning Admin 首页。
- 模型选择页移除右上角“退出 Admin”和“保存选择”按钮；筛选栏继续保留“刷新列表”和“保存选择”，模型设置能力不受影响。
- Todo 管理的九项视图标签不再使用仅适合拉丁字符的等宽字体，改用与正文一致的 `Manrope + Noto Sans SC` 无衬线字体栈，并将字号从 10px 提升至 13px、标签高度提升至 40px。
- Learning Admin 首页、新建词库、词库详情、Skills、Todo 与模型选择的主标题在桌面端统一为 36px、移动端统一为 30px，并使用相同字重、行高与字距；移除 Todo、模型页原先单独使用的 25px 视觉差异。
- Todo 管理的今日概览、周月统计和积分统计卡移除装饰性小图标，统一改为“大字号指标名称 + 数字”的单行表达；指标名称为 17px、数字为 31px，并继续使用原有四色状态区分。
- 上述统计卡进一步改为左右两端布局：指标名称位于左下、数值位于右下，二者按卡片底边对齐，便于快速横向比较四项数据。
- English 首页及 Word Palace、Daily Word、Vocabulary Skills、MAP Test、Language Arts、Reading、Daily Reports 等现有视图共用纸张底色、黑色细边框、直角面板和蓝色/荧光黄色状态色；表单、题目、报告和加载状态也随共享主题统一。
- English 页面顶部使用 `BACK2LEARNING / 03 / LANGUAGE / ENGLISH` 三栏导航，进入子模块后自动回到页面顶部，避免切换后标题或导航被当前滚动位置裁掉。
- Chinese 与 Math 入口现在分别展示 `01 / LANGUAGE`、`02 / LOGIC` 的“正在建设中”页面，并可返回 Learning Center；原业务接口及旧页面文件保留，便于以后继续开发。

### 实现与验证

- 新增 `static/learning_front_theme.css` 与 `static/learning_construction.html`，并增加共享样式静态路由；English 业务脚本和 API 未改动。
- 本地浏览器实际检查 English 首页、Word Palace、Daily Word 和 MAP Language Arts，模块切换、技能数据加载和表单展示正常，页面无横向溢出。
- 本地浏览器逐页复核 Learning Admin 的首页、新建、详情、Skills、Todo、模型六类页面，字体栈一致且均无横向溢出；六页面包屑内容与链接目标一致，三个元素处于同一水平线；模型页头按钮数量为 0，筛选栏保存按钮仍可用。
- 全量测试通过：`40 passed`；18 段静态页面内联脚本通过语法检查，`git diff --check` 通过。
- 已随本日 Jingsen.cc 首页与 Learning Center 视觉重构正式上线。

### 后续风险

- Google Fonts 无法访问时会依次回退到系统自带的苹方、微软雅黑和 Arial，仍保持无衬线显示。
- Chinese 与 Math 暂时只展示建设中页面，重新开放练习功能时需将对应路由切回保留的原页面并按共享主题继续适配。

## 2026-09-03：Learning Center Admin 全页面紧凑主题（已上线）

### 变更目的

- 将 Learning Center 后台首页及全部子页面统一到个人主页的编辑感设计语言。
- 按反馈控制信息密度，避免超大标题、大面积卡片和过多空白，让管理操作尽量集中在首屏。

### 用户可见结果

- `/admin/learningcenter`、`new`、`library`、`skills`、`todo`、`models` 六类页面统一使用纸张底色、黑色细边框、直角组件、蓝色/荧光黄色/橙色/紫色状态色和紧凑字体层级。
- Learning Center 管理首页的四个模块入口改为紧凑彩色导航板，筛选器与词库表格直接跟随其后。
- 新建词库与词库详情缩短输入区和间距；词库详情的元信息、词条和两个保存操作可在 720px 高桌面首屏内完整显示。
- Skills 将筛选、四项统计和数据表压缩排列，桌面首屏可显示 6 行知识点。
- Todo 管理保留全部 9 个视图，缩短顶部、标签、统计卡和面板高度；模型管理使用四列紧凑模型网格。

### 实现与验证

- 新增共享样式 `static/admin_learning_theme.css`，由六个页面共同引用，并通过 `/static/admin_learning_theme.css` 提供；页面业务脚本与数据接口未改动。
- 本地浏览器逐页检查六类页面均无横向溢出；Todo 管理的今日概览、任务、日、周、月、统计、积分、科目和设置视图全部可正常切换。
- 全量测试通过：`40 passed`；17 段静态页面内联脚本通过语法检查，`git diff --check` 通过。
- 已随本日 Jingsen.cc 首页与 Learning Center 视觉重构正式上线。

## 2026-09-03：Learning Todo 编辑风格视觉预览（已上线）

### 变更目的与结果

- 按个人主页与新版 Learning Center 的设计语言，为公开 Learning Todo 页面制作一版可回退的视觉预览。
- 顶部改为 `BACK2LEARNING / 04 / RHYTHM / 日期` 三栏导航；首屏使用超大标题和蓝色几何线条。
- 今日进度与学习积分改为蓝色、荧光黄色并列信息板，任务分组与任务卡片改用直角边框、大字号标题和栏目式排版。
- 根据首轮预览反馈压缩标题区：标题与说明改为左右两栏，降低字号和留白，并将统计信息板提前到首屏完整展示。
- 桌面端任务区进一步改为“逾期 / 待完成 / 已完成”三栏看板，并缩小分组标题、卡片内边距、控件和卡片间距；820px 以下仍使用单列布局。
- 保留原有真实数据读取、Demo 数据、任务完成、取消完成、撤销、积分刷新和 Admin 管理逻辑，仅修改 `static/todo.html` 的展示层。

### 验证与风险

- 使用 `?demo=1` 在本地浏览器检查完整页面，进度与积分卡片等高、页面无横向溢出。
- 在 1280×720 视口复查压缩版首屏：标题区高度 250px，统计区位于第 356–632px，今日完成数与可用积分均完整显示在首屏内。
- 在 1280px 宽桌面视口检查任务看板，三列宽度均约 381px，逾期、待完成、已完成任务互不遮挡且无横向溢出。
- 实际操作“完成逾期任务”后数量从 `2` 变为 `1`、已完成从 `2` 变为 `3`，随后撤销恢复原值，确认核心交互未受视觉改版影响。
- 已随本日生产发布上线；如不采用此方向，仍可单独回退 Todo 页面视觉。

## 2026-09-03：二级页面视觉统一与首页滚动文案配置（已上线）

### 变更目的

- 统一 Learning Center、Gallery、Baseball 三个二级空间的导航语言和栏目编号位置。
- 让 Learning Center 与新个人主页保持同一套编辑感视觉，同时完整保留原有入口。
- 允许站长从首页管理中修改荧光滚动条文案。

### 用户可见结果

- 首页顶部品牌字样统一为 `JINGSEN.cc`，其中 `JINGSEN` 使用大写、`cc` 保持小写，蓝色圆点样式不变。
- 三个二级页面左上角统一显示 `BACK2INDEX` 并返回 `/`；顶部正中分别显示 `01 / LEARN`、`02 / SEE`、`03 / PLAY`。
- Learning Center 门户改为大字号标题、几何装饰和不对称彩色卡片网格，继续提供 Chinese、Math、English、Learning Todo 与 Admin 五个入口，Admin 密码验证流程保持不变。
- `/admin/index` 的“主页文字”区域新增“荧光滚动条文字”，保存后首页四组循环文案同步更新。
- 修复 Baseball 右侧棒球装饰覆盖 `On deck.` 标题和说明文字的问题；正文现在固定在装饰图形之上。
- 修复 Gallery 无内容状态下 `Developing.` 标题下沉笔画与说明文字重叠的问题，扩大标题行高和段落间距。

### 实现说明

- 滚动文案作为 `homepage_settings` 的 `ticker` 字段写入现有 `app_state`，旧数据缺少该字段时自动使用当前默认文案，不涉及 Schema 迁移。
- Baseball 正文建立独立前景层，装饰球固定在背景层并禁止接收指针事件。

### 验证与风险

- 全量测试通过：`40 passed`；17 段静态页面内联脚本通过语法检查，`git diff --check` 通过。
- 本地浏览器逐页检查三个二级页面：返回入口与栏目编号纵向位置一致，编号中心相对视口偏移均为 0，页面无横向溢出；Baseball 装饰不再盖住正文。
- Learning Center 门户及后续确认的 English 学习区已完成视觉适配，并随本日生产发布上线。

## 2026-09-03：Admin 信息架构重构与 Gallery 瀑布流（已上线）

### 变更目的

- 将原先以 Learning Center 词库为首页的 Admin 重构为全站统一内容管理入口。
- 按 Index、Learning Center、Gallery、Baseball 四个空间组织前后台结构。
- 让 Gallery 可以真正上传、管理并公开展示拍摄内容。

### 用户可见结果

- `/admin` 改为统一管理中枢，登录后可进入首页管理、Learning Center 管理、Gallery 管理和 Baseball 管理。
- 首页管理迁移至 `/admin/index`。
- 原 Learning Center 后台整体迁移至 `/admin/learningcenter`，继续包含词库、Skills、Learning Todo 和 AI 模型管理；具体子页面统一放在 `/admin/learningcenter/*`。
- `/admin/gallery` 支持选择照片、预览、上传发布、编辑标题/说明/地点/日期/无障碍描述，以及从公开 Gallery 中移除。
- `/gallery` 改为响应式摄影瀑布流，根据原图比例自然排列，支持懒加载和无内容状态。
- Baseball 的公开页面和 `/admin/baseball` 管理页面按要求保持为预留空白状态。
- 上一版 `/admin/homepage`、`/admin/todo` 等地址及 `/learningcenter/admin*` 继续通过 308 重定向兼容旧书签。

### 实现与数据说明

- Gallery 元数据写入现有 SQLite `app_state`，不增加数据表、不改变 Schema 版本。
- 图片使用内容哈希命名并保存到 `data/gallery-assets/`，单张支持 JPG、PNG、WebP，限制 15MB；现有全量 data 快照与清单校验会自动保护这些文件。
- 从 Gallery 移除内容只撤下元数据，原始图片文件继续保留在 data 中，便于审计和人工恢复。
- Gallery 公开读取与图片接口位于 `/api/site/gallery*`；上传、编辑、移除接口位于 `/api/admin/gallery*` 并复用现有 Admin 会话。
- 词库管理 API 与 Skills 修改接口现在也要求有效 Admin 会话，避免绕过页面登录直接修改 Learning Center 数据；Skills 的公开读取接口保持不变。

### 验证

- 新增 Gallery 服务与路由测试，覆盖上传、元数据编辑、公开读取、图片读取、移除保留原文件，以及新 Admin 路由和旧地址兼容。
- 全量测试通过：`40 passed`。
- 所有静态页面的内联 JavaScript 均通过语法检查。
- 已随本日 Jingsen.cc 首页与 Learning Center 视觉重构正式上线。

### 后续风险

- Gallery 当前保留上传原图，没有生成多尺寸缩略图；大量高分辨率照片上线后可增加服务端缩略图和响应式 `srcset`。
- Baseball 内容类型尚未确定，当前没有数据模型与编辑控件。

## 2026-09-03：Jingsen.cc 个人主页与统一 Admin 入口（已上线）

### 变更目的

- 将根域名从 Learning Center 的直接跳转升级为更具个人主页气质的入口页。
- 首期集中展示 Learning Center、Gallery、Baseball 三个栏目，并让主页主要内容与大图可由 Admin 更新。
- 将原先挂在 Learning Center 路径下的后台页面统一迁移到 `/admin`。

### 用户可见结果

- `/` 提供全新响应式个人主页，采用编辑感排版、鲜明色彩与三张栏目卡片。
- Learning Center 继续通过 `/learningcenter` 进入现有学习门户；Gallery 与 Baseball 先提供风格一致的栏目预告页。
- Learning Center 门户顶部新增 `Jingsen.cc / Index` 返回入口，方便从学习空间回到个人主页。
- `/admin/homepage` 新增首页设置，可编辑主标题、简介、图片角标、无障碍描述，以及三个栏目的名称、简介、按钮和链接。
- 支持上传 JPG、PNG、WebP 主视觉（最大 10MB），也可恢复项目内置默认图。
- `/learningcenter/admin` 及其既有子页面使用 HTTP 308 重定向至对应 `/admin` 地址；Learning Center 门户内的 Admin 入口完成验证后也跳转到 `/admin`。

### 实现与数据说明

- 首页文字配置写入现有 SQLite `app_state`，不新增表或改变 Schema 版本。
- 自定义主视觉以内容哈希命名，保存在 `data/homepage-assets/`；因此会被现有全量 data 快照、恢复和清单校验流程覆盖。
- 首页读取接口为 `/api/site/homepage`，图片接口为 `/api/site/homepage/hero`；修改、上传和恢复接口均受现有 Admin 会话保护。
- 默认主视觉由内置 imagegen 工作流生成，项目文件为 `static/assets/homepage-hero.webp`；画面以笔记本、相机与棒球对应三个首发栏目，无人物肖像和品牌标识。WebP 交付文件约 75KB，保留 1536×1024 尺寸以兼顾清晰度与首屏加载速度。

### 验证

- 新增首页服务与路由测试，覆盖默认设置、持久化修改、图片替换/恢复、Admin 鉴权、不安全链接拒绝，以及旧 Admin 路由重定向。
- 本地浏览器完成桌面端与 390px 移动端验收，无横向溢出；同时检查 Admin 登录页、编辑表单和主视觉预览。
- 已随本日生产发布上线，根域名 Nginx 代理同步调整为应用入口。

### 后续风险

- Gallery 与 Baseball 当前为首版预告页，正式内容模型及其后台管理需在后续迭代补充。
- 上线前需确认 Nginx 根域名 `/` 已反向代理到本应用，而非继续强制跳转到 `/learningcenter/`。

## 2026-09-03：建立强制更新日志制度

- 将“每次重要更新后主动补充 `CHANGELOG.md`”设为仓库级维护规则。
- 新增 `AGENTS.md`，确保以后重新进入项目时仍会加载该约定。
- 日志至少应说明变更原因、结果、关键实现或运维信息、验证结果及后续风险。
- 只维护更新日志本身时不再递归增加无意义条目。

## 2026-09-02 至 2026-09-03：服务器套餐升级与恢复

### 变更目的

腾讯云轻量应用服务器升级到通用型套餐：

- CPU：4 核。
- 内存：16GB（操作系统内显示约 15GiB）。
- SSD 系统盘：220GB。
- 峰值带宽：35Mbps。
- 月流量包：6144GB。

本次是原实例套餐升级，不是迁移或重装。公网 IP、域名解析、防火墙、登录凭据、快照、宝塔配置、Nginx 配置和 SSL 证书均保留。

### 升级后现象

- Nginx 与 HTTPS 正常，但网站及健康接口返回 `502 Bad Gateway`。
- `127.0.0.1:8088` 没有进程监听。
- 云盘设备 `/dev/vda` 已识别为 220GB，但根分区 `/dev/vda1` 仍为 40GB。
- `learningcenter.service` 持续自动重启并报 `status=203/EXEC`。
- 四个 cloud-init 阶段因解释器无执行权限而启动失败。

### 根因

1. `/etc/systemd/system/learningcenter.service` 的旧 `ExecStart` 指向已经不存在的：

   ```text
   /www/wwwroot/learningcenter/app/.venv/bin/python
   ```

2. 服务器真正可用的生产 Python 环境位于：

   ```text
   /www/server/pyporject_evn/versions/3.11.15/
   ```

3. 系统解释器 `/usr/bin/python3.11` 被异常改成 `www:www 0644`，缺少执行权限。`/usr/bin/cloud-init` 的 shebang 使用该解释器，因此 cloud-init 无法运行，系统盘也没有自动扩展。

### 已执行修复

1. 通过 RPM 元数据恢复系统 Python 的属主和权限，修复后为 `root:root 0755`。
2. 保留原 systemd unit，并增加覆盖配置：

   ```text
   /etc/systemd/system/learningcenter.service.d/runtime.conf
   ```

   当前有效配置使用 `www` 用户及两个 Gunicorn worker：

   ```ini
   [Service]
   User=www
   ExecStart=
   ExecStart=/www/server/pyporject_evn/versions/3.11.15/bin/gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --timeout 180 --graceful-timeout 30 --bind 127.0.0.1:8088
   ```

3. 执行 `systemctl daemon-reload` 并启动 `learningcenter.service`；服务保持 `enabled` 和 `active`，可随系统启动。
4. 扩容前将原分区表保存到：

   ```text
   /root/vda-partition-table-before-expand-20260902-2358.sfdisk
   ```

5. 使用 `growpart /dev/vda 1` 将第一个分区扩展到整盘，再使用 `xfs_growfs /` 在线扩展 XFS 文件系统。
6. 清除本次启动遗留的 cloud-init failed 状态；没有强制重新运行初始化流程。

### 修复后验证

- CPU：4 核。
- 内存：15GiB，总可用约 14GiB。
- 根文件系统：XFS 220GB，检查时已用约 16GB、可用约 205GB。
- `learningcenter.service`：`enabled`、`active`。
- Gunicorn：主进程加两个 worker，监听 `127.0.0.1:8088`。
- 本地 `/health`：HTTP 200，返回 `healthy`。
- 公网首页跟随跳转后：HTTP 200。
- `/learningcenter/todo`、`/learningcenter/admin`、`/learningcenter/english`：HTTP 200。
- Nginx：正常运行。
- SSL：Let's Encrypt，覆盖 `jingsen.cc` 与 `www.jingsen.cc`，当时查得有效期至 2026-11-14。
- 持久数据结构校验通过：28 个 JSON、1 个 SQLite 数据库、42 个词库 TXT；词库、归档、Skills、Daily Reports、模型设置、Todo、积分流水均存在。
- 修复过程中没有重新部署代码，也没有覆盖线上业务数据。

### 后续排查提示

- 遇到 502 时，先检查：

  ```bash
  systemctl status learningcenter.service --no-pager -l
  ss -lntp | grep 8088
  curl -fsS http://127.0.0.1:8088/health
  ```

- 不要把 service 改回已经不存在的 `app/.venv/bin/python`。
- 若再次升配磁盘，必须同时比较 `lsblk` 与 `df -h /`；云盘容量变大不代表分区和文件系统已经同步扩展。
- `systemctl --failed` 曾显示虚拟机上的 `ipmi.service` 失败，与本项目及网站服务无关。

## 2026-09-02：GPT-5 出题延迟优化

提交：`9b8d286`、`f28e946`

- GPT-5 系列模型生成题目时增加 `reasoning_effort=minimal`，减少不必要的推理耗时。
- 非 GPT-5 模型不发送该参数，避免破坏其他兼容模型。
- 为兼容生产环境使用的旧版 OpenAI Python SDK 1.x，参数通过 `extra_body` 传递。
- 增加测试，覆盖 GPT-5 与非 GPT-5 两类请求。

## 2026-08-24：可审计的积分与连续记录修正

提交：`a3f3ff7`

- Admin Todo 新增积分修正入口，支持正数和负数调整。
- 每笔修正必须填写原因和生效日期，并写入积分流水，便于以后追溯。
- 支持保留或清除指定日期的连续完成记录，可修复误删任务造成的历史缺口。
- 可用积分公式扩展为：连续完成积分 + Reward 积分 + 人工修正 - 已支出积分。
- 增加 API、数据校验、界面和测试覆盖；部署校验明确包含 `points-ledger.json`。

## 2026-08-21：统一迁移 SQLite 与异步分批出题

提交：`11ba06c`、`6a3222d`、`04e5695`、`aa3664a`

### SQLite 统一持久化

- 运行时主数据切换到 `data/learning-center.sqlite3`，启用 WAL 模式。
- 词库、归档词库、Skills、练习报告、模型设置、Learning Todo 和积分流水统一纳入关系型数据结构。
- 旧 JSON/TXT 数据支持幂等、无损迁移，并继续作为部署备份和回滚资料保留。
- 增加 SQLite 完整性检查、外键检查、迁移脚本和旧格式导出脚本。
- `update_safe.sh` 增加 SQLite 一致性快照、迁移与部署后验证。
- Schema 版本为 v2，字段定义见 `SQLITE_DATABASE_SCHEMA.md`。

### Word Palace 异步出题

- Daily Word 的普通 `cloze` / `match` 和 Vocabulary Skills 改为后台分批生成。
- 创建任务后立即返回 `job_id`；首批 3 题完成后即可开始练习，后续题目继续生成。
- 生成任务、进度和题目保存在 SQLite `generation_jobs` 表，可由多个 Gunicorn worker 共享。
- 增加任务取消、超时、过期清理、断线恢复和前端进度展示。

当时完整测试结果：`33 passed`。

## 2026-08-10：Todo Reward、积分支出、词库归档与模型管理

提交：`7fceee4`、`665af27`、`6359fab`、`def625b`

### Todo 与 Reward

- 单次任务和重复任务模板可设置 Reward 目标与点数。
- 每个任务实例独立完成、家长确认和发放；接口保持幂等，避免重复加分。
- 增加积分支出流水，可用积分同时显示获得来源与支出去向。
- 家长端增加日期筛选、日视图确认和相关统计。

### 词库和模型

- 增加独立词库归档、查看和恢复流程；归档词库不参与出题。
- 增加 Admin 模型选择页面，可读取当前 API Key 可用模型并保存全站默认模型。
- API Key 始终保留在服务端，不下发浏览器。

### 部署安全

- 部署前强制检查活动词库与归档词库。
- 快照后执行逐字节和 SHA-256 校验。
- 完整保护词库、Skills、Daily Reports、模型设置、Todo、积分流水及 `.env`。
- 修正部署中新建数据的属主，保持 `www` 用户可写。

## 2026-07-28：Learning Todo 首次上线与安全发布流程

提交：`7ec62a6`

- 新增孩子端 `/learningcenter/todo` 和家长端 `/learningcenter/admin/todo`。
- 支持单次、每天、每周、每月任务，任务复制、科目管理、完成/取消完成、评语和统计。
- 加入 Admin 会话保护。
- 新增 `update_safe.sh`、持久数据检查、缺失数据合并和发布前完整快照。
- 确立“服务器真实 `data/` 与 `.env` 不被代码更新覆盖”的部署原则。
- 建立永久手工恢复基线：

  ```text
  /www/wwwroot/learningcenter/backups/manual-pre-todo-20260728-220002
  ```

## 2026-06-17：Daily Word 短文填空

提交：`63c51c8`

- Daily Word 增加 `Passage Cloze` 题型。
- 改进短文生成、干扰项、答题交互、批改结果和部署说明。

## 2026-05-10 至 2026-05-11：MAP、Skills、报告与安全更新脚本

提交：`4849070`、`4dc95fe`、`f2552d8`、`e2e4076`

- English Learning 拆分为 Word Palace 与 MAP Test。
- 上线 MAP Language Arts 的出题、答题、评估和报告流程。
- 建立 Skills 数据结构与管理页面，导入 Language Arts、Reading 和 Vocabulary Skills 数据。
- 上线 Vocabulary Skills 诊断练习、弱项分析和推荐练习。
- 建立统一 Daily Reports 展示。
- 创建并加强 `update_safe.sh`，形成线上数据先备份、再更新、再恢复和校验的流程。
- MAP Reading 已导入 Skills 数据，但完整出题/评估流程仍为后续项目。

## 2026-04-19：词库持久化改为服务器本地文件

提交：`b46ac0e`

- 取消当时对 PostgreSQL 的依赖，改用服务器本地文件管理词库。
- 为之后的 SQLite 统一迁移保留了清晰的本地数据边界。

## 2026-03-18：生产路径与数学入口

提交：`15ddd43`

- 应用支持部署在 `/learningcenter` URL 前缀下。
- 增加数学页面入口。
- 调整多个页面在带前缀环境下的跳转和资源路径。

## 2026-01：项目建立与语文体验完善

主要提交：`06a8bab`、`648d7af`、`53bb9b6`、`104cbf7`、`daf8393`

- 建立 Jingsen Learning Center 1.0。
- 完善语文填空、成语生成和关联词练习。
- 修复页面重定向与交互问题，形成后续多学科学习中心的基础结构。

## 当前生产运维基线

### 路径与服务

```text
应用目录     /www/wwwroot/learningcenter/app
持久数据     /www/wwwroot/learningcenter/app/data
发布快照     /www/wwwroot/learningcenter/backups/releases/<时间>
最新快照     /www/wwwroot/learningcenter/backups/latest
systemd      learningcenter.service
内部监听     127.0.0.1:8088
公网入口     https://jingsen.cc/learningcenter/
```

### 正常发布

```bash
cd /www/wwwroot/learningcenter/app
bash update_safe.sh
```

脚本成功后仍需重启或平滑重载应用进程，再完成健康检查。不要直接上传本地 `data/` 覆盖线上数据，也不要删除 `backups/releases/`。

### 发布后快速检查

```bash
systemctl is-enabled learningcenter.service
systemctl is-active learningcenter.service
curl -fsS http://127.0.0.1:8088/health
curl -I https://jingsen.cc/learningcenter/
lsblk
df -hT /
```

### 数据验证

```bash
cd /www/wwwroot/learningcenter/app
/www/server/pyporject_evn/versions/3.11.15/bin/python3 \
  scripts/validate_persistent_data.py data \
  --require-file library_registry.json \
  --require-file library_archive.json \
  --require-file learning-todo/points-ledger.json
```

更完整的部署与恢复说明见 `DeployToDo.md`、`updateNew.md`、`README.md` 和 `docs/sqlite-relational-migration-plan.md`。

# Jingsen Learning Center 更新日志与运维纪要

本文记录重要功能、数据架构和线上运维变更，供后续开发、部署、故障排查和恢复时查阅。

- 记录顺序：新记录在前。
- 代码依据：Git 提交、仓库文档及实际线上检查结果。
- 安全约定：不在本文记录密码、API Key、私钥或其他凭据。
- 当前生产分支：`deploy/tencent-learningcenter-path`。
- 当前公网入口：`https://jingsen.cc/learningcenter/`。

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

# 腾讯云宝塔面板部署手册 — jingsen.cc/learningcenter

> 目标：在已安装宝塔面板的腾讯云 2c2g 轻量服务器上，将 Jingsen 学习中心部署到 `https://jingsen.cc/learningcenter`。
>
> 宝塔面板让 Nginx、数据库、Python 环境、进程守护全部可以在网页操作，无需大量手敲命令。

---

## 前置确认

| 条件 | 状态 |
|------|------|
| 域名 `jingsen.cc` 已购买 | ✅ |
| SSL 证书已购买 | ✅ |
| 2c2g 轻量服务器已购买 | ✅ |
| 宝塔面板已安装，Nginx 已在宝塔中安装 | ✅ |

---

## 步骤一：登录宝塔面板，安装必要软件

1. 浏览器打开宝塔面板地址（通常是 `http://服务器IP:8888`）
2. 进入 **软件商店**，确认以下软件已安装：
   - **Nginx**（已安装 ✅）
   - **PostgreSQL**（搜索安装，推荐 14 或 15 版本）
   - **Python 项目管理器**（搜索 "Python" 安装宝塔的 Python 管理器）

> 以上都是直接点「安装」，等待完成即可。

---

## 步骤二：在宝塔中创建 PostgreSQL 数据库

1. 宝塔左侧菜单 → **数据库** → 选择 **PostgreSQL**
2. 点击 **添加数据库**：
   - 数据库名：`jingsen_db`
   - 用户名：`jingsen`
   - 密码：设置一个强密码，**记下来**
3. 点击确定，创建完成。

记下连接串（后面配置环境变量用）：

```
postgresql://jingsen:你设置的密码@localhost:5432/jingsen_db
```

---

## 步骤三：上传代码到服务器

**方式 A（推荐）：SSH 终端 git clone**

在宝塔面板右上角点 **终端**，或用本地 SSH 连接服务器：

```bash
mkdir -p /www/wwwroot/jingsen
cd /www/wwwroot/jingsen
git clone https://github.com/你的GitHub用户名/Jingsen-LearningCenter-V1.git learningcenter
```

**方式 B：宝塔文件管理器上传**

1. 宝塔左侧 → **文件** → 进入 `/www/wwwroot/`
2. 新建文件夹 `jingsen/learningcenter`
3. 将本地项目打包成 `.zip`，通过宝塔文件管理器上传并解压

---

## 步骤四：配置环境变量文件

在宝塔终端中执行：

```bash
nano /www/wwwroot/jingsen/learningcenter/.env
```

填入以下内容（替换 `<>` 内的值）：

```env
OPENAI_API_KEY=<你的API Key>
OPENAI_BASE_URL=<接口地址，如 https://api.openai.com/v1>
MODEL_NAME=gpt-3.5-turbo
PORT=8000
DATABASE_URL=postgresql://jingsen:<你设置的密码>@localhost:5432/jingsen_db
```

保存：`Ctrl+O` → `Enter` → `Ctrl+X`

---

## 步骤五：用宝塔 Python 项目管理器部署应用

1. 宝塔左侧 → **软件商店** → 已安装 → 打开 **Python 项目管理器**
2. 点击 **添加项目**：

| 字段 | 填写内容 |
|------|----------|
| 项目名称 | `jingsen-lc` |
| 项目路径 | `/www/wwwroot/jingsen/learningcenter` |
| Python 版本 | 3.11（或可用的最新版） |
| 启动文件 | `main.py` |
| 启动方式 | `gunicorn` |
| 启动命令（自定义） | 见下方 |
| 端口 | `8000` |

**启动命令填写：**

```
gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 127.0.0.1:8000
```

3. 点击 **确定**，宝塔会自动：
   - 创建虚拟环境
   - 安装 `requirements.txt` 中的依赖
   - 启动应用并配置开机自启

4. 看到项目状态变为 **运行中** 即成功。

> 如果宝塔 Python 管理器未自动加载 `.env`，在「环境变量」选项卡里手动添加上面 `.env` 中的 5 个变量。

---

## 步骤六：在宝塔中配置 SSL 证书

1. 宝塔左侧 → **SSL** 或通过**网站**管理进入
2. 如果已有腾讯云下载的证书文件，选择 **其他证书**：
   - 将 `.crt` 文件内容粘贴到「证书（PEM格式）」框
   - 将 `.key` 文件内容粘贴到「私钥」框
3. 点击保存，宝塔自动将证书配置到 Nginx。

---

## 步骤七：在宝塔中配置 Nginx 反代

1. 宝塔左侧 → **网站** → **添加站点**：
   - 域名：`jingsen.cc`
   - 不需要创建数据库，不需要 FTP
   - PHP 版本选「纯静态」
2. 站点创建后，点击站点域名进入**站点设置**
3. 点击 **SSL** 选项卡 → 关联刚才配置的证书，开启 HTTPS
4. 点击 **配置文件** 选项卡，找到 `server { listen 443 ...}` 块，在其中添加反代配置：

在 `server_name` 行下方、最后一个 `}` 前，加入：

```nginx
# HTTP → HTTPS
# （宝塔开启 HTTPS 后会自动处理，无需手动添加）

# /learningcenter 反代到 FastAPI
location /learningcenter {
    rewrite ^/learningcenter(/.*)?$ $1 break;
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
}
```

5. 点击 **保存**，宝塔自动重载 Nginx。

---

## 步骤八：配置域名 DNS 解析

登录**腾讯云 DNS（DNSPod）**控制台，添加以下 A 记录：

| 主机记录 | 记录类型 | 记录值 |
|----------|----------|--------|
| `@` | A | 服务器公网 IP |
| `www` | A | 服务器公网 IP |

DNS 生效约需 1～10 分钟。

---

## 步骤九：在腾讯云控制台开放防火墙端口

进入**腾讯云轻量服务器控制台 → 防火墙**，确认以下规则存在：

| 端口 | 协议 | 用途 |
|------|------|------|
| 80 | TCP | HTTP（自动跳转 HTTPS） |
| 443 | TCP | HTTPS 访问 |
| 22 | TCP | SSH / 宝塔终端 |
| 8888 | TCP | 宝塔面板（可选，不用后可关闭） |

> **8000 端口不需要开放**，FastAPI 只在服务器内部监听，由 Nginx 转发。

---

## 步骤十：验收测试

| 验收项 | 操作 |
|--------|------|
| Python 项目在运行 | 宝塔 Python 管理器 → 状态显示「运行中」 |
| 本地接口可达 | 宝塔终端：`curl http://127.0.0.1:8000/health` |
| HTTPS 正常 | 浏览器打开 `https://jingsen.cc/learningcenter` |
| 词库已导入 | 浏览器打开 `https://jingsen.cc/learningcenter/api/admin/libraries` |
| 数据库有数据 | 宝塔数据库 → PostgreSQL → 进入 `jingsen_db` 查看 `libraries` 表 |

---

## 后续更新代码

每次推送新版本后，在宝塔终端执行：

```bash
cd /www/wwwroot/jingsen/learningcenter
git pull origin main
```

然后在宝塔 Python 项目管理器中点击 **重启** 即可。

> 若 `requirements.txt` 有变化，点「安装模块」或在终端激活虚拟环境后运行 `pip install -r requirements.txt`。

---

## 常见问题

**Q：访问 `/learningcenter` 后页面空白或资源 404**  
A：检查 Nginx 配置中 `rewrite` 是否正确去掉了 `/learningcenter` 前缀。可在宝塔终端执行 `curl http://127.0.0.1:8000/portal` 验证 FastAPI 内部路由是否正常。

**Q：Python 项目管理器找不到 gunicorn**  
A：宝塔创建虚拟环境后，在终端手动激活并安装：  
```bash
source /www/wwwroot/jingsen/learningcenter/venv/bin/activate
pip install -r requirements.txt
```

**Q：数据库连接失败**  
A：宝塔终端运行 `psql -U jingsen -d jingsen_db -h localhost`，确认用户名密码正确；检查 `.env` 文件内容。

**Q：词库没有自动导入**  
A：查看宝塔 Python 项目日志，确认有 `bootstrap` 相关日志；确保 `data/` 目录下有 `.txt` 词库文件。

**Q：宝塔面板访问不了**  
A：确认腾讯云防火墙已开放 8888 端口；也可直接用宝塔的 SSH 终端操作。

# 数学试卷生成模块集成实施计划

## 项目概述
将"试卷分析+生成"功能集成到现有的 Jingsen LearningCenter 系统中，作为数学学科的完整功能模块。

**目标**: 用户上传试卷PDF → 系统分析试卷结构 → 生成同等难度的练习试卷 → 保存到数据库 → 可随时下载PDF

---

## 技术栈确认
- **后端**: FastAPI + Python 3.11+
- **数据库**: PostgreSQL (已有，使用 SQLAlchemy Core)
- **PDF处理**: reportlab (生成) + PyMuPDF (解析)
- **AI服务**: OpenAI API (已有)
- **前端**: 纯 HTML + JavaScript + Tailwind CSS
- **部署**: Render 平台

---

## 数据库设计

### 新增表结构

#### 1. `exam_templates` - 试卷模板表（存储上传的原始试卷）
```sql
CREATE TABLE exam_templates (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,           -- 试卷名称
    file_name VARCHAR(255) NOT NULL,       -- 原始PDF文件名
    file_path VARCHAR(500) NOT NULL,       -- PDF存储路径
    grade VARCHAR(50),                     -- 年级（如：五年级下学期）
    topics JSONB,                          -- 知识点列表（JSON数组）
    difficulty VARCHAR(20),                -- 难度：easy/medium/hard
    question_types JSONB,                  -- 题型分布（JSON对象）
    total_questions INTEGER,               -- 总题数
    has_extension BOOLEAN DEFAULT FALSE,   -- 是否有拓展题
    analysis_result JSONB,                 -- AI分析的完整结果
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

#### 2. `generated_exams` - 生成的试卷表
```sql
CREATE TABLE generated_exams (
    id VARCHAR(64) PRIMARY KEY,
    template_id VARCHAR(64) REFERENCES exam_templates(id),  -- 关联的模板
    name VARCHAR(255) NOT NULL,           -- 生成的试卷名称
    exam_pdf_path VARCHAR(500),            -- 练习卷PDF路径
    answer_pdf_path VARCHAR(500),          -- 答案卷PDF路径
    questions JSONB NOT NULL,              -- 题目内容（JSON数组）
    question_count INTEGER,                -- 题目数量
    difficulty_distribution JSONB,         -- 难度分布设置
    include_answer BOOLEAN DEFAULT TRUE,   -- 是否包含答案
    generation_params JSONB,               -- 生成时的参数
    created_at TIMESTAMP NOT NULL
);
```

#### 3. `math_questions` - 数学题目库表（可选，用于积累题目）
```sql
CREATE TABLE math_questions (
    id VARCHAR(64) PRIMARY KEY,
    question_type VARCHAR(50) NOT NULL,    -- 题型：choice/fill_blank/calculation/word_problem
    grade VARCHAR(50),                     -- 适用年级
    topic VARCHAR(100),                    -- 知识点
    difficulty VARCHAR(20),                -- 难度
    content TEXT NOT NULL,                 -- 题目内容
    options JSONB,                         -- 选项（选择题）
    answer TEXT NOT NULL,                  -- 答案
    analysis TEXT,                         -- 解析
    is_extension BOOLEAN DEFAULT FALSE,    -- 是否拓展题
    source_exam_id VARCHAR(64),            -- 来源试卷
    created_at TIMESTAMP NOT NULL
);
```

---

## 实施步骤

### Phase 1: 后端基础架构 (预计 3-4 小时)

#### 1.1 更新依赖配置
**文件**: `requirements.txt`
**操作**: 添加以下依赖
```
reportlab>=4.0.0
PyMuPDF>=1.23.0
```

#### 1.2 扩展数据模型 (Pydantic Schemas)
**文件**: `models/schemas.py`
**添加内容**:
- `ExamUploadRequest`: 试卷上传请求模型
- `ExamAnalysisResponse`: 试卷分析响应模型
- `ExamGenerateRequest`: 试卷生成请求模型
- `MathQuestion`: 数学题目模型（选择题、填空题、计算题、应用题）
- `ExamPaper`: 完整试卷模型
- `ExamTemplateResponse`: 试卷模板响应
- `GeneratedExamResponse`: 生成试卷响应
- `ExamListResponse`: 试卷列表响应

#### 1.3 创建数据库服务
**新文件**: `services/exam_database_service.py`
**功能**:
- `ExamDatabaseService` 类（参考 `library_admin_service.py` 的实现方式）
- `create_template(data)`: 创建试卷模板记录
- `get_template(template_id)`: 获取模板详情
- `list_templates()`: 列出所有模板
- `create_generated_exam(data)`: 保存生成的试卷
- `get_generated_exam(exam_id)`: 获取生成的试卷
- `list_generated_exams(template_id=None)`: 列出生成的试卷（可按模板筛选）
- `delete_generated_exam(exam_id)`: 删除生成的试卷

**技术要点**:
- 使用 SQLAlchemy Core（与现有代码风格一致）
- 在 `__init__` 中创建表结构
- 使用 `self.engine.begin()` 进行事务操作

#### 1.4 创建试卷生成服务
**新文件**: `services/exam_generator.py`
**功能**:
- `ExamGenerator` 类
- `analyze_exam(pdf_path)`: 分析上传的试卷PDF，提取题型、难度、知识点
- `generate_similar_exam(analysis_result)`: 基于分析结果生成类似试卷
- `generate_pdf(questions, output_path)`: 使用 reportlab 生成PDF试卷
- `generate_answer_key(questions, output_path)`: 生成答案卷

**核心算法**:
1. **试卷分析**: 使用 PyMuPDF 提取PDF文本，用 OpenAI API 分析试卷结构
2. **题目生成**: 基于分析结果，用 OpenAI API 生成对应类型和难度的题目
3. **PDF渲染**: 使用 reportlab 创建格式化的试卷（参考 create_math_pdf.py）

#### 1.5 扩展数学API路由
**文件**: `api/math.py`
**添加路由**:
- `POST /api/math/exam/upload`: 上传试卷文件，保存到数据库
- `GET /api/math/exam/templates`: 获取所有试卷模板列表
- `GET /api/math/exam/templates/{template_id}`: 获取模板详情
- `POST /api/math/exam/templates/{template_id}/generate`: 基于模板生成新试卷
- `GET /api/math/exam/generated`: 获取所有生成的试卷列表
- `GET /api/math/exam/generated/{exam_id}`: 获取生成的试卷详情
- `GET /api/math/exam/download/{exam_id}/{type}`: 下载试卷（type: exam/answer）
- `DELETE /api/math/exam/generated/{exam_id}`: 删除生成的试卷

#### 1.6 扩展数学服务
**文件**: `services/math_service.py`
**添加方法**:
- `upload_exam(file)`: 处理上传的试卷文件，保存到数据库
- `analyze_exam(file_path)`: 调用 ExamGenerator 分析试卷
- `generate_exam(template_id, params)`: 调用 ExamGenerator 生成试卷并保存到数据库
- `get_exam_history()`: 从数据库获取生成历史
- `get_exam_download_url(exam_id, type)`: 获取试卷下载链接

---

### Phase 2: 前端页面开发 (预计 3-4 小时)

#### 2.1 创建数学学科页面
**新文件**: `static/math.html`
**页面结构**:
- 顶部导航栏（与 english.html / chinese.html 风格一致）
- 功能标签页:
  - **试卷生成器** (主要功能)
  - **历史试卷** (查看所有生成的试卷)
  - **基础练习** (预留)

**试卷生成器界面**:
```
┌─────────────────────────────────────────┐
│  📤 上传原试卷                           │
│  [点击或拖拽上传PDF文件]                  │
│                                         │
│  📋 试卷分析结果                         │
│  ├─ 年级: 五年级下学期                    │
│  ├─ 题型: 选择/填空/计算/应用            │
│  ├─ 难度: 中等                           │
│  └─ 知识点: 分数运算、小数...            │
│                                         │
│  ⚙️ 生成选项                             │
│  ├─ 题目数量: [保持原卷/自定义]          │
│  ├─ 难度调整: [简单20%/中等60%/困难20%]  │
│  └─ 包含答案: [是/否]                    │
│                                         │
│  [🚀 生成试卷]                           │
│                                         │
│  ✅ 生成成功！已保存到历史记录            │
└─────────────────────────────────────────┘
```

**历史试卷界面**:
```
┌─────────────────────────────────────────┐
│  📚 历史生成的试卷                       │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 数学双周练习卷 - 2024-03-15     │   │
│  │ 基于: 五年级下学期试卷          │   │
│  │ 题目: 29题 | 难度: 中等         │   │
│  │ [下载练习卷] [下载答案] [删除]  │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 数学双周练习卷 - 2024-03-10     │   │
│  │ ...                             │   │
│  └─────────────────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

**样式要求**:
- 使用 Tailwind CSS (CDN)
- 配色: 数学主题色 `#3B82F6` (蓝色)
- 与现有 english.html / chinese.html 风格保持一致

#### 2.2 更新门户页面
**文件**: `static/portal.html`
**修改内容**:
- 修改 `selectSubject('math')` 函数，跳转到 `/math` 而不是 alert

#### 2.3 更新主应用入口
**文件**: `main.py`
**添加内容**:
- 注册 `/math` 路由，返回 `static/math.html`

---

### Phase 3: 核心功能实现 (预计 4-5 小时)

#### 3.1 PDF试卷生成器
**参考**: 当前工作目录下的 `create_math_pdf.py`
**整合到**: `services/exam_generator.py`

**试卷格式** (与原卷保持一致):
- A4 纸张
- 标题: "数学双周练习卷"
- 四大部分:
  - I. 选择题 (9题，含标记题▲)
  - II. 填空题 (10题，含2道拓展题)
  - III. 计算题 (6题)
  - IV. 应用题 (4题，含1道拓展题)
- 答题框和留空
- 页眉页脚

#### 3.2 试卷分析器
**实现方式**:
1. 使用 PyMuPDF 提取PDF文本内容
2. 使用 OpenAI API 分析:
   ```
   请分析这份数学试卷的结构，返回JSON格式:
   {
     "grade": "五年级下学期",
     "topics": ["分数运算", "小数转换", ...],
     "difficulty": "medium",
     "question_types": {
       "choice": 9,
       "fill_blank": 10,
       "calculation": 6,
       "word_problem": 4
     },
     "has_extension_questions": true
   }
   ```

#### 3.3 题目生成器
**实现方式**:
使用 OpenAI API 生成对应类型的数学题目:
```
请生成{数量}道{题型}的{年级}数学题，难度{难度}，知识点:{知识点列表}
要求:
1. 题目符合教学大纲
2. 计算过程清晰
3. 答案准确
4. 返回JSON格式
```

---

### Phase 4: 数据持久化实现 (预计 2-3 小时)

#### 4.1 数据库服务实现
**文件**: `services/exam_database_service.py`
**参考实现**:
```python
class ExamDatabaseService:
    def __init__(self):
        database_url = config.database_url_for_sqlalchemy()
        self.engine = create_engine(database_url, future=True, pool_pre_ping=True)
        self.metadata = MetaData()
        
        # 定义表结构
        self.exam_templates = Table(...)
        self.generated_exams = Table(...)
        
        # 创建表
        self.metadata.create_all(self.engine)
```

**核心方法**:
- `save_template(name, file_path, analysis_result)`: 保存上传的试卷模板
- `get_template(template_id)`: 获取模板详情（包含分析结果）
- `list_templates()`: 列出所有模板（用于下拉选择）
- `save_generated_exam(template_id, questions, exam_pdf, answer_pdf)`: 保存生成的试卷
- `list_generated_exams()`: 列出生成的试卷历史
- `get_generated_exam(exam_id)`: 获取生成的试卷详情（包含下载路径）
- `delete_generated_exam(exam_id)`: 删除记录和文件

#### 4.2 文件存储管理
**策略**:
- 上传的原始PDF: `data/exam_templates/{template_id}/original.pdf`
- 生成的练习卷: `data/generated_exams/{exam_id}/exam.pdf`
- 生成的答案卷: `data/generated_exams/{exam_id}/answer.pdf`

**清理策略**:
- 删除生成的试卷时，同时删除PDF文件
- 可添加定时任务清理过期文件（可选）

### Phase 5: 测试与优化 (预计 2 小时)

#### 5.1 本地测试
- 启动服务: `python3 main.py`
- 访问: `http://localhost:8000/portal`
- 测试完整流程:
  1. 点击 Math 进入数学页面
  2. 上传测试试卷PDF
  3. 查看分析结果并保存到数据库
  4. 生成新试卷并保存到数据库
  5. 在历史记录页面查看所有生成的试卷
  6. 下载练习卷和答案卷
  7. 删除历史记录

#### 5.2 数据库验证
- 使用 psql 或 pgAdmin 查看数据是否正确存储
- 验证表关系: templates ↔ generated_exams

#### 5.3 部署测试
- 提交代码到 Git
- Render 自动部署
- 线上环境测试（PostgreSQL 数据持久化）

---

## 文件变更清单

### 修改文件
1. `requirements.txt` - 添加依赖 (reportlab, PyMuPDF)
2. `models/schemas.py` - 添加试卷相关数据模型
3. `api/math.py` - 扩展API路由（上传、分析、生成、历史记录）
4. `services/math_service.py` - 扩展服务方法
5. `static/portal.html` - 启用数学入口
6. `main.py` - 注册数学页面路由

### 新建文件
1. `services/exam_database_service.py` - 数据库服务（核心新增）
2. `services/exam_generator.py` - 试卷生成核心服务
3. `static/math.html` - 数学学科前端页面（含历史记录功能）
4. `math_todo.md` - 本实施计划

### 数据库变更
- 新增 `exam_templates` 表：存储上传的原始试卷
- 新增 `generated_exams` 表：存储生成的试卷记录
- 可选 `math_questions` 表：积累题目库

---

## 实施建议

### 推荐执行顺序
1. **Phase 1.1 → 1.2**: 先更新依赖和模型
2. **Phase 1.3**: 实现数据库服务（exam_database_service.py）
3. **Phase 3.1**: 实现PDF生成器（可独立测试）
4. **Phase 1.4 → 1.5 → 1.6**: 完成后端API和服务
5. **Phase 2**: 开发前端页面（含历史记录功能）
6. **Phase 3.2 → 3.3**: 实现AI分析生成
7. **Phase 4**: 完善数据持久化逻辑
8. **Phase 5**: 测试优化

### 关键代码参考
- PDF生成逻辑可参考: `/Users/JasonChan/WorkBuddy/20260313090808/create_math_pdf.py`
- 前端样式可参考: `static/english.html` 或 `static/chinese.html`
- API设计可参考: `api/english.py`

### 注意事项
1. **文件上传**: 使用 FastAPI 的 `UploadFile`，注意设置文件大小限制（建议最大 10MB）
2. **文件存储**: 
   - 上传的PDF和生成的PDF保存到 `data/exam_templates/` 和 `data/generated_exams/`
   - 数据库只存储文件路径，不存储文件内容
   - 删除记录时同步删除物理文件
3. **AI调用**: 分析试卷和生成题目都需要调用 OpenAI API，注意错误处理和重试机制
4. **PDF格式**: 确保生成的PDF与原卷格式一致，便于打印使用
5. **数据库事务**: 使用 SQLAlchemy Core 的事务管理，确保数据一致性
6. **数据清理**: 可定期清理过期的生成试卷（如 30 天前的），保留模板

---

## 预期成果

完成后，用户可以通过 LearningCenter 网站:
1. 进入数学学科页面
2. 上传任意数学试卷PDF，系统自动保存到数据库
3. 系统自动分析试卷结构和难度
4. 一键生成同等难度的练习试卷，保存到数据库
5. 在"历史试卷"页面查看所有生成的试卷
6. 随时下载PDF格式的练习卷和答案卷
7. 删除不需要的历史记录

**数据持久化效果**:
- 上传的试卷模板永久保存，可重复使用
- 生成的试卷记录永久保存，可随时下载
- 刷新页面或重新登录后，历史记录依然存在
- Render 重新部署后，数据不丢失

---

## 后续扩展建议

1. **题目库**: 建立数学题目库，支持从题库选题组卷
2. **错题分析**: 分析学生错题，针对性生成练习
3. **多年级支持**: 扩展支持更多年级（目前先实现五年级）
4. **试卷分享**: 支持将生成的试卷分享给其他用户
5. **批量生成**: 一次生成多份不同难度的试卷
6. **定时任务**: 定期清理过期文件，释放存储空间

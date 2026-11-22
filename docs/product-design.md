# AI 求职助手 — 完整产品设计文档

---

## 一、产品概述

### 1.1 产品定位

**AI JobFun** 是一站式 AI 求职助手，面向技术求职者。核心价值主张是：**用 AI 安全地优化简历，而非编造简历**。用户上传 LaTeX 简历和 JD，系统分析匹配度、给出可操作的修改建议、用户确认后自动修改 LaTeX 源码并生成 PDF。

### 1.2 目标用户画像

| 维度 | 描述 |
|------|------|
| 人群 | 技术岗位求职者（SDE、MLE、DS 等） |
| 技能 | 使用 LaTeX/Overleaf 维护简历 |
| 痛点 | 海投时代，每份简历需要针对 JD 微调，手工改 LaTeX 效率低 |
| 需求 | 快速匹配评估 → AI 建议 → 一键修改 → 生成 PDF |

### 1.3 核心差异化

> ⚠️ **安全边界是第一原则**：AI 只能优化表达，不能编造经历。

| 竞品 | 我们的差异 |
|------|-----------|
| 通用简历优化工具 | 专为 LaTeX/Overleaf 设计，保留模板格式 |
| ChatGPT 通用对话 | 结构化匹配评分 + 可追溯的修改历史 |
| 一键生成简历 | 不允许编造内容，用户确认后才修改 |

---

## 二、功能模块详细设计

### 2.1 模块一：JD 匹配评分引擎

**JD 输入方式（三种，均为一等公民）**：

| 方式 | 入口 | 处理 | 适用场景 |
|------|------|------|---------|
| 📝 **文本粘贴** | 文本框直接粘贴 | Claude API 结构化提取 | 从网页复制 JD |
| 🖼️ **图片上传** | 拖拽/选择图片文件 | Claude Vision API → OCR + 结构化提取（一步完成） | 截图、拍照 |
| 📄 **PDF 上传** | 拖拽/选择 PDF 文件 | PyPDF2 提取文字 → Claude API 结构化提取 | 下载的 JD 文件 |

**处理流程**：

```
JD 文本 ─────────────────────┐
                              ├──→ Claude API 结构化提取 ──→ JD 结构化对象
JD 图片 ──→ Claude Vision ──→┤                                      ↓
                              │      简历结构化对象 ──→ 匹配计算 ──→ 评分报告
JD PDF  ──→ PyPDF2 提取 ────┘

简历 LaTeX ──→ LaTeX Parser ──→ 简历结构化对象
```

**JD 结构化对象 Schema**（所有输入方式归一化到此统一结构）：

```json
{
  "company": "Google",
  "position": "Senior Software Engineer",
  "team": "Cloud Infrastructure",
  "location": "Mountain View, CA",
  "required_skills": ["Python", "Kubernetes", "Terraform", ...],
  "preferred_skills": ["gRPC", "Service Mesh", ...],
  "years_experience": 5,
  "education": "BS in CS or equivalent",
  "responsibilities": ["Design distributed systems", ...],
  "soft_skills": ["cross-team collaboration", ...],
  "culture_signals": ["move fast", "customer focus", ...],
  "level": "Senior",
  "source_type": "text|image|pdf"
}
```

**输出**（六维度评分卡）：

| 维度 | 权重 | 说明 |
|------|------|------|
| 总匹配度 | — | 加权综合评分（0-100） |
| 技能匹配度 | 35% | 硬技能关键词命中率 |
| 经验匹配度 | 30% | 项目/工作经验的领域相关性 |
| 学历匹配度 | 10% | 学历层次 + 专业相关性 |
| 软技能匹配度 | 10% | 沟通/领导力/团队协作 |
| 文化匹配度 | 15% | 从 JD 措辞推断文化偏好 |

**额外输出**：

- ✅ 已匹配技能清单
- ❌ 缺失技能清单（诚实标注）
- ⚠️ 风险点（年限不足、领域偏差、技能缺口等）
- 📊 匹配雷达图数据

---

### 2.2 模块二：简历修改建议引擎

**核心原则**（铁律）：
1. ❌ 不编造经历
2. ❌ 不添加不存在的项目
3. ❌ 不修改公司名、职位名、时间
4. ✅ 仅优化措辞、亮点排序、关键词突出

**建议类型**：

| 类别 | 示例 |
|------|------|
| 🔑 关键词注入 | "你的经历中有 Kafka 但简历未体现，JD 要求消息队列经验" |
| 📐 结构调整 | "将实习中的分布式项目提前到项目列表第一位" |
| ✨ 表达优化 | "将 'Used Python' 优化为 'Built data pipeline with Python processing 500K records/day'" |
| 🎯 亮点突出 | "JD 强调系统设计，建议扩展这段架构描述" |
| 📉 内容弱化 | "JD 是后端岗位，前端 React 项目可缩减为一句话" |
| 📏 量化增强 | "这段经历缺少量化结果，建议补充（但需要你提供数据）" |

**交互流程**：

```
匹配报告 ──→ AI 生成建议列表 ──→ 用户勾选采纳的建议 ──→ AI 执行修改
                ↑                                              ↓
          用户可以要求                        修改后的 LaTeX 源码 ←──
          "再来一批建议"                       保留原模板格式
```

---

### 2.3 模块三：LaTeX 简历修改执行器

**技术难点**：LaTeX 是结构化标记语言，不能当纯文本随便替换 — 需要理解 `\section`、`\begin`/`\end`、宏展开等结构。

**处理策略**：

```
LaTeX 文件树                     抽象语法树 (AST)
─────────────                    ────────────────
main.tex                         Document
├── resume.cls                   ├── Preamble
├── sections/                    │   ├── \documentclass
│   ├── education.tex            │   ├── \usepackage{...}
│   ├── experience.tex           │   └── \newcommand{...}
│   ├── projects.tex             ├── Section: Education
│   └── skills.tex               │   └── Entry[]
└──                             ├── Section: Experience
                                │   └── Entry[]
                                ├── Section: Projects
                                │   └── Entry[]
                                └── Section: Skills
                                    └── Entry[]
```

**修改安全措施**：

| 措施 | 说明 |
|------|------|
| Git 备份 | 每次修改前自动 Git commit |
| LaTeX 编译校验 | 修改后自动编译，失败则回滚 |
| Diff 展示 | 修改前后对比，高亮变更 |
| 回滚能力 | 一键恢复到任意历史版本 |
| 格式保护 | Parser 识别 cls/macro 结构，只修改内容区 |

---

### 2.4 模块四：面试准备生成器

**基于 JD + 简历的交叉分析生成面试题**：

| 题目类别 | 生成逻辑 | 示例 |
|---------|---------|------|
| 🔧 技术基础 | JD 技术栈 → 高频考点 | "JD 要求 Python，请解释 GIL 机制" |
| 📂 项目追问 | 简历项目 → 深度追问 | "你在 XX 项目中用了 Redis，为什么选择 Redis 而非 Memcached？" |
| 🏢 行为面试 | JD 软技能 → STAR 问题 | "JD 要求跨团队协作，请举一个你推动跨团队项目的例子" |
| 🇬🇧 英文面试 | 自动翻译 + 英文场景 | "Tell me about a time you resolved a technical conflict" |
| 🧠 系统设计 | JD 级别 → 设计题 | "JD 是 Senior，请设计一个 URL 短链接服务" |

---

### 2.5 模块五：求职进度管理

**看板式管理**，每个申请是一条记录：

```
┌─────────────────────────────────────────────────────────┐
│  状态流转：已收藏 → 已投递 → 笔试中 → 面试中 → Offer → 已拒绝 │
│                         ↓                                │
│              每阶段可记录笔记、附件、时间戳                │
└─────────────────────────────────────────────────────────┘
```

---

## 三、系统架构设计

### 3.1 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                        前端层 (Streamlit)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ JD 上传  │ │ 匹配报告 │ │ 修改建议 │ │ Diff 确认│ │ 看板   │ │
│  │ & 解析   │ │ & 雷达图 │ │ & 勾选   │ │ & 编译   │ │ 管理   │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────┴───────────────────────────────────┐
│                         服务层 (Python)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │JD Parser │ │LaTeX     │ │Match     │ │Resume    │ │Interview│ │
│  │Service   │ │Parser    │ │Engine    │ │Modifier  │ │Generator│ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
│  ┌──────────┐ ┌──────────┐                                      │
│  │PDF       │ │Progress  │                                      │
│  │Compiler  │ │Manager   │                                      │
│  └──────────┘ └──────────┘                                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────┴───────────────────────────────────┐
│                          AI 层                                    │
│              Claude API (通过 Anthropic SDK)                      │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐                    │
│     │Prompt    │  │Thinking  │  │Tool Use  │                    │
│     │Templates │  │(推理链)   │  │(结构化输出)│                   │
│     └──────────┘  └──────────┘  └──────────┘                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────┴───────────────────────────────────┐
│                         数据层                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│  │ SQLite   │  │ ChromaDB │  │ 文件系统  │                       │
│  │(结构化)  │  │(向量检索)│  │(LaTeX/PDF)│                      │
│  └──────────┘  └──────────┘  └──────────┘                       │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 技术选型理由

| 技术 | 用途 | 选型理由 |
|------|------|---------|
| **Python** | 后端主语言 | 生态丰富，LaTeX/PDF 工具链成熟 |
| **Streamlit** | Web UI | 极简部署，适合个人项目展示；Python 原生 |
| **Claude API** | AI 引擎 | Opus 推理能力强，适合复杂匹配分析；Thinking 模式用于深度推理 |
| **ChromaDB** | 向量数据库 | 轻量嵌入式，存储 JD/简历 embedding，支持相似度搜索 |
| **SQLite** | 关系数据库 | 零配置，单文件，足够个人项目使用 |
| **PyLaTeX / tex2py** | LaTeX 解析 | 结构化解析 LaTeX 源码 |
| **pdflatex / xelatex** | PDF 编译 | 系统调用编译 LaTeX |
| **Git (GitPython)** | 版本控制 | LaTeX 修改的版本管理与回滚 |

---

## 四、数据流设计

### 4.1 核心数据流

```
用户上传简历 (LaTeX 文件包)
       │
       ▼
┌─────────────────┐
│  1. LaTeX Parser │ ──→ 解析为结构化 JSON ──→ 存入 SQLite
└─────────────────┘
       │
       ▼
用户输入 JD (文本粘贴 / 图片上传 / PDF上传)
       │
       ├── 图片 ──→ Claude Vision API (OCR + 结构化提取)
       ├── PDF  ──→ PyPDF2 提取文字 ──→ Claude API 结构化提取
       └── 文本 ──→ Claude API 结构化提取
       │
       ▼
┌─────────────────┐
│  2. JD Parser    │ ──→ 归一化 JD 结构化 JSON ──→ 存入 SQLite + ChromaDB
└─────────────────┘
       │
       ▼
┌─────────────────┐
│  3. Match Engine │ ──→ Claude API 多维匹配分析 ──→ 评分报告
└─────────────────┘
       │
       ▼
┌─────────────────┐
│  4. Suggestion   │ ──→ Claude API 生成修改建议 ──→ 展示给用户
│     Generator    │
└─────────────────┘
       │
       ▼ (用户勾选采纳的建议)
┌─────────────────┐
│  5. LaTeX        │ ──→ Claude API 执行修改 ──→ 新 LaTeX 源码
│     Modifier     │       Git commit 备份
└─────────────────┘
       │
       ▼
┌─────────────────┐
│  6. PDF Compiler │ ──→ 调用 pdflatex ──→ PDF 文件 ──→ 用户下载
└─────────────────┘
       │
       ▼
┌─────────────────┐
│  7. Interview    │ ──→ Claude API 交叉分析 JD+简历 ──→ 面试题库
│     Generator    │
└─────────────────┘
```

### 4.2 数据流中的安全护栏

```
用户确认前 ──╳── 决不写文件
              │
修改前 ────── Git commit (自动备份)
              │
修改后 ────── pdflatex 编译检查
              │
编译失败 ──── Git revert + 报错展示
              │
编译成功 ──── Diff 展示 + 下载按钮
```

---

## 五、数据库设计

### 5.1 SQLite 表结构

```
┌─────────────────────────────────────────────────────────────┐
│                        users                                 │
├─────────────────────────────────────────────────────────────┤
│ id            INTEGER PK AUTOINCREMENT                       │
│ username      TEXT                                          │
│ created_at    DATETIME DEFAULT CURRENT_TIMESTAMP            │
│ settings_json TEXT  (JSON blob for user preferences)        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      resumes                                 │
├─────────────────────────────────────────────────────────────┤
│ id            INTEGER PK AUTOINCREMENT                       │
│ user_id       INTEGER FK → users.id                         │
│ name          TEXT       (e.g. "Backend SDE 2026")          │
│ base_version  INTEGER   (0 = original)                      │
│ parent_id     INTEGER FK → resumes.id (version chain)       │
│ latex_path    TEXT      (directory path on disk)            │
│ pdf_path      TEXT      (compiled PDF path)                 │
│ structured_json TEXT    (parsed resume structure)           │
│ created_at    DATETIME                                       │
│ is_active     BOOLEAN DEFAULT 1                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    job_descriptions                          │
├─────────────────────────────────────────────────────────────┤
│ id            INTEGER PK AUTOINCREMENT                       │
│ user_id       INTEGER FK → users.id                         │
│ company       TEXT                                          │
│ position      TEXT                                          │
│ raw_text      TEXT       (original JD text)                 │
│ source_type   TEXT       (text/image/pdf)                   │
│ source_file   TEXT       (uploaded file path, nullable)     │
│ structured_json TEXT     (Claude-extracted structure)       │
│ source_url    TEXT       (optional)                         │
│ created_at    DATETIME                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    match_results                             │
├─────────────────────────────────────────────────────────────┤
│ id            INTEGER PK AUTOINCREMENT                       │
│ resume_id     INTEGER FK → resumes.id                       │
│ jd_id         INTEGER FK → job_descriptions.id              │
│ total_score   REAL       (0-100)                            │
│ skill_score   REAL                                          │
│ experience_score REAL                                       │
│ education_score REAL                                        │
│ soft_skill_score REAL                                       │
│ culture_score REAL                                          │
│ matched_skills_json TEXT                                    │
│ missing_skills_json TEXT                                    │
│ risks_json    TEXT                                          │
│ raw_report    TEXT       (full Claude output)               │
│ created_at    DATETIME                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    suggestions                               │
├─────────────────────────────────────────────────────────────┤
│ id            INTEGER PK AUTOINCREMENT                       │
│ match_id      INTEGER FK → match_results.id                 │
│ category      TEXT       (keyword/structure/wording/...)    │
│ priority      INTEGER    (1=highest)                        │
│ original_text TEXT      (当前简历原文)                       │
│ suggested_text TEXT     (建议修改后文本)                     │
│ rationale     TEXT      (修改理由)                           │
│ status        TEXT      (pending/accepted/rejected/modified) │
│ created_at    DATETIME                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    applications                              │
├─────────────────────────────────────────────────────────────┤
│ id            INTEGER PK AUTOINCREMENT                       │
│ user_id       INTEGER FK → users.id                         │
│ jd_id         INTEGER FK → job_descriptions.id              │
│ resume_id     INTEGER FK → resumes.id (applied version)     │
│ match_id      INTEGER FK → match_results.id                 │
│ status        TEXT    (saved/applied/oa/interview/offer/    │
│                        rejected/withdrawn)                   │
│ applied_date  DATE                                          │
│ notes         TEXT                                          │
│ next_step     TEXT                                          │
│ updated_at    DATETIME                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    interview_questions                       │
├─────────────────────────────────────────────────────────────┤
│ id            INTEGER PK AUTOINCREMENT                       │
│ match_id      INTEGER FK → match_results.id                 │
│ category      TEXT    (technical/project/behavioral/english/ │
│                        system_design)                        │
│ question      TEXT                                          │
│ suggested_answer TEXT (AI-generated reference)              │
│ difficulty     TEXT    (easy/medium/hard)                   │
│ created_at    DATETIME                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    latex_changes                             │
├─────────────────────────────────────────────────────────────┤
│ id            INTEGER PK AUTOINCREMENT                       │
│ resume_id     INTEGER FK → resumes.id                       │
│ suggestion_id INTEGER FK → suggestions.id                   │
│ file_path     TEXT      (which .tex file was changed)       │
│ old_content   TEXT                                          │
│ new_content   TEXT                                          │
│ commit_hash   TEXT      (git commit)                        │
│ created_at    DATETIME                                       │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 ChromaDB Collection 设计

| Collection Name | 用途 | Embedding 内容 |
|----------------|------|---------------|
| `jds` | JD 向量库 | JD 结构化摘要 + 技能关键词 |
| `resumes` | 简历向量库 | 简历项目/技能描述 |
| `suggestions` | 历史建议缓存 | 修改建议文本（相似 JD 复用建议） |

---

## 六、项目目录结构

```
jobfun/
├── README.md                     # 项目介绍 + 使用指南
├── requirements.txt              # Python 依赖
├── .env.example                  # 环境变量模板
├── .gitignore
│
├── app.py                        # Streamlit 主入口
├── config.py                     # 全局配置
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/                     # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── jd_parser.py          # JD 解析服务
│   │   ├── latex_parser.py       # LaTeX 结构化解析
│   │   ├── match_engine.py       # 匹配评分引擎
│   │   ├── suggestion_engine.py  # 修改建议生成
│   │   ├── latex_modifier.py     # LaTeX 修改执行器
│   │   ├── pdf_compiler.py       # PDF 编译服务
│   │   ├── interview_generator.py # 面试题生成
│   │   └── progress_manager.py   # 求职进度管理
│   │
│   ├── ai/                       # AI 调用层
│   │   ├── __init__.py
│   │   ├── client.py             # Claude API 客户端封装
│   │   ├── prompts/              # Prompt 模板
│   │   │   ├── __init__.py
│   │   │   ├── jd_extraction.py
│   │   │   ├── match_scoring.py
│   │   │   ├── suggestions.py
│   │   │   ├── latex_edit.py
│   │   │   └── interview.py
│   │   └── token_tracker.py      # Token 用量统计
│   │
│   ├── db/                       # 数据库层
│   │   ├── __init__.py
│   │   ├── sqlite_client.py      # SQLite CRUD
│   │   ├── chroma_client.py      # ChromaDB 向量操作
│   │   └── models.py             # 数据模型定义
│   │
│   ├── latex/                    # LaTeX 工具
│   │   ├── __init__.py
│   │   ├── parser.py             # LaTeX → AST
│   │   ├── modifier.py           # AST → 修改后 LaTeX
│   │   ├── compiler.py           # pdflatex 编译
│   │   └── validator.py          # 编译后校验
│   │
│   └── utils/                    # 通用工具
│       ├── __init__.py
│       ├── file_utils.py         # 文件上传/解压
│       ├── diff_utils.py         # Diff 生成
│       ├── git_utils.py          # Git 操作封装
│       └── logger.py             # 日志
│
├── ui/                           # Streamlit 页面
│   ├── __init__.py
│   ├── home.py                   # 首页仪表盘
│   ├── upload.py                 # 简历/JD 上传页
│   ├── match.py                  # 匹配评分展示页
│   ├── suggestions.py            # 修改建议 + 确认页
│   ├── resume_editor.py          # Diff 查看 + 修改确认页
│   ├── interview_prep.py         # 面试准备页
│   └── tracker.py                # 求职进度看板页
│
├── data/                         # 运行时数据 (gitignored)
│   ├── sqlite/
│   │   └── jobfun.db
│   ├── chroma/
│   │   └── ...
│   ├── uploads/                  # 用户上传的原始文件
│   ├── resumes/                  # 简历工作目录
│   │   └── {resume_id}/
│   │       ├── main.tex
│   │       ├── resume.cls
│   │       ├── sections/
│   │       └── .git/             # 简历版本控制
│   └── outputs/                  # 生成的 PDF
│
├── tests/                        # 测试
│   ├── __init__.py
│   ├── test_jd_parser.py
│   ├── test_latex_parser.py
│   ├── test_match_engine.py
│   ├── test_suggestion_engine.py
│   ├── test_latex_modifier.py
│   └── fixtures/                 # 测试用 LaTeX 文件
│       ├── sample_resume/
│       └── sample_jds/
│
└── docs/                         # 文档
    ├── architecture.md
    ├── api_design.md
    └── user_guide.md
```

---

## 七、MVP 功能范围

### MVP v0.1 — 核心闭环（2-3 周）

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P0 | 简历上传（LaTeX zip） | 支持 main.tex + cls + sections 结构 |
| P0 | JD 输入（文本粘贴） | 文本框输入 |
| P0 | JD 输入（图片上传） | 支持截图/拍照，Claude Vision 一步 OCR+提取 |
| P0 | 匹配评分 | 六维度评分 + 缺失技能 + 风险点 |
| P0 | 修改建议生成 | AI 生成建议列表，用户可逐条查看 |
| P0 | 用户确认修改 | 勾选采纳的建议 |
| P0 | LaTeX 自动修改 | 只修改内容文字，保留模板 |
| P0 | PDF 生成 | 编译 LaTeX → PDF 下载 |
| P0 | Git 版本备份 | 每次修改前自动 commit |

**MVP v0.1 不包含**：
- 用户注册/登录（单用户本地运行）
- 求职进度管理
- 面试题生成
- ChromaDB 向量检索
- Overleaf API 集成
- JD PDF 文件上传（P2）
- URL 抓取（P2）

### MVP v0.2 — 体验增强（+1 周）

| 优先级 | 功能 |
|--------|------|
| P1 | Diff 对比展示（修改前后） |
| P1 | 修改回滚 |
| P1 | 匹配雷达图可视化 |
| P1 | 面试题生成（基础版） |
| P1 | 求职进度看板（简单 CRUD） |

### MVP v0.3 — 智能化（+1 周）

| 优先级 | 功能 |
|--------|------|
| P2 | ChromaDB 向量检索（相似 JD 复用建议） |
| P2 | 多简历版本管理 |
| P2 | JD PDF 文件上传（PyPDF2 提取文字） |
| P2 | 英文面试题生成 |
| P2 | Token 用量统计与费用预估 |

---

## 八、后续扩展路线

### Phase 1：数据分析与洞察（v1.0）

- 📊 求职趋势 Dashboard（投递/面试/Offer 转化漏斗）
- 📈 技能差距分析（跨多个 JD 聚合）
- 🎯 岗位推荐（基于历史匹配数据）

### Phase 2：自动化集成（v1.5）

- 🔗 Overleaf API 集成（直接 push 修改到 Overleaf）
- 📧 邮件提醒（面试时间、跟进提醒）
- 🤖 LinkedIn/猎聘 JD 自动抓取
- 📝 自动生成 Cover Letter

### Phase 3：协作与社交（v2.0）

- 👥 多用户支持（求职小组共享面经）
- 💬 面试反馈记录与复盘
- 🏆 面试通过率统计
- 📤 简历版本 A/B 测试

### Phase 4：深度 AI（v2.5）

- 🎭 模拟面试（AI 面试官实时对话）
- 🗣 语音面试练习
- 🧠 个性化学习路径推荐
- 📋 自动填申请表（Workday/Greenhouse 等）

---

## 九、关键技术决策

### 9.1 LaTeX 解析策略

不构建完整的 LaTeX 编译器，而是采用 **启发式段落级解析**：

```
方案：基于 section 命令 + 环境边界 的结构提取
输入：LaTeX 源码文本
输出：
{
  "preamble": {...},
  "sections": [
    {
      "title": "Experience",
      "entries": [
        {
          "header": "Software Engineer @ Google, 2023-Present",
          "bullets": ["bullet 1", "bullet 2", ...]
        }
      ]
    }
  ]
}
```

这样 Claude 可以在 entry/bullet 粒度上做修改，而非整个文件。

### 9.2 Claude API 使用策略

| 场景 | 模型选择 | 特殊配置 |
|------|---------|---------|
| JD 结构化提取（文本） | Haiku（快速、便宜） | Tool Use：强制 JSON Schema 输出 |
| JD 结构化提取（图片） | Sonnet（Vision 能力） | 图片 + Tool Use 一步完成 OCR+提取 |
| 匹配评分 | Opus（深度推理） | Thinking 模式 |
| 修改建议生成 | Sonnet（平衡） | 多轮对话式 |
| LaTeX 修改执行 | Opus（需精确理解 LaTeX） | System Prompt 强化 |
| 面试题生成 | Sonnet | — |
| 简单问答 | Haiku | Prompt Caching 启用 |

### 9.3 安全设计

```
┌─────────────────────────────────────────┐
│            安全约束层                     │
│                                          │
│  1. Prompt 层：System Prompt 硬约束       │
│     "你只能修改措辞，不能编造经历"         │
│                                          │
│  2. 校验层：修改前后结构对比               │
│     - 公司名不允许变化                     │
│     - 时间不允许变化                       │
│     - 项目数量不允许增减                   │
│                                          │
│  3. 编译层：LaTeX 编译通过才算成功          │
│     - 编译失败 → 自动回滚                  │
│                                          │
│  4. 版本层：Git 记录所有修改               │
│     - 每次修改一个 commit                 │
│     - 可精确回滚到任意版本                  │
└─────────────────────────────────────────┘
```

---

## 十、UI 页面流设计（Wireframe）

### 页面 1：仪表盘

```
┌──────────────────────────────────────────────────────┐
│  🤖 JobFun - AI 求职助手                              │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ 3 份简历    │  │ 12 条 JD    │  │ 5 个面试    │  │
│  │ 最新: v3   │  │ 待匹配: 3  │  │ 本周: 2     │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                      │
│  最近活动:                                           │
│  📝 Google SDE 匹配度 78% — 2 小时前                 │
│  📝 Meta MLE 匹配度 65% — 昨天                       │
│  ...                                                 │
└──────────────────────────────────────────────────────┘
```

### 页面 2：JD 匹配

```
┌──────────────────────────────────────────────────────┐
│  步骤 1：选择简历    [我的简历 v3 ▾]                  │
│  步骤 2：输入 JD
│
│  ┌─ 输入方式 ───────────────────────┐
│  │ [📝 文本] [🖼️ 图片] [📄 PDF]    │  ← Tab 切换
│  ├──────────────────────────────────┤
│  │                                  │
│  │  (根据选择展示文本框 或 文件上传)   │
│  │                                  │
│  └──────────────────────────────────┘
│                                                      │
│  [🔍 开始匹配分析]                                    │
│                                                      │
│  ─────────────── 匹配结果 ───────────────             │
│                                                      │
│  总匹配度：78%  ████████████░░░░░░                    │
│                                                      │
│  技能匹配度    85%  ████████████████░░               │
│  经验匹配度    72%  ██████████████░░░░               │
│  学历匹配度    90%  ██████████████████░              │
│  软技能匹配度  65%  █████████████░░░░░               │
│  文化匹配度    70%  ██████████████░░░░               │
│                                                      │
│  ✅ 已匹配：Python, AWS, Docker, Kubernetes...       │
│  ❌ 缺失：Terraform, gRPC                            │
│  ⚠️ 风险：JD 要求 5 年经验，你当前 3 年              │
│                                                      │
│  [📝 查看修改建议]  [🎯 生成面试题]                   │
└──────────────────────────────────────────────────────┘
```

### 页面 3：修改建议

```
┌──────────────────────────────────────────────────────┐
│  修改建议 (共 12 条)                                  │
│                                                      │
│  ☑ 🔑 关键词：将 "Message Queue" 改为 "Apache Kafka" │
│    理由：JD 明确要求 Kafka 经验                       │
│                                                      │
│  ☑ 📐 结构调整：将分布式系统项目移到第一位            │
│    理由：JD 强调分布式系统经验                        │
│                                                      │
│  ☐ ✨ 表达优化：将 "Used Python for data processing"  │
│    优化为 "Built ETL pipeline with Python..."         │
│    理由：更专业的动词 + 量化描述                       │
│                                                      │
│  ☐ 📏 量化增强：补充处理数据量                        │
│    ⚠️ 需要你提供具体数据                              │
│                                                      │
│  [✅ 执行选中的修改 (3条)]  [🔄 刷新建议]              │
└──────────────────────────────────────────────────────┘
```

### 页面 4：修改确认

```
┌──────────────────────────────────────────────────────┐
│  修改预览                                            │
│                                                      │
│  experience.tex                                      │
│  ──────────────────────────────────────────────      │
│  - \item Utilized Message Queue for async tasks      │
│  + \item Designed event-driven architecture with     │
│  +   Apache Kafka processing 100K msg/sec            │
│  ──────────────────────────────────────────────      │
│                                                      │
│  projects.tex                                        │
│  ──────────────────────────────────────────────      │
│  (列表重新排序：分布式项目移到第一位)                  │
│  ──────────────────────────────────────────────      │
│                                                      │
│  [🔄 回滚]  [📥 下载修改后的 LaTeX]  [📄 生成 PDF]   │
└──────────────────────────────────────────────────────┘
```

---

## 十一、Prompt 工程策略

### 系统级 Prompt 设计原则

```
┌─────────────────────────────────────────┐
│ Level 1: 硬约束（不可违反）              │
│ - 不编造经历、项目、技能                │
│ - 不修改时间、公司名、职位               │
│ - 只修改用户明确确认的内容               │
├─────────────────────────────────────────┤
│ Level 2: 格式约束                        │
│ - 保持 LaTeX 语法正确                    │
│ - 不修改 preamble / cls / 宏定义         │
│ - 输出完整段落，不是片段                  │
├─────────────────────────────────────────┤
│ Level 3: 质量约束                        │
│ - 使用行业标准动词（Architected > Made）  │
│ - 量化优先（"处理 500K 条/天" > "处理大量数据"）│
│ - STAR 法则（情境-任务-行动-结果）        │
└─────────────────────────────────────────┘
```

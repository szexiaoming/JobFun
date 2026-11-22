# AI JobFun — 分阶段开发路线

---

## Phase 概览

```
Phase 1 (MVP)          Phase 2 (RAG)         Phase 3 (修改)        Phase 4 (PDF)         Phase 5 (进度)
─────────────────     ─────────────────     ─────────────────     ─────────────────     ─────────────────
                                                                                        
 上传简历 ✅           向量存储 JD/简历       修改 LaTeX 源码       pdflatex 编译         求职看板 CRUD
 输入 JD (文本/图片)    相似 JD 匹配           Git 版本控制          PDF 下载              状态流转
 匹配评分               建议复用              修改前后 Diff         编译校验+回滚          面试题生成
 修改建议               语义搜索              用户确认→执行         完整闭环              数据统计
                                                                                        
 可看不可改 ──────────→ 更聪明的建议 ────────→ 可以改了 ──────────→ 自动出 PDF ────────→ 完整求职管家
```

---

## Phase 1：MVP — 分析引擎（可看不可改）

### 功能目标

> 用户上传简历 + 输入 JD → 看到匹配评分 + 修改建议。**不做任何文件修改。**

| 功能 | 说明 |
|------|------|
| 简历上传 | 支持 LaTeX 文件包（zip），解析为结构化 JSON |
| JD 输入 | 文本粘贴 + 图片上传（Claude Vision） |
| JD 结构化提取 | Claude API 提取公司/职位/技能/要求 |
| 匹配评分 | 六维度评分 + 已匹配/缺失技能 + 风险点 |
| 修改建议 | AI 生成优化建议列表，按类别分 |
| 结果展示 | Streamlit 页面展示评分 + 建议（纯看） |

### 用户流程

```
上传简历 zip ──→ 粘贴/拍照 JD ──→ 点击「开始分析」──→ 看到评分 + 建议列表（完）
```

### 需要的文件

```
jobfun/
├── app.py                          # Streamlit 主入口（单页模式）
├── config.py                       # 全局配置（API key、路径等）
├── requirements.txt
├── .env.example
├── .gitignore
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── jd_parser.py            # JD 文本/图片 → 结构化 JSON
│   │   ├── latex_parser.py         # LaTeX 源码 → 结构化 JSON
│   │   └── match_engine.py         # 匹配评分 + 建议生成
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── client.py               # Anthropic SDK 封装
│   │   └── prompts/
│   │       ├── __init__.py
│   │       ├── jd_extraction.py    # JD 提取 prompt 模板
│   │       └── match_scoring.py    # 匹配评分 + 建议 prompt 模板
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── sqlite_client.py        # SQLite 连接 + CRUD
│   │   └── models.py               # 数据模型（dataclass）
│   │
│   └── utils/
│       ├── __init__.py
│       ├── file_utils.py           # zip 解压、文件操作
│       └── logger.py               # 日志
│
├── ui/
│   ├── __init__.py
│   ├── home.py                     # 首页：上传 + JD 输入 + 开始分析
│   └── match.py                    # 结果页：评分 + 建议
│
├── data/                           # gitignored
│   ├── sqlite/
│   │   └── jobfun.db
│   ├── uploads/                    # 用户上传的原始文件
│   └── resumes/                    # 解压后的简历
│
└── tests/
    ├── __init__.py
    ├── test_jd_parser.py
    ├── test_latex_parser.py
    ├── test_match_engine.py
    └── fixtures/
        ├── sample_resume.zip
        └── sample_jd.txt
```

### 需要安装的库

```txt
# === 核心 ===
streamlit>=1.28.0
anthropic>=0.39.0
python-dotenv>=1.0.0

# === 数据处理 ===
pandas>=2.0.0

# === 文件处理 ===
Pillow>=10.0.0          # 图片处理（JD 截图）

# === 测试 ===
pytest>=7.0.0
```

**为什么 Phase 1 不需要这些？**
- ❌ `chromadb` → Phase 2
- ❌ `GitPython` → Phase 3
- ❌ `pdflatex` → Phase 4

### 输入输出

| 步骤 | 输入 | 输出 |
|------|------|------|
| 上传简历 | `resume.zip`（含 main.tex + cls + sections/*.tex） | 解压到 `data/resumes/{id}/`，解析为 `structured_json` 存入 SQLite |
| 输入 JD（文本） | 文本框纯文本 | 调用 Claude API → `JD 结构化 JSON` |
| 输入 JD（图片） | `.png` / `.jpg` 文件 | 调用 Claude Vision API → `JD 结构化 JSON` |
| 匹配分析 | 简历 JSON + JD JSON | 六维度评分 + 技能清单 + 建议列表 → 存入 SQLite + 展示 |

**统一的 JD 结构化 JSON Schema**：

```json
{
  "company": "Google",
  "position": "Senior SDE",
  "team": "Cloud",
  "required_skills": ["Python", "K8s", ...],
  "preferred_skills": ["gRPC", ...],
  "years_experience": 5,
  "education": "BS in CS",
  "responsibilities": ["Design ...", ...],
  "soft_skills": ["collaboration", ...],
  "source_type": "text | image"
}
```

**匹配评分输出**：

```json
{
  "total_score": 78,
  "skill_score": 85,
  "experience_score": 72,
  "education_score": 90,
  "soft_skill_score": 65,
  "culture_score": 70,
  "matched_skills": ["Python", "AWS", "Docker", ...],
  "missing_skills": ["Terraform", "gRPC"],
  "risks": ["JD 要求 5 年经验，当前 3 年"],
  "suggestions": [
    {
      "category": "keyword",
      "priority": 1,
      "original": "...",
      "suggested": "...",
      "rationale": "..."
    }
  ]
}
```

### 测试方法

| 测试 | 方法 | 预期 |
|------|------|------|
| LaTeX 解析 | 准备一个标准 Overleaf 简历 zip，运行 `latex_parser.parse()` | 输出正确的 section 结构，每个 entry 有 header 和 bullets |
| JD 文本提取 | 输入一段真实 JD 文本，运行 `jd_parser.parse_text()` | 输出包含 company/position/skills 的结构化 JSON |
| JD 图片提取 | 上传一张 JD 截图，运行 `jd_parser.parse_image()` | 输出与文本提取同 schema 的结构化 JSON（OCR 准确） |
| 匹配评分 | 给定固定简历 JSON + 固定 JD JSON | 评分可复现，建议有理由 |
| 端到端 | 启动 `streamlit run app.py`，走完整流程 | 页面不崩溃，结果正确展示 |
| API Mock 测试 | 用 mock Anthropic 响应跑 `match_engine` | 不消耗真实 API token，逻辑正确 |

### Phase 1 成功的标志

- [ ] `streamlit run app.py` 启动无报错
- [ ] 能上传 Overleaf 简历 zip，解压并解析
- [ ] 能粘贴 JD 文本，得到结构化提取
- [ ] 能上传 JD 截图，得到同样结构化的提取
- [ ] 能点击分析，看到六维度评分 + 建议列表
- [ ] 所有数据持久化到 SQLite
- [ ] 不需要 LaTeX 环境即可运行

---

## Phase 2：RAG — 向量检索增强

### 功能目标

> 用 ChromaDB 存储历史的 JD 和修改建议，当分析新 JD 时自动检索相似的历史 JD，复用有效建议。

| 功能 | 说明 |
|------|------|
| JD 向量化 | 新 JD 结构化后自动 embedding 存入 ChromaDB |
| 相似 JD 检索 | 分析新 JD 时 Top-K 相似历史 JD |
| 建议复用 | 历史上对相似 JD 的高分建议自动推荐 |
| 语义搜索 | 用户可搜索"显示所有要求 Kafka 的 JD" |

### 用户流程变化

```
上传 JD
    │
    ▼
JD 文本 → embedding ──→ ChromaDB 检索 Top-3 相似 JD
    │                       │
    ▼                       ▼
Claude 提取结构化      历史匹配报告
    │                       │
    └───────┬───────────────┘
            ▼
    Claude 综合当前 JD + 历史参考 → 更精准的建议
            │
            ▼
    展示评分 + 建议（标注哪些来自历史复用）
```

### 新增/修改文件

```
src/
├── core/
│   └── match_engine.py        # 修改：增加 RAG 上下文注入
│
├── ai/
│   └── prompts/
│       └── match_scoring.py   # 修改：prompt 增加历史 JD 参考模板
│
├── db/
│   ├── chroma_client.py       # 新增：ChromaDB 初始化 + CRUD
│   └── models.py              # 修改：增加 embedding 相关模型
│
└── core/
    └── retriever.py           # 新增：相似 JD 检索 + 建议复用逻辑

tests/
├── test_chroma_client.py      # 新增
└── test_retriever.py          # 新增
```

### 新增依赖

```txt
# Phase 2 新增
chromadb>=0.4.0
sentence-transformers>=2.2.0   # 或直接用 Claude Embeddings API
```

**Embedding 方案选择**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| Claude Embeddings API | 质量高，统一 API 供应商 | 额外 API 费用 |
| sentence-transformers (all-MiniLM-L6-v2) | 本地免费，384 维，够用 | 质量略低于 Claude |

**MVP 建议用 sentence-transformers**（免费，无需额外 API key），后续可切到 Claude。

### ChromaDB Collection 设计

| Collection | 存储内容 | 向量维度 | metadata |
|-----------|---------|---------|---------|
| `jds` | JD 结构化摘要 + 技能列表拼接文本 | 384 | company, position, skills, date |
| `suggestions` | 修改建议文本 | 384 | category, priority, jd_id, accepted_count |

### 输入输出

| 步骤 | 输入 | 输出 |
|------|------|------|
| JD Embedding | JD 结构化 JSON 的技能+描述拼接文本 | 384 维向量 → 存入 `jds` collection |
| 相似检索 | 新 JD embedding | Top-3 相似 JD + 相似度分数 |
| 建议复用 | 相似 JD 的 match_id | 历史上 accepted 的高分建议列表 |
| 增强匹配 | 简历 JSON + JD JSON + 历史上下文 | 更精准的评分 + 带"历史复用"标记的建议 |

### 测试方法

| 测试 | 方法 | 预期 |
|------|------|------|
| ChromaDB 写入 | 存入 10 条 JD | 无报错，collection.count() == 10 |
| 相似检索 | 存入 5 条后端 JD + 3 条前端 JD，查询后端 JD | Top-3 全是后端 JD |
| 建议复用 | 相似 JD 有 2 条 accepted 建议 | 返回这 2 条，带来源标记 |
| 边角：空库 | 首次使用，ChromaDB 为空 | 降级为纯 Claude 分析，不报错 |
| 边角：重复 JD | 同一个 JD 分析两次 | 直接命中缓存，跳过 API 调用 |

### Phase 2 成功的标志

- [ ] `chroma_client` 初始化不报错（ChromaDB 用本地持久化模式）
- [ ] 分析新 JD 时自动检索 Top-3 相似历史 JD
- [ ] 匹配报告中出现"历史复用建议"标记
- [ ] 空库首次运行不崩溃（降级处理）
- [ ] 同上 JD 再次分析时能命中缓存

---

## Phase 3：LaTeX 自动修改

### 功能目标

> 用户勾选采纳的建议 → 系统自动修改 LaTeX 源码 → Git 记录版本 → 展示 Diff。

**这是最核心也最危险的环节，安全是第一优先级。**

### 用户流程

```
Phase 1/2 的建议列表
        │
        ▼
用户勾选 3 条建议 → 点击「执行修改」
        │
        ▼
┌──────────────────────────────┐
│  1. Git commit（修改前备份）  │
│  2. Claude 根据建议修改 LaTeX │
│  3. 校验修改结果              │
│     - 公司名不变？            │
│     - 时间不变？              │
│     - 项目数不变？            │
│     - LaTeX 语法合法？        │
│  4. Git commit（修改后）      │
│  5. 展示 Diff                │
│  6. 用户可选：确认 / 回滚     │
└──────────────────────────────┘
```

### 安全护栏（硬约束）

```
┌─────────────────────────────────────────────┐
│ Layer 1: Prompt 约束                         │
│ System Prompt 明确"只改用户指定的内容"        │
├─────────────────────────────────────────────┤
│ Layer 2: 结构化校验                          │
│ 修改前后对比：公司名、时间、entry 数量不变    │
│ 违反任何一条 → 拒绝修改 + 告警               │
├─────────────────────────────────────────────┤
│ Layer 3: Git 回滚                            │
│ 每次修改一个 commit，可一键 `git revert`     │
├─────────────────────────────────────────────┤
│ Layer 4: 用户确认                            │
│ Diff 先展示，用户手动确认后才算完成           │
└─────────────────────────────────────────────┘
```

### 新增/修改文件

```
src/
├── core/
│   ├── latex_modifier.py       # 新增：修改执行器（核心）
│   └── match_engine.py         # 不改
│
├── ai/
│   └── prompts/
│       └── latex_edit.py       # 新增：LaTeX 修改专用 prompt
│
├── latex/                       # 新增：LaTeX 子系统
│   ├── __init__.py
│   ├── parser.py               # 从 core/latex_parser.py 迁移+增强
│   ├── modifier.py             # LaTeX AST 级别修改
│   └── validator.py            # 修改后安全校验
│
├── utils/
│   ├── diff_utils.py           # 新增：Diff 生成（unified diff）
│   └── git_utils.py            # 新增：Git init/commit/revert 封装
│
└── db/
    └── models.py               # 修改：suggestions 表增加 modified_text

ui/
├── suggestions.py              # 修改：增加勾选 + 执行按钮
└── resume_editor.py            # 新增：Diff 展示 + 确认/回滚页

tests/
├── test_latex_modifier.py      # 新增
├── test_latex_validator.py     # 新增
└── test_git_utils.py           # 新增
```

### 新增依赖

```txt
# Phase 3 新增
GitPython>=3.1.0
diff-match-patch>=20230430    # 或直接用 Python difflib（内置）
```

### 输入输出

| 步骤 | 输入 | 输出 |
|------|------|------|
| 用户选择 | 勾选的 suggestion_id 列表 | 待执行的修改计划 |
| Git 备份 | 简历目录路径 | `git commit` hash |
| LaTeX 修改 | 原始 `.tex` 文件 + suggestion 列表 | 修改后的 `.tex` 文件 |
| 安全校验 | 修改前后结构化 JSON | 通过/拒绝 + 违规项列表 |
| Diff 展示 | 修改前后文件内容 | unified diff（绿色+红色） |
| 用户确认 | 用户点击「确认」或「回滚」 | 确认 → Git commit；回滚 → Git revert |

**修改粒度**：

```
    粗粒度（整个文件）  ←── 不采用，太危险
    段落级（一个 section） ←── 不采用
    entry 级（一段经历）  ←── ✅ 采用
    bullet 级（一个要点） ←── ✅ 采用（最佳粒度）
```

Claude 始终只修改指定的 entry/bullet，不改其他内容。

### 测试方法

| 测试 | 方法 | 预期 |
|------|------|------|
| 单条修改 | 1 条建议 → 执行修改 | 只改了那一行，其他不变 |
| 多条修改 | 3 条建议 → 执行修改 | 3 处都改了，其他不变 |
| 安全校验：公司名 | Prompt 中尝试改公司名 | validator 拒绝，返回违规 |
| 安全校验：时间 | Prompt 中尝试改时间 | validator 拒绝，返回违规 |
| 安全校验：新增项目 | Prompt 中尝试加一个项目 | validator 拒绝，返回违规 |
| Git 回滚 | 修改完成后回滚 | 文件恢复到修改前，git log 正确 |
| Diff 展示 | 修改完成后 | 展示正确的 diff，红色/绿色正确 |
| 空建议 | 不勾选任何建议点执行 | 提示"未选择修改" |

### Phase 3 成功的标志

- [ ] 勾选建议 → 执行修改 → Diff 展示 → 用户确认 → 修改成功
- [ ] 安全校验生效：尝试编造经历时被拦截
- [ ] 可以一键回滚到修改前
- [ ] 修改后 LaTeX 源码语法正确（手动检查）
- [ ] Git log 中能看到每次修改的 commit 记录

---

## Phase 4：PDF 自动生成

### 功能目标

> 修改确认后的 LaTeX 源码 → 自动编译为 PDF → 用户下载。

### 用户流程

```
Phase 3 修改确认
        │
        ▼
  [📄 生成 PDF]
        │
        ▼
  pdflatex 编译
        │
        ├── 编译成功 → 展示 "✅ PDF 已生成" → [📥 下载 PDF] [📥 下载 LaTeX 源码包]
        │
        └── 编译失败 → 展示编译错误日志 → [🔄 自动修复] [↩ 回滚]
                            │
                    Claude 根据错误日志修复 LaTeX
                            │
                    重新编译 → 成功/失败
```

### 编译环境

| 方案 | 说明 | 推荐度 |
|------|------|--------|
| 本地 TeX Live / MiKTeX | 需要用户安装完整的 LaTeX 发行版（~4GB） | ⭐ 最稳定 |
| Docker + TeX Live | `docker run texlive/texlive pdflatex ...` | ⭐⭐ 环境一致 |
| tectonic | Rust 写的轻量 LaTeX 引擎，支持 Overleaf 项目 | ⭐⭐⭐ 推荐试用 |

**建议先支持本地 pdflatex，后续可加 tectonic 作为备选。**

### 新增/修改文件

```
src/
├── core/
│   └── pdf_compiler.py          # 新增：PDF 编译 + 错误处理
│
├── latex/
│   ├── compiler.py              # 新增：pdflatex 调用封装
│   └── error_parser.py          # 新增：解析 LaTeX 编译错误日志
│
└── ai/
    └── prompts/
        └── latex_fix.py         # 新增：LaTeX 编译错误修复 prompt

ui/
└── resume_editor.py             # 修改：增加「生成 PDF」按钮 + 下载

data/
└── outputs/                     # 新增：PDF 输出目录
    └── {resume_id}/
        ├── resume_v3.pdf
        └── resume_v3.zip        # LaTeX 源码包
```

### 新增依赖

```txt
# Phase 4 新增（这些不需要 pip install，需要系统安装）
# TeX Live 或 MiKTeX（提供 pdflatex 命令）
```

**运行时检查**：
- `pdflatex --version` → 可用则直接编译
- 不可用 → 提示用户安装，或降级为"仅下载 LaTeX 源码包"

### 输入输出

| 步骤 | 输入 | 输出 |
|------|------|------|
| 编译 | 简历目录路径（含 main.tex） | PDF 文件路径 或 编译错误日志 |
| 错误修复 | 错误日志 + LaTeX 源码 | Claude 修复后的 LaTeX 源码 → 重新编译 |
| 下载 | PDF 路径 | 浏览器触发文件下载 |
| 源码包 | 简历目录路径 | `resume_v{N}.zip`（含全部 .tex + .cls） |

### 测试方法

| 测试 | 方法 | 预期 |
|------|------|------|
| 正常编译 | 使用合规的 LaTeX 简历 | 生成 PDF，文件存在且非空 |
| 编译失败 | 故意在 .tex 中写 `\invalidcmd` | 捕获错误日志，不崩溃 |
| 错误修复 | 编译失败 → 自动修复 | Claude 修复后重新编译成功（或最终降级提示） |
| 环境缺失 | 系统没装 pdflatex | 优雅提示，提供安装指引 + LaTeX 源码包下载 |
| PDF 下载 | 点击下载按钮 | 浏览器下载正确文件 |
| 中文支持 | 简历含中文 | 自动使用 xelatex（需要检查中文字符） |

### Phase 4 成功的标志

- [ ] 修改后的简历可以一键编译为 PDF
- [ ] PDF 内容与 LaTeX 源码一致，格式正确
- [ ] 编译失败时有错误提示，不会静默失败
- [ ] 可以下载 PDF + LaTeX 源码包
- [ ] 没有 LaTeX 环境时给出清晰的安装指引

---

## Phase 5：求职进度管理

### 功能目标

> 完整的求职看板：记录每个岗位的申请状态、面试题生成、数据统计。从"单次分析"变成"长期求职伴侣"。

### 用户流程

```
求职看板
    │
    ├── 列表视图：所有申请（公司/岗位/状态/匹配分/时间）
    │       │
    │       ├── 点击某条 → 详情页（JD/简历/面试题/笔记）
    │       │
    │       ├── 新增申请 ──→ 从已有 JD+简历创建 或 全新录入
    │       │
    │       └── 更新状态：已收藏 → 已投递 → OA → 面试 → Offer → 已拒绝
    │
    ├── 面试准备页
    │       ├── 技术面：根据 JD 技能生成
    │       ├── 项目追问：根据简历项目生成
    │       ├── 行为面：STAR 问题
    │       ├── 英文面：英文问题
    │       └── 系统设计：根据职级生成
    │
    └── 统计 Dashboard
            ├── 投递数 / 面试数 / Offer 数
            ├── 平均匹配度
            ├── 状态分布饼图
            └── 时间线
```

### 新增/修改文件

```
src/
├── core/
│   ├── progress_manager.py      # 新增：申请 CRUD + 状态流转
│   └── interview_generator.py   # 新增：面试题生成
│
└── ai/
    └── prompts/
        └── interview.py         # 新增：面试题生成 prompt

ui/
├── home.py                      # 修改：仪表盘增加统计数据
├── tracker.py                   # 新增：求职看板页
├── application_detail.py        # 新增：单条申请详情页
└── interview_prep.py            # 新增：面试准备页

src/db/
└── models.py                    # 修改：新增 applications / interview_questions 表
```

### 新增依赖

```txt
# Phase 5 新增（无额外依赖）
# streamlit 自带的 chart 够用
# 如果需要好看的图表：plotly>=5.0.0（可选）
```

### 输入输出

| 步骤 | 输入 | 输出 |
|------|------|------|
| 新建申请 | JD（可从已有 JD 选 或 新建）+ 简历版本 | application 记录 |
| 更新状态 | application_id + 新状态 + 备注 | 更新后的记录 + 时间戳 |
| 面试题生成 | match_id | 5 类面试题（各 5-10 题）|
| 统计 | 用户所有 application | 数量统计 + 状态饼图 + 趋势 |

### 面试题生成 Schema

```json
{
  "match_id": 42,
  "categories": {
    "technical": [
      {
        "question": "Explain Python's GIL mechanism...",
        "suggested_answer": "...",
        "difficulty": "medium"
      }
    ],
    "project_deep_dive": [...],
    "behavioral": [...],
    "english": [...],
    "system_design": [...]
  }
}
```

### 测试方法

| 测试 | 方法 | 预期 |
|------|------|------|
| 新建申请 | 选择一个已有 JD + 简历，创建申请 | application 表新增一条，状态为 saved |
| 状态流转 | saved → applied → interview → offer | 状态正确更新，updated_at 变更 |
| 看板过滤 | 按状态筛选 | 只显示对应状态的申请 |
| 面试题生成 | 给定 match_id | 生成 5 类题目，每题有难度标记 |
| 面试题不重复 | 同 match_id 再生成一次 | 题目不同（或明确标记"重新生成"） |
| 统计正确 | 手动插入已知数据 | 统计数字完全匹配 |
| 空状态 | 0 条申请 | 显示引导页"开始你的第一份申请" |

### Phase 5 成功的标志

- [ ] 看板页能展示所有申请，支持状态筛选
- [ ] 状态流转正常（saved → applied → oa → interview → offer → rejected）
- [ ] 可以记录笔记和时间
- [ ] 面试准备页能根据 JD+简历生成题目
- [ ] 仪表盘统计数据正确
- [ ] 各页面导航流畅

---

## 自定义 Slash Command 设计

### 为什么需要自定义 Skill

JobFun 有两种使用模式互补：

| 模式 | 入口 | 适用场景 |
|------|------|---------|
| 🌐 **Web UI** (Streamlit) | 浏览器 | 完整体验、看板管理、演示展示 |
| ⌨️ **CLI** (Slash Command) | Claude Code 终端 | 快速单次分析、不想启动服务时 |

CLI 模式通过 Claude Code 的**自定义 Slash Command** 实现，本质是给 Agent 的结构化 Prompt 指令。即使底层代码还在开发中，Skill 可以先定义好行为规范。

### Skill 与开发阶段的关系

| Skill | 激活时机 | 依赖 |
|-------|---------|------|
| `/analyze` | Phase 1 完成后 | jd_parser + latex_parser + match_engine |
| `/suggest` | Phase 1 完成后 | match_engine（在已有 match 上追加建议） |
| `/apply` | Phase 3 完成后 | latex_modifier + git_utils + validator |
| `/prep` | Phase 5 完成后 | interview_generator |

---

### Skill 1：`/analyze` — JD 匹配分析

**用途**：上传简历 + 输入 JD → 输出六维度评分卡 + 修改建议。

**文件**：`.claude/commands/analyze.md`

**行为规范**：

```
当用户输入 /analyze 时，执行以下流程：

1. 确认简历来源
   - 如果用户已上传简历：列出已有简历，让用户选择
   - 如果用户拖入了 zip 文件：解压并解析新简历
   - 如果都没有：提示用户先上传简历

2. 确认 JD 来源
   - 用户粘贴的文本 → 直接使用
   - 用户拖入的图片 → 调用 Claude Vision 提取文字 → 结构化
   - 用户提供了 JD ID → 从数据库读取已有 JD
   - 都没有：提示用户输入 JD

3. 执行匹配分析
   - 调用 src.core.jd_parser 解析 JD
   - 调用 src.core.latex_parser 解析简历
   - 调用 src.core.match_engine 计算匹配度
   - 生成六维度评分 + 技能清单 + 风险点

4. 输出格式
   - 评分卡（ASCII 进度条）
   - 已匹配/缺失技能标签
   - 风险点列表
   - Top 5 修改建议（按优先级）
   - 底部提示：/suggest 获取更多建议 | /apply 执行修改
```

**输入示例**：

```
/analyze
简历: my_resume_v3
JD: [粘贴 Google SDE JD 文本]
```

**输出示例**：

```
╔══════════════════════════════════════════╗
║        Google — Senior SDE              ║
║        匹配度: 78%                       ║
╠══════════════════════════════════════════╣
║  技能匹配  85%  ████████████████░░       ║
║  经验匹配  72%  ██████████████░░░░       ║
║  学历匹配  90%  ██████████████████░      ║
║  软技能    65%  █████████████░░░░░       ║
║  文化匹配  70%  ██████████████░░░░       ║
╠══════════════════════════════════════════╣
║  ✅ Python, K8s, Docker, AWS            ║
║  ❌ Terraform, gRPC                     ║
║  ⚠️ JD 要求 5 年，你当前 3 年            ║
╠══════════════════════════════════════════╣
║  🔑 [P1] 将 "Message Queue" 改为 Kafka  ║
║  📐 [P2] 分布式项目移到第一             ║
║  ✨ [P3] 优化 Python 描述措辞            ║
║  ...                                     ║
╠══════════════════════════════════════════╣
║  /suggest # 更多建议                     ║
║  /apply 1,2   # 执行建议 1 和 2         ║
╚══════════════════════════════════════════╝
```

---

### Skill 2：`/suggest` — 修改建议扩展

**用途**：对已有的匹配结果，生成更多/更细的修改建议。

**文件**：`.claude/commands/suggest.md`

**行为规范**：

```
当用户输入 /suggest 时，执行以下流程：

1. 确定上下文
   - 用户指定了 match_id → 使用该匹配
   - 用户指定了 JD+简历 → 使用最近一次匹配
   - 都没有 → 列出最近的匹配让用户选择

2. 生成建议
   - 如果用户指定了类别（--category keyword）→ 只生成该类建议
   - 默认生成所有类别，但排除用户已拒绝的建议
   - 检查 ChromaDB（Phase 2+）复用相似 JD 的高分建议

3. 输出格式
   - 按优先级排列
   - 每条：ID + 类别标签 + 原文 + 建议文 + 理由
   - 标注来源（AI 新生成 vs 历史复用）
```

**输入示例**：

```
/suggest --category wording --count 5
/suggest --focus missing-skills    # 专门针对缺失技能找可匹配的经历
/suggest --all                      # 重新生成全部建议
```

---

### Skill 3：`/apply` — 执行 LaTeX 修改

**用途**：勾选建议 ID → 自动修改 LaTeX 源码 → Diff 展示 → 用户确认。

**文件**：`.claude/commands/apply.md`

**行为规范**：

```
当用户输入 /apply <suggestion_ids> 时，执行以下流程：

1. 预检查
   - 确认建议对应的简历版本是最新的
   - 确认 LaTeX 文件存在且可读写
   - 列出即将执行的修改清单，请用户确认

2. 执行修改（用户确认后）
   - Step 1: Git commit（备份当前状态）
   - Step 2: 逐条执行修改
     - 对于每条建议，调用 Claude 修改对应 .tex 文件
     - 只修改 entry/bullet 级别内容
     - 不碰 preamble/cls/macro
   - Step 3: 安全校验
     - 公司名不变 ✓
     - 时间不变 ✓
     - 项目数量不变 ✓
     - LaTeX 语法合法 ✓
   - Step 4: Git commit（记录修改）
   - Step 5: 展示 Diff

3. 用户决策
   - ✅ 确认 → 修改完成，提示 /build 生成 PDF
   - ↩ 回滚 → git revert，提示"已恢复到修改前"
   - 🔄 调整 → 保持当前状态，用户手动编辑后再 commit

4. 安全边界（硬约束，不可跳过）
   - 系统 Prompt 明确"只改措辞，不编造经历"
   - 修改后自动运行安全校验
   - 任何校验失败 → 自动回滚 + 告警
```

**输入示例**：

```
/apply 1,3,5                     # 执行建议 1、3、5
/apply --dry-run 1,3,5           # 预览修改（不实际执行）
/apply --rollback                 # 回滚最近一次修改
/apply --history                  # 查看修改历史
```

---

### Skill 4：`/prep` — 面试准备

**用途**：基于 JD + 简历交叉分析，生成各类面试题。

**文件**：`.claude/commands/prep.md`

**行为规范**：

```
当用户输入 /prep 时，执行以下流程：

1. 确定上下文
   - 指定 match_id → 使用该匹配的 JD+简历
   - 指定 JD ID + 简历 ID → 使用这两个
   - 默认 → 最近一次的匹配

2. 生成题目
   - 默认生成全部 5 类，每类 5 题
   - 可选参数过滤：
     --category technical|project|behavioral|english|system-design
     --difficulty easy|medium|hard
     --count N
     --language zh|en   (题目语言)

3. 输出格式
   - 按类别分组
   - 每题：编号 + 题目 + 难度 + AI 参考答案
   - 底部提示：/prep --category system-design --difficulty hard
```

**输入示例**：

```
/prep --category system-design --difficulty hard
/prep --language en                 # 英文面试题
/prep --category project            # 项目追问题
/prep --all --count 3               # 每类 3 题
```

---

### Skill 文件目录

```
.claude/
├── commands/
│   ├── analyze.md               # /analyze — JD 匹配分析
│   ├── suggest.md               # /suggest — 修改建议
│   ├── apply.md                 # /apply — 执行修改
│   └── prep.md                  # /prep — 面试准备
└── settings.json                # 项目设置（权限等）
```

### Skill 到核心模块的映射

```
/analyze ──→ src/core/jd_parser.py
         ──→ src/core/latex_parser.py
         ──→ src/core/match_engine.py
         ──→ src/ai/prompts/jd_extraction.py
         ──→ src/ai/prompts/match_scoring.py

/suggest ──→ src/core/match_engine.py (追加建议模式)
         ──→ src/core/retriever.py (Phase 2+)

/apply  ──→ src/core/latex_modifier.py
         ──→ src/latex/modifier.py
         ──→ src/latex/validator.py
         ──→ src/utils/git_utils.py
         ──→ src/utils/diff_utils.py
         ──→ src/ai/prompts/latex_edit.py

/prep   ──→ src/core/interview_generator.py
         ──→ src/ai/prompts/interview.py
```

### 开发建议

- **Phase 1 开始前**：创建 4 个 `.md` 文件的骨架（只有行为规范描述，不调代码）
- **每完成一个 Phase**：让对应的 Skill 从 "伪指令" 变成 "真实调用 Python 模块"

---

## 完整依赖汇总

### requirements.txt（最终完整版）

```txt
# ==========================================
# Phase 1: MVP 分析引擎
# ==========================================
streamlit>=1.28.0
anthropic>=0.39.0
python-dotenv>=1.0.0
pandas>=2.0.0
Pillow>=10.0.0
pytest>=7.0.0

# ==========================================
# Phase 2: RAG 向量检索
# ==========================================
chromadb>=0.4.0
sentence-transformers>=2.2.0

# ==========================================
# Phase 3: LaTeX 自动修改
# ==========================================
GitPython>=3.1.0

# ==========================================
# Phase 4: PDF 生成
# ==========================================
# (需要系统安装 TeX Live / MiKTeX，不是 pip 包)

# ==========================================
# Phase 5: 求职进度管理
# ==========================================
plotly>=5.0.0   # 可选：更好看的图表
```

---

## 开发路线总览

```
                    Phase 1           Phase 2        Phase 3        Phase 4         Phase 5
                    2-3 周            1 周            1.5 周         0.5 周          1 周
                 ───────────      ───────────     ───────────    ───────────     ───────────
                 
Steamlit UI      ████████████      ░░░░░░░░░░      ░░░░░░░░░░     ░░░░░░░░░░      ████████████
                   首页+结果页                        Diff页+确认页   PDF下载按钮      看板+统计+面试

LaTeX 解析        ████████████      ░░░░░░░░░░      ████████████    ░░░░░░░░░░      ░░░░░░░░░░
                   结构化提取                         AST+修改+校验                   

Claude API        ████████████      ████████████      ████████████    ████████████    ████████████
                 JD提取+评分+建议    增强prompt       LaTeX修改prompt  错误修复prompt    面试题prompt

SQLite            ████████████      ░░░░░░░░░░      ░░░░░░░░░░     ░░░░░░░░░░      ████████████
                   resumes+JDs                        latex_changes                   applications+
                   +matches+                          (新增表)                        questions(新表)
                   suggestions

ChromaDB          ░░░░░░░░░░      ████████████      ░░░░░░░░░░     ░░░░░░░░░░      ░░░░░░░░░░
                                    jds+suggestions
                                    collections

Git               ░░░░░░░░░░      ░░░░░░░░░░      ████████████    ░░░░░░░░░░      ░░░░░░░░░░
                                                    commit/revert

pdflatex          ░░░░░░░░░░      ░░░░░░░░░░      ░░░░░░░░░░     ████████████     ░░░░░░░░░░
                                                                  编译+校验

Slash Commands    ████████████      ░░░░░░░░░░      ████████████    ░░░░░░░░░░      ████████████
                  /analyze骨架      (静默)           /apply激活      (静默)           /prep激活
                  /suggest骨架                       (真实调用)                       (真实调用)
                  (伪指令→实调)

累计文件数          ~19              ~22              ~29             ~31              ~36
```

---

## 风险与应对

| 风险 | 影响阶段 | 应对 |
|------|---------|------|
| LaTeX 解析不如预期 | Phase 1, 3 | 先用 Claude 直接理解 LaTeX 源码做 fallback，Parser 逐步完善 |
| Claude API 费用 | 全部 | Prompt Caching + Haiku 做简单任务 + 本地 embedding 免费 |
| pdflatex 环境缺失 | Phase 4 | 降级为仅下载 LaTeX 源码包 + 提供安装指引 |
| 安全校验被绕过 | Phase 3 | 多层防御：Prompt + 结构化校验 + 人工确认，任何一层拦截都可回滚 |
| ChromaDB 持久化 | Phase 2 | 用本地持久化模式（默认），定期备份 data/chroma 目录 |

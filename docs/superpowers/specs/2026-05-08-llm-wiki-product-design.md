# LLM Wiki 产品设计规格

> 基于 llm-wiki-agent 参考架构，全新构建的可视化知识库产品。

## 项目目标

将 llm-wiki-agent 的命令行/agent 工作流产品化为一个完整的 Web 应用：用户通过 Vue3 前端界面上传文件、管理源文件目录，系统自动调用 LLM 摄入知识、构建 Wiki 知识库和知识图谱。同时提供 REST API 供外部系统调用。

## 多租户设计

每个项目（知识库）是一个独立的数据空间，拥有自己的文件系统目录：

```
data/
├── projects/
│   ├── {project-id-1}/
│   │   ├── raw/           # 源文件（团队共享）
│   │   ├── wiki/           # Wiki 页面
│   │   │   ├── index.md
│   │   │   ├── log.md
│   │   │   ├── overview.md
│   │   │   ├── sources/
│   │   │   ├── entities/
│   │   │   ├── concepts/
│   │   │   └── syntheses/
│   │   └── graph/          # 图谱数据
│   │       ├── graph.json
│   │       └── graph.html
│   └── {project-id-2}/
│       └── ...
├── audit/                   # 全局审计日志（SQLite）
└── users.db                 # 用户 + 项目成员关系（SQLite）
```

项目成员角色：**Owner**（创建者，可删除项目/管理成员）、**Editor**（上传/摄入/查询/管理文件）、**Viewer**（只读查询和浏览）。

---

## 约束条件

| 维度 | 决策 |
|------|------|
| 部署 | 内网，前后端分离（Nginx + Python 后端） |
| LLM | 内部部署 DeepSeek v4 flash 兼容接口，不支持外部代理 |
| 存储 | 文件系统（markdown 文件），需备份恢复方案 |
| 图谱 | vis.js 离线自托管，不依赖外网 CDN |
| 用户 | 团队协作，多用户多项目 |
| 参考项目 | llm-wiki-agent（仅参考，不修改不依赖） |
| 开放接口 | API 优先（v1），Skill + MCP 后置 |
| 前端风格 | 暖奶油极简文档风（参考 sitor.ai），浅色主题 |

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    浏览器 (Vue3 SPA)                  │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│                   Nginx :80                          │
│      静态资源 (Vue dist)  +  /api/* → :8000          │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│                 FastAPI :8000                        │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ API 层    │  │ Service 层    │  │ Engine 层      │  │
│  │ 路由/验证  │→│ 业务逻辑      │→│ 核心引擎        │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
└──┬──────────────┬────────────────┬──────────────────┘
   │              │                │
┌──▼──┐    ┌─────▼─────┐   ┌─────▼──────┐
│文件系统│    │  SQLite   │   │ DeepSeek   │
│wiki/  │    │用户/项目   │   │ v4 flash   │
│raw/   │    │审计日志    │   │ 内部接口    │
│graph/ │    └───────────┘   └────────────┘
└──────┘
```

### 目录结构

```
backend/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理
│   ├── api/                    # API 路由层
│   │   ├── auth.py             # 认证路由
│   │   ├── projects.py         # 项目管理
│   │   ├── files.py            # 文件与目录管理
│   │   ├── ingestion.py        # 摄入触发与监控
│   │   ├── knowledge.py        # 知识查询与浏览
│   │   ├── graph.py            # 图谱构建与查询
│   │   └── maintenance.py      # 健康检查/备份/审计
│   ├── services/               # 业务逻辑层
│   │   ├── auth_service.py
│   │   ├── file_service.py     # 编排文件→wiki→图谱联动
│   │   ├── ingest_service.py
│   │   ├── query_service.py
│   │   ├── graph_service.py
│   │   ├── lint_service.py
│   │   └── backup_service.py
│   ├── engines/                # 核心引擎层
│   │   ├── wiki_engine.py      # Wiki 页面 CRUD / wikilinks / index
│   │   ├── llm_engine.py       # DeepSeek 调用（via litellm）
│   │   ├── graph_engine.py     # NetworkX + Louvain
│   │   └── convert_engine.py   # markitdown 多格式转换
│   ├── models/                 # Pydantic 数据模型
│   ├── storage/                # 文件系统操作封装
│   └── utils/
├── requirements.txt
└── pyproject.toml

frontend/
├── src/
│   ├── App.vue
│   ├── main.ts                 # Vue3 入口
│   ├── router/index.ts
│   ├── views/
│   │   ├── KnowledgeBaseView.vue   # 知识库主页（源文件+查询子视图）
│   │   ├── GraphView.vue           # 知识图谱
│   │   └── SettingsView.vue        # 设置（备份/日志/LLM 配置）
│   ├── components/
│   │   ├── layout/             # AppShell / Sidebar / TopBar
│   │   ├── files/              # DirTree / FileList / UploadDialog
│   │   ├── wiki/               # PageViewer / QueryInput / QueryResult
│   │   ├── graph/              # GraphCanvas / FilterPanel / NodeDetail
│   │   └── common/             # ConfirmDialog / ProgressBar / EmptyState
│   ├── composables/            # useApi / useAuth / useWiki / useGraph
│   ├── stores/                 # Pinia: auth / files / wiki / graph
│   └── types/
├── public/static/              # vis.js 离线自托管
├── package.json
├── vite.config.ts
└── tsconfig.json
```

---

## 后端三层设计

### API 层端点

#### 认证
- `POST /api/auth/login` — 登录，返回 JWT
- `POST /api/auth/register` — 注册（v1 可配置关闭，管理员手动创建账号）
- `GET /api/projects/{id}/members` — 项目成员列表
- `POST /api/projects/{id}/members` — 添加成员（Owner 操作）
- `DELETE /api/projects/{id}/members/{user_id}` — 移除成员

#### 项目管理
- `GET /api/projects` — 用户所属项目列表
- `POST /api/projects` — 创建项目
- `GET /api/projects/{id}` — 项目详情
- `DELETE /api/projects/{id}` — 删除项目

#### 文件与目录管理
- `GET /api/files/dirs` — 浏览 raw/ 目录树
- `POST /api/files/dirs` — 创建子目录（最多 3 层）
- `DELETE /api/files/dirs` — 删除空目录
- `POST /api/files/upload` — 上传文件到指定子目录
- `POST /api/files/upload-batch` — 批量上传
- `GET /api/files` — 文件列表（支持 dir/搜索/分页）
- `DELETE /api/files/{id}` — 删除文件（级联清理 wiki 页）
- `POST /api/files/move` — 移动文件到其他子目录

#### 摄入
- `POST /api/ingestion/trigger` — 触发摄入（单文件或批量）
- `GET /api/ingestion/status/{task_id}` — 摄入进度（5 步分阶段）
- `GET /api/ingestion/history` — 历史记录

#### 知识查询
- `POST /api/knowledge/query` — LLM 综合回答，附 `[[wikilink]]` 引用
- `GET /api/knowledge/pages` — Wiki 页面列表/树
- `GET /api/knowledge/pages/{path}` — 读取页面 markdown

#### 图谱
- `GET /api/graph/data` — 节点 + 边 JSON
- `POST /api/graph/build` — 触发构建
- `GET /api/graph/stats` — 统计信息

#### 维护
- `POST /api/backup/export` — 导出 tar.gz
- `POST /api/backup/import` — 恢复备份
- `GET /api/health` — 结构健康检查
- `POST /api/lint` — 语义质量检查
- `GET /api/audit-log` — 审计日志查询（支持筛选/分页/导出 CSV）

### Service 层

| Service | 职责 | 依赖引擎 |
|---------|------|----------|
| AuthService | 注册、登录、JWT、项目成员管理 | — |
| FileService | 上传/目录管理/删除/移动，编排文件→wiki→图谱联动 | ConvertEngine, IngestService, GraphService |
| IngestService | 摄入流程编排：读文件→调 LLM→写页面→更新索引→验证 | WikiEngine, LLMEngine |
| QueryService | 查 index→找相关页→LLM 综合回答→可选保存 | WikiEngine, LLMEngine |
| GraphService | 双 Pass 构建 + Louvain + SHA256 缓存 | WikiEngine, LLMEngine, GraphEngine |
| LintService | Orphan/Broken/矛盾检测 | WikiEngine, LLMEngine |
| BackupService | 全量导出/恢复/校验 | WikiEngine |

### Engine 层

| Engine | 职责 |
|--------|------|
| WikiEngine | 页面 CRUD（YAML 前页+markdown）、wikilink 提取/验证、index/log 维护、SHA256 |
| LLMEngine | litellm→DeepSeek v4 flash、Prompt 模板、JSON 解析、重试+超时 |
| GraphEngine | NetworkX 图构建、Louvain 社区检测、vis.js JSON 输出、SHA256 缓存 |
| ConvertEngine | markitdown 多格式转换（PDF/DOCX/PPTX/HTML 等） |

---

## 文件→Wiki→图谱自动联动

所有文件操作自动级联更新，保证三者一致：

### 上传/覆盖
```
上传文件 → ConvertEngine 转换
         → IngestService 摄入
         → 写入 wiki 页面
         → 更新 index.md / log.md
         → GraphService 重建图谱
```
覆盖时先清理旧 wiki 页面再重新摄入。

### 移动
```
移动到新目录 → 更新 wiki 页面 source_file 字段
             → 增量重建图谱
（文件内容未变，不重新摄入）
```

### 删除
```
删除文件 → 级联删除关联 wiki 页面
        → 从 index.md 移除
        → 清理孤立实体/概念页
        → 重建图谱
```

### 原子性保证
- 文件保存失败 → 终止，不触发摄入
- 摄入失败 → wiki 不写入，源文件保留
- 图谱构建失败 → 保留旧图谱，日志告警
- 项目级文件锁防并发（fcntl/filelock），同一项目同时只有一个摄入任务

---

## 审计日志

### 日志记录字段
timestamp | action | user_id | username | project_id | target | detail(JSON) | result | error

### 双重存储
- **wiki/log.md**：文本可读格式，追加写入（沿用原项目风格，扩展 user 字段）
- **SQLite audit_log 表**：结构化存储，支持按项目/用户/时间/操作类型查询和导出 CSV

### 安全约束
- 日志只追加，不提供修改/删除 API
- 随备份导出
- detail 仅含元信息，不含文件内容

---

## 前端设计

### 页面与路由

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | 登录 | JWT 认证 |
| `/` | 知识库主页 | 源文件管理 + 查询（Tab 切换） |
| `/graph` | 知识图谱 | vis.js 交互式图谱 |
| `/settings` | 设置 | LLM 配置、备份恢复、审计日志 |

### 导航结构
侧边栏 4 项（从 6 项精简）：
- 📖 知识库（含子视图：源文件 / 查询）
- 🔗 知识图谱
- ⚙️ 设置

### 设计风格

**配色**：暖奶油极简文档风

| 角色 | 色值 | 用途 |
|------|------|------|
| 页面背景 | `#F7F6F2` | 暖奶油底 |
| 卡片/内容区 | `#FFFFFF` | 白色层 + `#E7E2D9` 边框 |
| 正文 | `#44403C` | 暖深灰 |
| 次级文字 | `#78716C` | 暖中灰 |
| 主按钮/强调 | `#D97706` | 暖琥珀（hover: `#B45309`） |
| 链接 | `#B45309` | 深琥珀 |
| 成功 | `#ECFDF5` bg + `#065F46` text | 薄荷绿 |
| 警告 | `#FEF3C7` bg + `#92400E` text | |
| 错误 | `#FEE2E2` bg + `#991B1B` text | |
| 品牌元素 | amber 渐变（Logo）+ 页面角落 ~4% 放射纹理 | |

**排版**：系统字体栈，正文 14px/1.7，标题 weight 600，圆角 6-8px，间距 4px 基础单位。

### P1 交互保护
- **删除确认**：弹出对话框，显示将被级联删除的 wiki 页面列表，提供"仅删文件/同时清理 wiki"选项
- **摄入进度**：5 步可视化进度条（转换→LLM 提取→写页面→更新索引→重建图谱），每步显示耗时

### P2 新手体验
- **空状态引导**：空项目（引导上传）、空目录（拖拽区域）、空图谱（摄入进度提示）
- **图谱筛选**：折叠面板，默认仅展开节点类型，边/社区按需展开

### P3 品牌辨识
- amber 渐变 Logo + 品牌标语"知识从不丢失"
- 页面角落极淡 amber 放射渐变（仅大屏可见）

---

## API 调用流程

```
1. 用户上传文件
   POST /api/files/upload (multipart) { project_id, subdir, file }
   → 文件保存到 raw/{subdir}/file
   → 后台触发摄入任务
   → 返回 task_id

2. 前端轮询摄入进度
   GET /api/ingestion/status/{task_id}
   → { step: 3, total: 5, steps: [...], elapsed: 13.1s }

3. 摄入完成后自动重建图谱
   前端 GET /api/graph/data → 渲染 vis.js

4. 用户查询知识库
   POST /api/knowledge/query { question }
   → LLM 综合回答 + [[wikilink]] 引用 + 来源页面列表
```

---

## 备份方案

- **导出**：将项目下 `raw/` + `wiki/` + `graph/` + `audit_log` 打包为 tar.gz，含元信息 JSON
- **导入**：上传 tar.gz → 校验完整性 → 预览内容 → 确认恢复
- **增量备份**（v2）：SHA256 对比，仅导出变更文件

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端框架 | Vue 3 (Composition API + `<script setup>`) |
| 构建工具 | Vite |
| 状态管理 | Pinia |
| 请求 | Axios |
| 图谱渲染 | vis.js (离线自托管) |
| 后端框架 | FastAPI (Python 3.10+) |
| 认证 | JWT (python-jose) |
| LLM 调用 | litellm → DeepSeek v4 flash |
| 图计算 | NetworkX + Louvain |
| 文件转换 | markitdown |
| 数据库 | SQLite（用户/项目/审计日志） |
| 存储 | 文件系统（wiki/raw/graph） |
| 前端部署 | Nginx 静态托管 + 反向代理 |
| 后端部署 | Uvicorn / Gunicorn |

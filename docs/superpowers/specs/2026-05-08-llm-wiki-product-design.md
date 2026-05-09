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
| 图谱 | AntV G6 v5 离线自托管，不依赖外网 CDN |
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
│   │   ├── backup_service.py
│   │   └── lock_manager.py       # 并发锁管理
│   ├── engines/                # 核心引擎层
│   │   ├── wiki_engine.py      # Wiki 页面 CRUD / wikilinks / index
│   │   ├── llm_engine.py       # DeepSeek 调用（via litellm）
│   │   ├── graph_engine.py     # NetworkX + Louvain → G6 JSON 输出
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
│   │   ├── graph/              # GraphCanvas / FilterPanel / NodeDetail (G6)
│   │   └── common/             # ConfirmDialog / ProgressBar / EmptyState
│   ├── composables/            # useApi / useAuth / useWiki / useGraph
│   ├── stores/                 # Pinia: auth / files / wiki / graph
│   └── types/
├── public/static/              # AntV G6 离线自托管
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
| WikiEngine | 页面 CRUD（YAML 前页+markdown）、wikilink 提取/验证、index/log 维护、SHA256，所有写操作加锁 |
| LLMEngine | litellm→DeepSeek v4 flash、Prompt 模板、JSON 解析、重试+超时 |
| GraphEngine | NetworkX 图构建、Louvain 社区检测、输出 G6 兼容 JSON、SHA256 缓存 |
| ConvertEngine | markitdown 多格式转换（PDF/DOCX/PPTX/HTML 等） |
| LockManager | 项目级 + 文件级读写锁管理，确保并发安全 |

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

### 操作原子性
- 文件保存失败 → 终止，不触发摄入
- 摄入失败 → wiki 不写入，源文件保留
- 图谱构建失败 → 保留旧图谱，日志告警

---

## 并发安全设计

多用户同时操作同一项目的文件系统和 Wiki 需要严格的并发控制。

### 锁分层策略

```
LockManager
├── 项目级写锁 (per-project write lock)
│   保护：摄入任务、图谱构建
│   同一项目同时最多 1 个摄入 + 1 个图谱构建排队
│
├── Wiki 页面锁 (per-page lock)
│   保护：单个 .md 页面的读写
│   多读并发，写入互斥
│
├── 文件操作锁 (per-directory lock)
│   保护：raw/ 目录下的上传/移动/删除
│   同一目录并发上传不同文件 → 允许
│   同一目录移动/删除 → 排队
│
└── 索引锁 (index lock)
    保护：index.md、log.md、overview.md
    写入互斥，读取不受限
```

### 并发场景处理

| 场景 | 锁策略 | 行为 |
|------|--------|------|
| 多用户同时查询 | 无锁 | 读取 wiki 页面和 index，完全并发 |
| 用户 A 摄入，用户 B 查询 | A 持有项目写锁，B 无锁读 | B 读取当前快照，A 写入完成后 B 可见新内容 |
| 用户 A 摄入，用户 B 上传文件 | B 正常上传到 raw/，任务排队 | 返回 task_id，在摄入队列中等待 |
| 用户 A 摄入，用户 B 触发摄入 | B 返回 409 Conflict | `{"status":"conflict","current_task_id":"xxx","message":"项目正在摄入中"}` |
| 用户 A 删除文件，用户 B 查看文件 | B 读取时文件已删除 | 返回 404，前端刷新文件列表 |
| 用户 A 和 B 同时修改同一目录 | A 获锁，B 排队（最多 5s） | B 超时返回 423 Locked |
| 用户 A 构建图谱，用户 B 查看图谱 | B 读取旧图谱 | 构建完成后自动切换为新图谱 |
| 用户 A 读 wiki 页面，用户 B 写同一页面 | 页面级读写锁 | A 读完释放锁后 B 写入 |

### 锁实现

```python
# 使用文件系统锁（fcntl / filelock），无额外中间件依赖
# 所有锁在进程内有效，跨进程也有效

class LockManager:
    def __init__(self, data_dir: Path):
        self.lock_dir = data_dir / ".locks"
        self.lock_dir.mkdir(exist_ok=True)

    def acquire_project_write(self, project_id: str, timeout: float = 300):
        """项目级写锁 — 摄入和图谱构建时持有"""
        ...

    def acquire_page_lock(self, page_path: Path, mode: str = "rw"):
        """页面级读写锁"""
        ...

    def acquire_directory_lock(self, dir_path: Path, timeout: float = 5):
        """目录级写锁 — 移动/删除时持有"""
        ...

    def acquire_index_lock(self, project_id: str):
        """索引文件写锁 — 更新 index/log 时持有"""
        ...
```

### 摄入任务队列

每个项目维护一个轻量级内存队列：

```
ProjectQueue
├── current_task: Task | None     # 正在执行的任务
├── pending_tasks: deque[Task]    # 排队等待的任务
└── max_queue_size: int = 10      # 最大排队数

Task
├── task_id: str                  # UUID
├── action: "ingest" | "graph_build"
├── file_paths: list[str]
├── status: "queued" | "running" | "completed" | "failed"
├── progress: int                 # 0-100
└── created_by: str               # user_id
```

- 队列中前一个任务完成（或失败）后自动启动下一个
- 任务完成/失败通过 WebSocket 或轮询通知前端
- 服务重启后队列清空（内存队列），未完成的任务需手动重新触发

### 文件系统原子写入

所有 wiki 页面的写入采用 **临时文件 + 原子重命名** 策略：

```python
def atomic_write(path: Path, content: str):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)  # 原子操作，不会出现半写文件
```

- 读者永远读到完整内容（要么旧版本，要么新版本）
- 写入过程崩溃不会损坏现有文件（.tmp 残留，health check 定期清理）

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
| `/graph` | 知识图谱 | AntV G6 v5 交互式图谱 |
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

### 知识图谱 (AntV G6 v5)

G6 内置能力与需求映射：

| 需求 | G6 能力 | 配置 |
|------|---------|------|
| 节点按类型着色 | 节点样式映射 | `node.style.fill` 按 type 字段映射色值 |
| 社区分组着色 | Combo 组件 | Louvain 社区 ID → combo 节点，子节点自动嵌套 |
| 边类型区分 | 边样式映射 | 显式链接（实线 #555）vs LLM 推断（虚线 #FF5722） |
| 点击节点查看详情 | 内置交互 | `node:click` 事件 → 右侧详情面板 |
| 筛选面板联动 | 数据过滤 | 前端按类型/社区过滤节点数组 → `graph.changeData()` |
| 缩放/拖拽 | 内置行为 | `drag-canvas` + `zoom-canvas` 默认启用 |
| 小地图导航 | Minimap 插件 | `new Minimap({ size: [150, 100] })` |
| Tooltip 悬停预览 | Tooltip 插件 | `new Tooltip({ getContent: (e) => ... })` |
| 空图谱 | 自定义状态 | `graph.render()` 前判断节点数为 0 → 显示空状态组件 |

G6 离线自托管：`npm install @antv/g6` 后 Vite 打包进 dist/static，无 CDN 依赖。

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
   前端 GET /api/graph/data → 渲染 AntV G6

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
| 图谱渲染 | AntV G6 v5 (离线自托管，MIT 协议) |
| 后端框架 | FastAPI (Python 3.10+) |
| 认证 | JWT (python-jose) |
| LLM 调用 | litellm → DeepSeek v4 flash |
| 图计算 | NetworkX + Louvain |
| 文件转换 | markitdown |
| 数据库 | SQLite（用户/项目/审计日志） |
| 存储 | 文件系统（wiki/raw/graph） |
| 前端部署 | Nginx 静态托管 + 反向代理 |
| 后端部署 | Uvicorn / Gunicorn |

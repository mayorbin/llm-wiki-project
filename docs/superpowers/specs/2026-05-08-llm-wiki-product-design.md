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
├── tasks.db                 # 任务队列持久化（SQLite）
└── users.db                 # 用户 + 项目成员关系（SQLite）
```

项目成员角色：**Owner**（创建者，可删除项目/管理成员/转让所有权）、**Editor**（上传/摄入/管理文件/编辑 wiki 页面）、**Viewer**（只读查询和浏览）。

### 权限矩阵

| 操作 | Owner | Editor | Viewer |
|------|-------|--------|--------|
| **查询知识库** `POST /api/knowledge/query` | ✅ | ✅ | ✅ |
| **浏览 Wiki 页面** `GET /api/knowledge/pages` | ✅ | ✅ | ✅ |
| **查看图谱** `GET /api/graph/data` | ✅ | ✅ | ✅ |
| **查看文件/目录** `GET /api/files` / `dirs` | ✅ | ✅ | ✅ |
| **下载源文件** | ✅ | ✅ | ✅ |
| **上传文件** `POST /api/files/upload` | ✅ | ✅ | ❌ |
| **创建目录** `POST /api/files/dirs` | ✅ | ✅ | ❌ |
| **删除文件** `DELETE /api/files/{id}` | ✅ | ✅ | ❌ |
| **移动文件** `POST /api/files/move` | ✅ | ✅ | ❌ |
| **触发摄入** `POST /api/ingestion/trigger` | ✅ | ✅ | ❌ |
| **重试/回滚摄入** `POST /api/ingestion/retry|rollback` | ✅ | ✅ | ❌ |
| **编辑 Wiki 页面** `PUT /api/knowledge/pages/{path}` | ✅ | ✅ | ❌ |
| **检测变更** `POST /api/files/detect-changes` | ✅ | ✅ | ❌ |
| **触发 Re-Ingest** `POST /api/files/refresh*` | ✅ | ✅ | ❌ |
| **构建图谱** `POST /api/graph/build` | ✅ | ✅ | ❌ |
| **运行 Lint** `POST /api/lint` | ✅ | ✅ | ❌ |
| **存活探针** `GET /api/ping` | ✅（公开） | ✅（公开） | ✅（公开） |
| **就绪探针** `GET /api/health` | ✅（公开） | ✅（公开） | ✅（公开） |
| **项目健康检查** `GET /api/projects/{id}/health` | ✅ | ✅ | ✅ |
| **查看审计日志** `GET /api/audit-log` | ✅ | ✅ | ❌ |
| **修改项目设置** `PATCH /api/projects/{id}/settings` | ✅ | ❌ | ❌ |
| **修改项目信息** `PATCH /api/projects/{id}` | ✅ | ❌ | ❌ |
| **管理成员** `GET|POST|DELETE /api/projects/{id}/members*` | ✅ | ❌ | ❌ |
| **转让所有权** `POST /api/projects/{id}/transfer` | ✅ | ❌ | ❌ |
| **删除项目** `DELETE /api/projects/{id}` | ✅ | ❌ | ❌ |
| **导出备份** `POST /api/backup/export` | ✅ | ✅ | ❌ |
| **导入备份** `POST /api/backup/import` | ✅ | ❌ | ❌ |

### Owner 转让

Owner 离开项目前需转让所有权：

```
POST /api/projects/{id}/transfer
body: { "new_owner_id": "u_xyz" }

前置条件：
- 调用者必须是当前 Owner
- new_owner_id 必须是项目已有成员（Editor 或 Viewer）
- 转让后原 Owner 自动降级为 Editor
```

转让日志：`audit_log: action="owner_transfer", detail={"from":"u_abc","to":"u_xyz"}`

如果 Owner 是最后一个成员且直接注销账号：
- 项目自动归档（`status: archived`），保留数据
- 管理员（全局 admin 角色）可以接管项目或删除

### 用户注销

用户注销不物理删除数据，采用软删除：

```sql
-- users 表
ALTER TABLE users ADD COLUMN deleted_at TEXT;  -- NULL = 活跃，有值 = 已注销
```

注销行为：
- 用户从所有项目的成员列表中移除
- 审计日志中的 `user_id` 和 `username` **保留不变**（溯源需要）
- 注销用户创建的任务（摄入记录）保留，标记 `created_by` 不变
- 注销用户编辑的 wiki 页面保留，编辑历史中的用户信息保留
- 注销用户的所有权项目：如果有其他成员 → 自动转让给加入最早的 Editor；如果无其他成员 → 项目归档
- `GET /api/admin/users` 管理员可查看已注销用户列表（标记 `deleted`）
- 注销用户不可重新登录，`is_active=0` + `deleted_at` 不为空

### 全局 Admin 角色

用户表中 `role = "admin"` 的全局管理员跨项目拥有权限：

| 操作 | 全局 Admin |
|------|-----------|
| 查看任意项目列表 | ✅ |
| 进入任意项目（只读） | ✅ |
| 接管无主项目 | ✅ |
| 创建/禁用/注销用户 | ✅ |
| 查看全平台审计日志 | ✅ |
| 修改全局配置 | ✅ |
| 删除任意项目 | ✅（需二次确认） |

---

## 约束条件

| 维度 | 决策 |
|------|------|
| 部署 | 内网，前后端分离（Nginx + Python 后端） |
| LLM | 内部部署兼容接口（DeepSeek v4 flash / GLM-47 / 其他 OpenAI 兼容模型），不支持外部代理 |
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
│   │   ├── llm_engine.py       # LLM 调用（via litellm，多 provider 支持）
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
│   ├── router/index.ts          # 路由定义 + 导航守卫（项目权限校验）
│   ├── api/                    # 统一请求管理层
│   │   ├── client.ts           # Axios 实例 + 拦截器
│   │   ├── auth.ts             # 认证 API
│   │   ├── files.ts            # 文件管理 API
│   │   ├── projects.ts         # 项目管理 API
│   │   ├── ingestion.ts        # 摄入 API
│   │   ├── knowledge.ts        # 知识查询 API
│   │   ├── graph.ts            # 图谱 API
│   │   └── maintenance.ts      # 备份/健康/审计 API
│   ├── views/
│   │   ├── KnowledgeBaseView.vue   # 知识库主页（源文件+查询子视图）
│   │   ├── GraphView.vue           # 知识图谱
│   │   └── SettingsView.vue        # 设置（备份/日志/LLM 配置）
│   ├── components/
│   │   ├── layout/             # AppShell / Sidebar / ProjectSwitcher
│   │   ├── files/              # DirTree / FileList / UploadDialog
│   │   ├── wiki/               # PageViewer / PageEditor / QueryInput / QueryResult
│   │   ├── graph/              # GraphCanvas / FilterPanel / NodeDetail (G6)
│   │   └── common/             # ConfirmDialog / ProgressBar / EmptyState
│   ├── lib/                    # markdown-it + DOMPurify 封装 / 工具函数
│   ├── composables/            # useAuth / useWiki / useGraph
│   ├── stores/                 # Pinia: auth / project / files / wiki / graph
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
- `POST /api/auth/login` — 登录，返回 access_token + refresh_token
- `POST /api/auth/refresh` — 刷新 access_token（使用 refresh_token）
- `GET /api/auth/me` — 当前用户信息（用户名、角色、所属项目列表、权限）
- `POST /api/auth/register` — 注册（v1 可配置关闭，管理员手动创建账号）
- `GET /api/projects/{id}/members` — 项目成员列表
- `POST /api/projects/{id}/members` — 添加成员（Owner 操作）
- `DELETE /api/projects/{id}/members/{user_id}` — 移除成员
- `POST /api/projects/{id}/transfer` — 转让项目所有权（Owner 操作）

##### Token 设计

```json
// POST /api/auth/login 响应
{
  "access_token": "eyJhbGciOi...",     // JWT，有效期 1 小时
  "refresh_token": "eyJhbGciOi...",    // JWT，有效期 7 天
  "token_type": "bearer",
  "expires_in": 3600
}
```

- `access_token`：短期 JWT，负载 `{ sub: user_id, username, role, iat, exp }`
- `refresh_token`：长期 JWT，负载 `{ sub: user_id, type: "refresh", iat, exp }`，仅用于刷新
- refresh 端点接受 `refresh_token` → 返回新的 `access_token` + `refresh_token`（滚动刷新）
- 刷新时校验 refresh_token 未过期且未列入黑名单（logout 时加入）

##### GET /api/auth/me 响应

```json
{
  "user": {
    "id": "u_abc",
    "username": "zhangsan",
    "display_name": "张三",
    "role": "user",                     // admin | user
    "is_admin": false
  },
  "projects": [
    {
      "id": "proj_1",
      "name": "AI 研究知识库",
      "role": "owner",                  // owner | editor | viewer
      "status": "active"                // active | archived
    },
    {
      "id": "proj_2",
      "name": "竞品分析",
      "role": "editor",
      "status": "active"
    }
  ]
}
```

前端初始化流程：

```
应用启动
  │
  ▼
GET /api/auth/me（一次请求）
  │
  ├─ user → 写入 authStore（username / role / isAdmin）
  ├─ projects → 写入 projectStore（项目列表 + 角色）
  ├─ 有 projects → 恢复 lastVisitedProject（localStorage）或默认进入第一个
  └─ 无 projects → 显示空项目引导页
```

前端在应用初始化时调用 `GET /api/auth/me` 获取用户上下文，写入 Pinia auth store，作为全局导航、权限判断、项目切换的数据源。

#### 项目管理
- `GET /api/projects` — 用户所属项目列表
- `POST /api/projects` — 创建项目
- `GET /api/projects/{id}` — 项目详情
- `PATCH /api/projects/{id}` — 更新项目基本信息（名称、描述）
- `DELETE /api/projects/{id}` — 删除项目

#### 项目设置
- `GET /api/projects/{id}/settings` — 项目完整设置
- `PATCH /api/projects/{id}/settings` — 更新项目设置

##### 设置结构

```json
{
  "project": {
    "name": "AI 研究知识库",
    "description": "追踪 Transformer 系列论文和工程实践",
    "status": "active",           // active | archived
    "created_at": "2026-05-01T10:00:00+08:00",
    "archived_at": null
  },
  "llm": {
    "provider": "deepseek",        // deepseek | glm | openai_compatible
    "model": "deepseek-v4-flash",  // 模型标识名（litellm 格式，如 deepseek/deepseek-v4-flash）
    "api_base": "http://10.0.1.5:8000/v1",  // OpenAI 兼容 API 地址
    "api_key": null,               // null 表示继承全局配置
    "temperature": 0.3,            // 0.0–2.0，默认 0.3（知识提取需要确定性）
    "max_tokens": 8192,            // 默认 8192，大文件摄入可调大
    "timeout": 120,                // 秒，默认 120
    "retry": 3,                    // 最大重试次数，默认 3
    "system_prompt_append": ""     // 项目级 System Prompt 追加（可选）
  },
  "features": {
    "auto_ingest_on_upload": true, // 上传后自动触发摄入
    "auto_graph_rebuild": true,    // 摄入后自动重建图谱
    "registration_open": false,    // 是否允许自由注册加入项目
    "snapshot_retention_days": 30  // 快照保留天数
  }
}
```

##### 设置变更行为

| 设置 | 变更后行为 |
|------|-----------|
| `llm.temperature` | 下次摄入生效，不影响进行中任务 |
| `llm.max_tokens` | 下次摄入生效 |
| `llm.system_prompt_append` | 下次摄入生效，追加在标准 Prompt 末尾 |
| `features.auto_ingest_on_upload` | 即时生效 |
| `features.auto_graph_rebuild` | 即时生效（关闭后摄入跳过 Step 5，status 标记 completed_without_graph） |
| `features.registration_open` | 即时生效 |
| `status: active → archived` | 归档项目：只读访问，拒绝摄入和编辑，隐藏于默认项目列表 |
| `status: archived → active` | 重新激活：恢复完全功能 |

##### 项目归档

归档后的行为限制：

| 操作 | archived 状态 |
|------|--------------|
| 查询知识库 | ✅ 允许 |
| 浏览 wiki 页面 | ✅ 允许 |
| 查看图谱 | ✅ 允许 |
| 上传文件 | ❌ 返回 403 "项目已归档" |
| 触发摄入 | ❌ 返回 403 |
| 编辑 wiki 页面 | ❌ 返回 403 |
| 删除文件 | ❌ 返回 403 |
| 导出备份 | ✅ 允许 |
| 删除项目 | ✅ Owner 允许 |
| 归档后首页列表 | 默认隐藏，勾选"显示已归档"可见 |

#### 文件与目录管理
- `GET /api/files/dirs` — 浏览 raw/ 目录树
- `POST /api/files/dirs` — 创建子目录（最多 3 层）
- `DELETE /api/files/dirs` — 删除空目录
- `POST /api/files/upload` — 上传文件到指定子目录
- `POST /api/files/upload-batch` — 批量上传（多文件并发上传，每个文件独立 Task）
- `GET /api/files` — 文件列表（支持 dir/搜索/分页）
- `DELETE /api/files/{id}` — 删除文件（级联清理 wiki 页）
- `POST /api/files/move` — 移动文件到其他子目录

#### 文件上传安全

##### 文件类型白名单

```python
ALLOWED_EXTENSIONS = {
    ".md", ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    ".rst", ".rtf", ".epub", ".ipynb",
    ".yaml", ".yml", ".tsv",
    ".wav", ".mp3",
}

def validate_extension(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    # 双重扩展名检测：阻止 attack.pdf.exe 伪装
    stem = Path(filename).stem
    if Path(stem).suffix.lower() in ALLOWED_EXTENSIONS:
        return False
    if suffix not in ALLOWED_EXTENSIONS:
        return False
    # 无扩展名文件拒绝
    if suffix == "":
        return False
    return True
```

校验点：
- 仅允许白名单内扩展名，其余一律拒绝
- 检测双重扩展名（`report.pdf.exe` → 拒绝，stem `report.pdf` 的扩展名在白名单内）
- 空扩展名拒绝
- 校验发生在文件保存之前，恶意文件不落盘

##### 文件大小限制

| 文件类型 | 上限 | 理由 |
|----------|------|------|
| `.pdf` `.epub` | 100 MB | 学术论文、电子书体积较大 |
| `.wav` `.mp3` | 200 MB | 音频转录场景 |
| `.pptx` `.xlsx` `.docx` | 50 MB | Office 文档 |
| 其他（`.md` `.txt` `.json` 等） | 10 MB | 纯文本不应过大 |

- 前端和后端**双重校验**，前端拦截减少无效上传，后端是安全边界
- 超过上限返回 413 Payload Too Large
- 上传过程中流式读取，不将整个文件读入内存

##### 路径穿越防护

```python
import os
from pathlib import Path

RAW_BASE = Path("/data/projects/{project_id}/raw").resolve()

def safe_subdir(raw_base: Path, subdir: str) -> Path:
    """将用户输入的 subdir 规范化为安全的绝对路径，杜绝 ../ 穿越。"""
    # 1. 移除空路径段和首尾空白
    cleaned = "/".join(s for s in subdir.strip("/").split("/") if s and s not in (".", ".."))
    # 2. 拼接后 resolve 消除 ..
    candidate = (raw_base / cleaned).resolve()
    # 3. 必须在 raw_base 之下
    if not str(candidate).startswith(str(raw_base)):
        raise ValueError(f"路径穿越检测: {subdir}")
    return candidate
```

- 所有文件操作（上传/删除/移动/列表）的路径参数都经过此函数规范化
- 任何 `../` 或 `..\..` 尝试直接抛错 400，不记录、不处理
- subdir 深度限制为最多 3 层（`论文/2025/12月/`），超过拒绝

##### 文件名规范化

```python
import unicodedata
import re

MAX_FILENAME_LENGTH = 200  # 字节（UTF-8 编码后）

def sanitize_filename(filename: str) -> str:
    # 1. Unicode 规范化：全角→半角，兼容等价→标准形式
    filename = unicodedata.normalize("NFKC", filename)
    # 2. 剥离路径分隔符（恶意文件名可能含 / 或 \）
    filename = filename.replace("/", "_").replace("\\", "_")
    # 3. 移除不可打印字符（仅保留空格 + 可见字符）
    filename = re.sub(r"[^\x20-\x7E一-鿿　-〿＀-￯]", "_", filename)
    # 4. 去首尾空格和点（Windows 不允许尾随点/空格）
    filename = filename.strip(" .")
    # 5. 长度截断：保留扩展名，截中间
    if len(filename.encode("utf-8")) > MAX_FILENAME_LENGTH:
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        # 保留前 60% + 后 30% + 扩展名
        split = int(MAX_FILENAME_LENGTH * 0.6)
        stem = stem.encode("utf-8")[:split].decode("utf-8", errors="ignore")
        filename = stem + "..." + suffix
    # 6. 空文件名兜底
    if not filename or filename.startswith("."):
        filename = f"unnamed_{uuid4().hex[:8]}{Path(filename).suffix}"
    return filename
```

##### 上传安全总览

| 风险 | 措施 | 拒绝方式 |
|------|------|---------|
| 恶意扩展名 | 白名单 + 双重扩展名检测 | 400 Bad Request |
| 文件过大 | 前后端双重大小校验 | 413 Payload Too Large |
| 路径穿越 | `resolve()` + 前缀校验 | 400 Bad Request |
| 特殊字符文件名 | Unicode 规范化 + 正则过滤 | 静默替换为 `_` |
| 空文件名/隐藏文件 | 检查空名和 `.` 开头 | 自动生成 `unnamed_xxx` |
| 文件名过长 | UTF-8 字节截断 | 截断保留扩展名 |
| 并发上传同一文件 | 目录级锁（见并发安全章节） | 排队等待 |
| 大文件内存溢出 | 流式写入磁盘（`shutil.copyfileobj`） | — |

#### 摄入
- `POST /api/ingestion/trigger` — 触发摄入（单文件、多 file_ids 共享上下文、或目录路径）
- `POST /api/ingestion/retry/{task_id}` — 重试失败的摄入（复用已上传文件）
- `GET /api/ingestion/status/{task_id}` — 单个摄入进度（5 步分阶段，失败时含 error 详情和建议）
- `POST /api/ingestion/statuses` — 批量查询摄入进度 `{ "task_ids": ["t1","t2"] }`
- `GET /api/ingestion/history` — 历史记录（含快照状态）
- `POST /api/ingestion/rollback/{task_id}` — 回滚摄入（从快照恢复）

#### 知识查询
- `POST /api/knowledge/query` — LLM 综合回答，附 `[[wikilink]]` 引用
- `GET /api/knowledge/pages` — Wiki 页面列表/树
- `GET /api/knowledge/pages/{path}` — 读取页面 markdown（含 frontmatter 元信息）
- `PUT /api/knowledge/pages/{path}` — 更新页面内容（手动修正）
- `GET /api/knowledge/pages/{path}/history` — 页面编辑历史

#### 图谱
- `GET /api/graph/data` — 节点 + 边 JSON
- `POST /api/graph/build` — 触发构建
- `GET /api/graph/stats` — 统计信息

#### 全局管理（仅 Admin）

- `GET /api/admin/users` — 用户列表（含已注销）
- `POST /api/admin/users` — 创建用户
- `PATCH /api/admin/users/{id}` — 修改用户（禁用/启用/重置角色）
- `DELETE /api/admin/users/{id}` — 注销用户（软删除）
- `GET /api/admin/projects` — 全平台项目列表
- `POST /api/admin/projects/{id}/takeover` — 接管无主项目
- `GET /api/admin/audit-log` — 全平台审计日志

#### 公共（无需认证）

- `GET /api/ping` — 存活探针（K8s liveness probe / LB health check）
- `GET /api/health` — 就绪探针（含依赖检查，K8s readiness probe）

##### 端点语义

```json
// GET /api/ping — 仅验证进程存活，零依赖调用，<1ms
// HTTP 200
{ "status": "ok", "version": "0.1.0", "uptime_seconds": 123456 }

// GET /api/health — 验证进程 + 关键依赖可用
// HTTP 200 或 503
{
  "status": "healthy",           // healthy | degraded | unhealthy
  "version": "0.1.0",
  "uptime_seconds": 123456,
  "checks": {
    "database": "ok",            // ok | error
    "file_system": "ok",         // data/ 目录可读写
    "llm_api": "ok",             // LLM 接口可达（可选，由 ?deep=true 触发）
    "disk_usage": "42%"          // 磁盘使用率
  }
}
```

| 端点 | 认证 | 用途 | 检查深度 |
|------|------|------|---------|
| `GET /api/ping` | ❌ 无需 | Liveness probe | 仅进程存活 |
| `GET /api/health` | ❌ 无需 | Readiness probe | 进程 + DB + 文件系统 |
| `GET /api/health?deep=true` | ❌ 无需 | 深度健康检查 | 含 LLM 连通性验证（较慢） |
| `GET /api/projects/{id}/health` | ✅ 需认证 | 项目级结构检查 | wiki 页面完整性（empty/stub/index sync） |

##### Nginx 配置

```nginx
# 健康检查请求不记录 access log，也不代理到后端时保持轻量
location = /api/ping {
    proxy_pass http://backend:8000;
    access_log off;
}
```

##### K8s Probe 配置

```yaml
livenessProbe:
  httpGet:
    path: /api/ping
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /api/health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 15
```

#### 维护（Owner + Editor）
- `POST /api/backup/export` — 导出 tar.gz
- `POST /api/backup/import` — 恢复备份（Owner only）
- `POST /api/lint` — 语义质量检查
- `GET /api/audit-log` — 项目审计日志查询（支持筛选/分页/导出 CSV）

### 统一分页规范

所有列表类 API 使用统一的分页参数和响应格式。

#### 分页策略

| 场景 | 策略 | 理由 |
|------|------|------|
| 文件列表、Wiki 页面树、用户列表 | **offset/limit** | 数据量可控，支持随机跳页 |
| 审计日志、摄入历史、编辑历史 | **cursor-based + 上一页/下一页** | 数据持续追加，offset 在新数据插入时会导致重复或遗漏 |
| 导出类接口 | **不分页** | 全量导出 |

#### 请求参数

```typescript
// offset/limit（默认策略）
interface PageQuery {
  offset?: number    // 偏移量，默认 0，最小 0
  limit?: number     // 每页条数，默认 50，最小 1，最大 200
  order_by?: string  // 排序字段
  order_dir?: "asc" | "desc"  // 排序方向，默认 desc
}

// cursor-based（审计日志等持续追加场景）
interface CursorQuery {
  cursor?: string    // 游标（上一页返回的 next_cursor），首页不传
  direction?: "next" | "prev"  // 翻页方向，默认 next
  limit?: number     // 每页条数，默认 50，最小 1，最大 200
}
```

#### 响应格式

```json
// offset/limit 响应
{
  "data": [...],
  "pagination": {
    "strategy": "offset",
    "offset": 0,
    "limit": 50,
    "total": 342,
    "has_more": true
  }
}

// cursor-based 响应
{
  "data": [...],
  "pagination": {
    "strategy": "cursor",
    "limit": 50,
    "has_more": true,
    "next_cursor": "eyJ0cyI6IjIwMjYtMDUtMDlUMTQ6MzA6MDBaIiwiaWQiOjE1MH0=",
    "prev_cursor": null
  }
}
```

`next_cursor` 和 `prev_cursor` 是 base64 编码的 opaque 字符串，客户端不应解析其内容。

#### 默认值

| 参数 | 默认值 | 允许范围 |
|------|--------|---------|
| `limit` | 50 | 1–200 |
| `offset` | 0 | ≥0 |
| `order_dir` | `desc` | asc / desc |

#### 各端点分页策略

| 端点 | 策略 | 默认排序 |
|------|------|---------|
| `GET /api/files` | offset | `created_at DESC` |
| `GET /api/knowledge/pages` | offset | `title ASC` |
| `GET /api/projects/{id}/members` | offset | `joined_at ASC` |
| `GET /api/audit-log` | cursor | `timestamp DESC` |
| `GET /api/ingestion/history` | cursor | `created_at DESC` |
| `GET /api/knowledge/pages/{path}/history` | cursor | `timestamp DESC` |
| `GET /api/files/dirs` | 不分页 | —（目录树全量返回） |

#### 前端约定

- 列表页默认每页 50 条
- 文件列表提供 20/50/100 切换
- 搜索时重置 offset 到 0
- cursor-based 的列表显示「上一页」「下一页」按钮，不显示页码

### Service 层

| Service | 职责 | 依赖引擎 |
|---------|------|----------|
| AuthService | 注册、登录、JWT、项目成员管理 | — |
| FileService | 上传/目录管理/删除/移动，编排文件→wiki→图谱联动 | ConvertEngine, IngestService, GraphService |
| IngestService | 摄入流程编排：读文件→调 LLM→写页面→更新索引→验证 | WikiEngine, LLMEngine |
| QueryService | 查 index→找相关页→LLM 综合回答→可选保存 | WikiEngine, LLMEngine |
| PageService | Wiki 页面手动编辑、编辑快照、历史查询、wikilink 自动修正 | WikiEngine, GraphService |
| GraphService | 双 Pass 构建 + Louvain + SHA256 缓存 | WikiEngine, LLMEngine, GraphEngine |
| LintService | Orphan/Broken/矛盾检测 | WikiEngine, LLMEngine |
| BackupService | 全量导出/恢复/校验 | WikiEngine |

### Engine 层

| Engine | 职责 |
|--------|------|
| WikiEngine | 页面 CRUD（YAML 前页+markdown）、wikilink 提取/验证、index/log 维护、SHA256，所有写操作加锁 |
| LLMEngine | litellm 通用 LLM 调用（OpenAI 兼容协议）、Prompt 模板、JSON 解析、重试+超时 |
| GraphEngine | NetworkX 图构建、Louvain 社区检测、输出 G6 兼容 JSON、SHA256 缓存 |
| ConvertEngine | 多后端 PDF 转换 + markitdown 通用转换 |
| LockManager | 项目级 + 文件级读写锁管理，确保并发安全 |

### LLMEngine — 多 Provider 通用设计

LLMEngine 基于 litellm 的统一接口，所有兼容 OpenAI Chat Completions 协议的模型通过配置切换，无需改代码。

#### Provider 配置模板

```yaml
# DeepSeek v4 flash（默认）
llm:
  provider: "openai_compatible"
  model: "deepseek/deepseek-v4-flash"
  api_base: "http://your-server:8000/v1"
  api_key: "sk-xxx"

# GLM-47
llm:
  provider: "openai_compatible"
  model: "glm/glm-47"
  api_base: "http://your-glm-server:8000/v1"
  api_key: "sk-xxx"
  extra_headers:
    X-Custom-Auth: "optional-header"

# 其他任意 OpenAI 兼容接口（vLLM / Ollama / text-generation-webui）
llm:
  provider: "openai_compatible"
  model: "openai/meta-llama-3.1-70b"  # 任意 litellm 支持的 model id
  api_base: "http://your-vllm-server:8080/v1"
  api_key: "not-needed"
```

#### 切换方式

- **全局切换**：修改 `config.yaml` → 重启服务，所有项目默认使用新模型
- **单项目覆盖**：在项目设置中覆盖 `llm.model` / `llm.api_base` / `llm.api_key`，仅该项目生效，不重启服务
- **运行中生效**：项目设置变更即时生效（下次摄入/查询使用新配置），不影响进行中的任务

#### 模型要求

任何用作 Wiki 后端的 LLM 需要满足：

| 能力 | 要求 | 说明 |
|------|------|------|
| Chat Completions API | OpenAI 兼容格式 | litellm 统一入口 |
| 上下文长度 | ≥ 32K tokens | 大文件摄入需要长上下文 |
| JSON 输出 | 可靠的 JSON 格式遵循 | 摄入 Prompt 要求返回结构化 JSON |
| 中文支持 | 良好 | Wiki 页面中英文混合 |
| 推理能力 | 中上 | 需要从文档中准确提取实体、概念和关系 |

#### 健康检查中的模型验证

```python
# manage.py check 或 health.py 中
def verify_llm_connection(settings) -> bool:
    try:
        response = litellm.completion(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "Hello, respond with just 'OK'."}],
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
            max_tokens=5,
            timeout=10,
        )
        return response.choices[0].message.content.strip() == "OK"
    except Exception as e:
        logger.error(f"LLM 连接验证失败: {e}")
        return False
```

### ConvertEngine — 多后端文件转换

不同文件类型和排版复杂度需要不同的转换后端。ConvertEngine 按优先级和文件类型自动选择最佳后端，支持 fallback。

#### 后端矩阵

| 后端 | 适用场景 | 输出质量 | 速度 | 安装 | 可选 |
|------|---------|---------|------|------|------|
| **markitdown** | 通用 MS Office、HTML、TXT、CSV | 良好 | 快 | `pip install markitdown[all]` | ❌ 必装 |
| **pymupdf4llm** | 通用 PDF（含中文）| 良好 | 快 | `pip install pymupdf4llm` | ✅ 可选 |
| **marker-pdf** | 复杂排版 PDF（多栏/表格/公式） | 优秀 | 慢（需 GPU） | `pip install marker-pdf` | ✅ 可选 |
| **arxiv2markdown** | arXiv 论文专用（LaTeX 源码转换） | 最优（对 arXiv 论文） | 中 | `pip install arxiv2markdown` | ✅ 可选 |

#### 文件类型路由

```
用户上传文件
    │
    ▼
按扩展名分流
    │
    ├─ .md — 跳过转换，直接摄入
    │
    ├─ .docx / .pptx / .xlsx / .html / .txt / .csv / .json
    │      → markitdown（唯一选择，必装）
    │
    ├─ .pdf（非 arXiv 来源）
    │      → 按优先级尝试：
    │        1. marker-pdf（如果已安装且文件页数 > 20 或有表格/多栏检测）
    │        2. pymupdf4llm（如果已安装）
    │        3. markitdown（通用 fallback）
    │
    └─ .pdf（arXiv 来源，文件名如 2401.12345.pdf）
           → 按优先级尝试：
             1. arxiv2markdown（LaTeX 源码 → Markdown，质量最优）
             2. marker-pdf（如果已安装）
             3. pymupdf4llm（如果已安装）
             4. markitdown（通用 fallback）
```

#### 后端检测与 Fallback

```python
class ConvertEngine:
    def __init__(self):
        self._backends = self._detect_backends()

    def _detect_backends(self) -> dict:
        backends = {"markitdown": self._try_import("markitdown", "MarkItDown")}

        for name, module, cls in [
            ("pymupdf4llm", "pymupdf4llm", None),
            ("marker", "marker", "convert_single_pdf"),
            ("arxiv2md", "arxiv2markdown", "Arxiv2Markdown"),
        ]:
            try:
                backends[name] = self._try_import(module, cls)
            except ImportError:
                backends[name] = None
        return backends

    def pdf_convert(self, file_path: Path, source_hint: str = "auto") -> ConvertResult:
        if source_hint == "arxiv" and self._backends["arxiv2md"]:
            return self._arxiv_convert(file_path)

        # 复杂排版检测
        need_high_quality = self._detect_complex_layout(file_path)
        #   - page_count > 20
        #   - 包含多栏排版（标记检测）
        #   - 包含表格（表格线检测）
        #   - 中文内容占比 > 30% → marker-pdf 对中文更优

        backends_priority = (
            ["marker", "pymupdf4llm", "markitdown"]
            if need_high_quality
            else ["pymupdf4llm", "markitdown"]
        )

        for backend_name in backends_priority:
            if self._backends.get(backend_name):
                result = self._try_convert(backend_name, file_path)
                if result.success and result.text_length > 0:
                    return result

        raise ConversionError("所有 PDF 转换后端均失败")
```

#### 质量评估

转换完成后对输出做质量检查，不达标的输出自动换后端重试：

```python
def _quality_check(self, text: str, original: Path) -> tuple[bool, str]:
    # 1. 输出太短（<100 字符且原文件 >1MB）→ 可能转换失败
    if len(text) < 100 and os.path.getsize(original) > 1024 * 1024:
        return False, "output_too_short"

    # 2. 乱码检测（高比例不可打印字符）
    printable_ratio = sum(c.isprintable() or c in "\n\r\t" for c in text) / len(text)
    if printable_ratio < 0.7:
        return False, "garbled_output"

    # 3. 中文文档输出无中文字符 → 编码问题
    if _has_chinese_filename(original) and not _has_chinese_chars(text):
        return False, "chinese_missing"

    # 4. 全部是图片引用（无实质文本）
    text_without_images = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    if len(text_without_images.strip()) < 200:
        return False, "image_only"

    return True, "ok"
```

#### 转换 API

转换可单独调用（不上传不摄入），方便用户预览转换结果：

```
POST /api/convert              # 上传文件 → 返回 Markdown 预览（不保存、不摄入）
POST /api/convert/preview      # 对比多个后端的转换结果
```

#### 转换统计

```python
# GET /api/convert/stats
{
  "total_conversions": 1523,
  "by_backend": {
    "pymupdf4llm": 823,
    "markitdown": 450,
    "marker": 180,
    "arxiv2markdown": 70
  },
  "by_format": { "pdf": 1200, "docx": 200, "pptx": 80, "html": 43 },
  "fallback_rate": 0.08,      // 8% 的任务触发了 fallback
  "avg_duration_ms": 3200
}
```

#### 安装指引

系统部署时，管理员按需安装可选后端：

```bash
# 必装
pip install markitdown[all]

# 推荐安装：通用 PDF（含中文）
pip install pymupdf4llm

# 按需安装：复杂排版 PDF
pip install marker-pdf

# 按需安装：arXiv 论文
pip install arxiv2markdown
```

前端设置页显示当前已安装的后端和版本：「已安装后端：markitdown ✅ · pymupdf4llm ✅ · marker-pdf ❌ · arxiv2markdown ❌」

---

## 文件→Wiki→图谱自动联动

所有文件操作自动级联更新，保证三者一致：

### 上传/覆盖

```
上传文件 → ConvertEngine 转换
         → 检测是否已存在同名文件
           ├─ 不存在 → 新建摄入
           │           → IngestService 摄入
           │           → 写入 wiki 页面
           │           → 更新 index.md / log.md
           │           → GraphService 重建图谱
           │
           └─ 已存在（覆盖上传） → 对比 SHA256
               ├─ 内容相同 → 跳过摄入（返回 200 "未变更"）
               └─ 内容不同 → 清理旧 wiki → 重新摄入 → 重建图谱
```

覆盖操作用户确认：
- 上传 API 检测到同名文件时，返回 `{"exists": true, "current_hash": "xxx", "last_ingest": "2026-05-09"}`，由前端二次确认
- 用户确认后才执行覆盖，避免误覆盖

### 批量上传与 auto_ingest

```
POST /api/files/upload-batch
  files: [a.pdf, b.pdf, c.pdf]     ← 前端并发上传
  project_id: xxx
  subdir: "论文"
```

当 `auto_ingest_on_upload: true` 时，批量上传的行为：

| 行为 | 决策 | 理由 |
|------|------|------|
| Task 粒度 | **每个文件一个独立 Task** | 独立追踪进度、独立重试、独立回滚 |
| 排队顺序 | 按上传完成顺序排队 | 先上传完成的先摄入，不按文件名排序 |
| 并发摄入 | 同一项目仅跑 1 个摄入 | 项目写锁保证串行，其余 Task 排队 |
| 前端反馈 | 每个文件独立显示摄入状态 | 文件列表行内状态标签实时更新 |

```json
// POST /api/files/upload-batch 响应
{
  "uploaded": 3,
  "failed": 0,
  "tasks": [
    {"file_id": "f_1", "filename": "a.pdf", "task_id": "t_01", "status": "queued"},
    {"file_id": "f_2", "filename": "b.pdf", "task_id": "t_02", "status": "queued"},
    {"file_id": "f_3", "filename": "c.pdf", "task_id": "t_03", "status": "queued"}
  ]
}
```

#### 批量摄入（共享上下文）

如果用户希望多个文件在 **同一个 LLM 调用中摄入**（LLM 同时看到所有文件，提取跨文件的关联），使用独立端点：

```
POST /api/ingestion/trigger
body: {
  "project_id": "xxx",
  "file_ids": ["f_1", "f_2", "f_3"]   // 指定多个文件，合并为一次摄入
}
```

此时创建一个 `action: "ingest"` 的 Task，`file_paths` 包含多个文件。LLM Prompt 中同时附上所有文件内容，一次提取所有知识并建立跨文件关联。

| 方式 | Task 粒度 | LLM 视角 | 适用场景 |
|------|----------|---------|---------|
| 批量上传 + auto_ingest | 每文件 1 个 Task | 每个文件独立摄入 | 文件内容独立（不同主题） |
| `POST /api/ingestion/trigger` 多 file_ids | 1 个 Task 含多文件 | LLM 同时看到所有文件 | 关联文件（同名文档的中英文版、系列报告） |

两种方式共享同一任务队列和项目写锁，不因粒度不同而有特殊行为。

### Re-Ingest（文件外部变更检测）

用户可能通过文件系统直接替换 `raw/` 中的文件（rsync、脚本同步、手动复制等），前端不知道。需要主动检测变更并重新摄入。

#### 变更检测

每次触发 refresh / re-ingest 时，对比文件的 `mtime` + `SHA256` 与上次摄入时记录的值：

```python
class FileService:
    def detect_changes(self, project_id: str) -> list[ChangeRecord]:
        changed = []
        for source_file in self.list_source_files(project_id):
            current_hash = sha256(source_file.path)
            last_ingest = self.get_last_ingest_record(source_file.id)

            if last_ingest is None:
                # 未摄入过的新文件
                changed.append(ChangeRecord(
                    file=source_file,
                    status="new",
                    action="ingest",
                ))
            elif current_hash != last_ingest.source_hash:
                # 内容已变更
                changed.append(ChangeRecord(
                    file=source_file,
                    status="modified",
                    old_hash=last_ingest.source_hash,
                    new_hash=current_hash,
                    action="re_ingest",
                ))
            # 内容未变，跳过
        return changed
```

#### API

```
POST /api/files/detect-changes?project_id=xxx
  → 扫描整个 raw/，返回变更文件列表

{
  "total_files": 45,
  "changed": [
    {"file_id": "f_1", "path": "raw/论文/attention.pdf", "status": "modified", "action": "re_ingest"},
    {"file_id": "f_3", "path": "raw/会议记录/new-meeting.docx", "status": "new", "action": "ingest"},
  ],
  "unchanged": 43
}
```

```
POST /api/files/refresh
  body: { "project_id": "xxx", "file_ids": ["f_1", "f_2", ...] }
  → 对指定文件列表执行 re-ingest
  → 返回 task_id 列表（每个文件一个任务，排队执行）
```

```
POST /api/files/refresh-all?project_id=xxx
  → 自动检测全项目变更 → 对所有变更文件执行 re-ingest
  → 返回总结: { "new": 2, "modified": 3, "skipped": 40, "task_ids": [...] }
```

#### 自动检测触发时机

| 触发方式 | 说明 |
|---------|------|
| **手动触发** | 用户在文件管理页点击「检测变更」按钮，预览变更列表，勾选确认后执行 |
| **定期检测** | 项目设置中可配置 cron 表达式（如每天凌晨 3 点），自动检测并 re-ingest |
| **Webhook** | 外部系统通过 `POST /api/files/refresh-all` 主动触发（如 rsync 脚本末尾调用） |
| **上传时关联检测** | 用户通过网页上传文件时，不触发全量检测，仅对本次上传做覆盖判断 |

#### 与摄入任务队列的关系

- re-ingest 复用相同的摄入任务队列和锁机制
- re-ingest 文件与普通摄入任务无区别，排队执行
- 如果 re-ingest 时上一个摄入正在运行，变更文件加入排队（不会冲突，队列保证顺序）
- re-ingest 同样受项目写锁保护

#### 前端 UI

文件管理页顶部工具栏增加：

```
[📤 上传文件]  [📤 批量上传]  [🔄 检测变更]  [⚙️ 自动检测: 每天 03:00 ▼]
```

点击「检测变更」→ 弹出变更预览对话框：

```
┌──────────────────────────────────────────────────┐
│  检测到 3 个文件变更                               │
│                                                  │
│  📄 论文/attention.pdf                           │
│     修改于 2026-05-09 16:30                       │
│     上次摄入: 2026-05-08 14:30 (SHA256 已变更)     │
│     ☑ 重新摄入                                   │
│                                                  │
│  📄 技术文档/api-design.md                        │
│     新增文件，从未摄入                             │
│     ☑ 摄入                                       │
│                                                  │
│  📄 会议记录/q1-review.docx                       │
│     mtime 变更但内容未变 (SHA256 相同)              │
│     ☐ 跳过                                       │
│                                                  │
│  [确认执行]  [取消]                                │
└──────────────────────────────────────────────────┘
```

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

### Wiki 页面版本历史与回滚

摄入成功但输出质量差（LLM 生成内容不当、格式错误、遗漏关键信息）是常见场景。提供轻量级快照机制，不引入 Git 等外部依赖。

#### 快照存储

```
wiki/.history/
├── {task_id-1}/                # 每次摄入一个快照目录
│   ├── manifest.json           # 快照元信息
│   ├── sources/
│   │   └── attention-paper.md  # 被修改页面的副本
│   ├── entities/
│   │   └── Self-Attention.md
│   └── concepts/
│       └── Transformer.md
├── {task_id-2}/
│   └── ...
└── .retention                  # 保留策略配置
```

`manifest.json`：
```json
{
  "task_id": "uuid",
  "timestamp": "2026-05-09T14:30:00+08:00",
  "action": "ingest",
  "user_id": "u_xxx",
  "username": "张三",
  "source_file": "raw/论文/attention.pdf",
  "changed_pages": [
    {"path": "sources/attention-paper.md", "type": "created"},
    {"path": "entities/Self-Attention.md", "type": "updated"},
    {"path": "concepts/Transformer.md", "type": "updated"},
    {"path": "index.md", "type": "updated"},
    {"path": "overview.md", "type": "updated"},
    {"path": "log.md", "type": "updated"}
  ],
  "total_pages": 6
}
```

#### 工作流程

```
摄入开始
    │
    ▼
扫描即将被修改的页面列表（新旧 entity/concept/source + index/log/overview）
    │
    ▼
将当前版本复制到 wiki/.history/{task_id}/
    │
    ▼
执行摄入（写入新页面内容）
    │
    ├─ 摄入成功 → 标记快照 complete，保留 N 天
    │
    └─ 摄入失败 → 从快照恢复原始内容 → 删除快照目录
```

#### 回滚 API

```
POST /api/ingestion/rollback/{task_id}
```

执行流程：
1. 校验 task_id 对应的快照存在且未被更晚的操作覆盖
2. 将快照中的文件逐份复制回 wiki/ 对应位置（原子写入）
3. 清理本次摄入创建的新文件（快照中不存在的页面）
4. 追加回滚日志到 wiki/log.md
5. 触发图谱重建

```python
def rollback_ingestion(project_id: str, task_id: str) -> RollbackResult:
    snapshot_dir = get_snapshot_dir(project_id, task_id)
    if not snapshot_dir.exists():
        raise SnapshotNotFound(task_id)

    manifest = json.loads((snapshot_dir / "manifest.json").read_text())

    # 1. 从快照恢复被修改的页面
    for page in manifest["changed_pages"]:
        snapshot_file = snapshot_dir / page["path"]
        target = WIKI_DIR / page["path"]
        if page["type"] == "created":
            target.unlink(missing_ok=True)  # 新创建的页面直接删除
        elif snapshot_file.exists():
            atomic_write(target, snapshot_file.read_text())  # 还原

    # 2. 清理残留（快照后新产生的页面）
    snapshot_paths = {snapshot_dir / p["path"] for p in manifest["changed_pages"]}
    # ... 删除不在快照中的关联页面

    # 3. 日志
    append_log(f"## [{today}] rollback | task={task_id} | 回滚了 {len(manifest['changed_pages'])} 个页面")

    # 4. 重建图谱
    graph_service.rebuild(project_id)

    return RollbackResult(restored=len(manifest["changed_pages"]))
```

#### 保留策略

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 快照保留天数 | 30 天 | 超过的自动清理 |
| 每项目最大快照数 | 50 | 触发清理最旧的 |
| 清理时机 | health check 中执行 | 每次健康检查自动清理过期快照 |
| 备份行为 | 随备份包导出 | 恢复备份时历史快照一并恢复 |

#### 与并发锁的关系

- 回滚操作持有项目级写锁（与摄入相同级别）
- 回滚等待当前摄入完成，或当前摄入等待回滚完成
- 正在回滚时，新的摄入请求返回 423 Locked

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

使用 `filelock` 库（跨平台文件锁，基于 `fcntl`/`msvcrt`），无额外中间件依赖。所有锁文件存放在共享目录 `data/.locks/`，Gunicorn 多 worker 和独立进程共享同一套锁。

```python
from filelock import FileLock, Timeout as LockTimeout
from pathlib import Path

class LockManager:
    def __init__(self, data_dir: Path):
        self.lock_dir = data_dir / ".locks"
        self.lock_dir.mkdir(exist_ok=True)

    def _lock_path(self, scope: str, identifier: str) -> Path:
        # 锁文件路径：data/.locks/{scope}/{identifier}.lock
        return self.lock_dir / scope / f"{identifier}.lock"

    def acquire(self, scope: str, identifier: str,
                timeout: float = 30, mode: str = "exclusive") -> FileLock:
        """获取锁，支持超时和死锁恢复。"""
        lock_path = self._lock_path(scope, identifier)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(lock_path), timeout=timeout)

        try:
            lock.acquire(timeout=timeout)
        except LockTimeout:
            # 死锁检测：检查是不是上一个持有者已经死了
            if _is_stale_lock(lock_path, timeout_seconds=timeout):
                _break_stale_lock(lock_path)
                lock.acquire(timeout=5)  # 短超时重试
            else:
                raise LockBusyError(
                    f"锁 {scope}/{identifier} 被其他进程持有，超时 {timeout}s"
                ) from None

        # 记录持有者信息（用于死锁诊断）
        _write_lock_owner_info(lock_path)
        return lock

    def release(self, lock: FileLock):
        lock.release()
```

#### Gunicorn 多 Worker 与锁的交互

```
Gunicorn (workers=4)
│
├── Worker 1 ────┐
├── Worker 2 ────┤  所有 worker 共享 data/.locks/ 目录
├── Worker 3 ────┤  filelock 基于内核级 fcntl，跨进程有效
├── Worker 4 ────┘
│
└── 任何一个 worker 持有锁时，其他 worker 的 acquire() 阻塞等待
```

关键约束：
- **锁文件必须在共享文件系统上**。`data/.locks/` 位于项目数据目录，所有 worker 可访问
- **worker 数量建议**：`workers = CPU 核数`。锁等待时 worker 被阻塞，过多 worker 只会排队空耗资源。建议 2-4 个 worker
- **多 worker 场景的锁竞争**：摄入操作持有项目写锁期间，该项目的其他写请求在任何 worker 上都会被阻塞，读取操作不受影响（不获取锁）
- **进程崩溃时的锁释放**：`filelock` 基于内核 `fcntl` 锁，进程退出时内核自动释放。即使 worker 被 SIGKILL 杀死，锁也不会残留

#### 死锁检测与恢复

```python
# 锁持有信息文件：data/.locks/{scope}/{identifier}.info
import json, os, time

def _write_lock_owner_info(lock_path: Path):
    info_path = lock_path.with_suffix(".info")
    info_path.write_text(json.dumps({
        "pid": os.getpid(),
        "worker_id": os.getenv("GUNICORN_WORKER_ID", "unknown"),
        "acquired_at": time.time(),
        "hostname": os.uname().nodename,
    }))

def _is_stale_lock(lock_path: Path, timeout_seconds: float) -> bool:
    """判断锁是否已被死进程持有。"""
    info_path = lock_path.with_suffix(".info")
    if not info_path.exists():
        return False

    try:
        info = json.loads(info_path.read_text())
    except json.JSONDecodeError:
        return True  # 损坏的 info 文件，视为残留

    pid = info.get("pid", -1)
    acquired = info.get("acquired_at", 0)

    # 检测 1：进程是否存在
    try:
        os.kill(pid, 0)  # 信号 0 不杀进程，仅检查存在性
        process_alive = True
    except (OSError, ProcessLookupError):
        process_alive = False

    # 检测 2：持有时间是否超过超时阈值
    held_too_long = (time.time() - acquired) > timeout_seconds

    # 进程已死 OR 持有太久 → 判定为残留锁
    return not process_alive or held_too_long

def _break_stale_lock(lock_path: Path):
    """强制释放残留锁。"""
    logger.warning(f"破坏残留锁: {lock_path}")
    lock_path.unlink(missing_ok=True)
    lock_path.with_suffix(".info").unlink(missing_ok=True)
```

#### 死锁场景处理矩阵

| 场景 | 触发条件 | 恢复方式 | 对用户影响 |
|------|---------|---------|-----------|
| Worker SIGKILL | 进程被强制杀死 | 内核自动释放 fcntl 锁 | 无影响，锁立即释放 |
| Worker 进程崩溃 | Python 异常未捕获导致进程退出 | 内核自动释放 fcntl 锁 | 子进程退出时锁释放 |
| 持有锁的 worker 进入了死循环 | `held_too_long` 超过 timeout | 健康检查清理 + 下一个获取者 break | 锁超时后新请求可获取锁 |
| Gunicorn 优雅重启 | Master 发 SIGTERM → worker 退出 | 内核自动释放 | 重启完成后自动恢复 |
| 锁文件残留（磁盘） | 罕见：内核崩溃 / 强制断电 | 健康检查定期清理 .lock / .info | 下次获取锁时清理 |

#### 健康检查：残留锁清理

```python
# 在 health.py 的 check 中执行

def cleanup_stale_locks(lock_dir: Path, max_age_seconds: float = 3600):
    """清理残留的锁文件和 info 文件。"""
    cleaned = 0
    now = time.time()

    for info_file in lock_dir.rglob("*.info"):
        try:
            info = json.loads(info_file.read_text())
        except (json.JSONDecodeError, OSError):
            # 损坏文件直接删除
            info_file.unlink(missing_ok=True)
            info_file.with_suffix(".lock").unlink(missing_ok=True)
            cleaned += 1
            continue

        acquired = info.get("acquired_at", 0)
        pid = info.get("pid", -1)

        # 检查进程是否存活
        try:
            os.kill(pid, 0)
            process_alive = True
        except (OSError, ProcessLookupError):
            process_alive = False

        # 进程已死 OR 持有超过 max_age → 清理
        if not process_alive or (now - acquired) > max_age_seconds:
            info_file.unlink(missing_ok=True)
            lock_file = info_file.with_suffix(".lock")
            lock_file.unlink(missing_ok=True)
            cleaned += 1
            logger.info(f"清理残留锁: {lock_file} (pid={pid}, age={now - acquired:.0f}s)")

    return cleaned
```

#### 锁目录结构

```
data/.locks/
├── project/                  # 项目级写锁
│   ├── proj-abc.lock
│   └── proj-abc.info         # 持有者信息
├── page/                     # Wiki 页面读写锁
│   ├── sources_attention-paper.lock
│   └── sources_attention-paper.info
├── dir/                      # 目录操作锁
│   ├── 论文_2025.lock
│   └── 论文_2025.info
└── index/                    # 索引文件锁
    ├── proj-abc.lock
    └── proj-abc.info
```

### 摄入任务队列（持久化）

每个项目维护一个任务队列，状态持久化到 SQLite，服务重启不丢失。

#### 存储

```sql
CREATE TABLE task_queue (
    task_id       TEXT PRIMARY KEY,         -- UUID
    project_id    TEXT NOT NULL,
    action        TEXT NOT NULL,            -- "ingest" | "graph_build"
    file_paths    TEXT NOT NULL,            -- JSON array
    status        TEXT NOT NULL DEFAULT 'queued',  -- queued | running | completed | failed | rolled_back
    progress      INTEGER NOT NULL DEFAULT 0,      -- 0-100
    error_message TEXT,
    created_by    TEXT NOT NULL,            -- user_id
    created_at    TEXT NOT NULL,            -- ISO 8601
    started_at    TEXT,                     -- 开始执行时间
    completed_at  TEXT,                     -- 完成时间
    snapshot_dir  TEXT                      -- 快照路径（回滚用）
);

CREATE INDEX idx_task_project ON task_queue(project_id, status);
CREATE INDEX idx_task_created ON task_queue(created_at);
```

#### 生命周期

```
文件上传完成
    │
    ▼
创建 Task (status=queued) → 写入 SQLite → 加入内存 ProjectQueue
    │
    ▼
队列调度器取出 Task → status=running → 更新 SQLite → 开始摄入
    │
    ├─ 摄入成功 → status=completed + completed_at → 保留 7 天 → 清理
    │
    ├─ 摄入失败 → status=failed + error_message → 保留 7 天 → 清理
    │
    └─ 用户回滚  → status=rolled_back → 保留到快照过期一同清理
```

#### 服务重启恢复

```
FastAPI startup
    │
    ▼
从 SQLite 加载 status IN ("queued", "running") 的任务
    │
    ├─ queued 任务  → 按 created_at 排序加入内存队列
    │
    └─ running 任务 → 服务重启时中断，重置为 queued，重新排队
                      （此时 raw/ 中文件已保存，重新摄入安全）
```

```python
async def recover_tasks_on_startup():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM task_queue WHERE status IN ('queued', 'running') ORDER BY created_at"
    ).fetchall()

    for row in rows:
        if row["status"] == "running":
            # 中断的任务重置，等待重新执行
            db.execute(
                "UPDATE task_queue SET status='queued', progress=0, started_at=NULL WHERE task_id=?",
                (row["task_id"],)
            )
        project_queue = get_project_queue(row["project_id"])
        project_queue.enqueue(task_from_row(row))

    db.commit()
```

#### 状态查询 API

```python
# GET /api/ingestion/status/{task_id}
# 优先查内存队列（当前运行状态），回退到 SQLite（历史任务）
def get_task_status(task_id: str) -> TaskStatus:
    # 1. 检查内存队列中是否有此任务（当前在排队或运行中）
    for pq in active_queues.values():
        if task := pq.find(task_id):
            return task.to_status()

    # 2. 回退到 SQLite（已完成/失败/已回滚的历史任务）
    row = db.execute("SELECT * FROM task_queue WHERE task_id = ?", (task_id,)).fetchone()
    if row:
        return task_from_row(row).to_status()

    raise TaskNotFound(task_id)
```

#### 内存 + SQLite 双写原则

- **创建/状态变更 → 先写 SQLite，再更新内存**
- 内存队列是 SQLite 的缓存视图，不是真实数据源
- 任意时刻崩溃，SQLite 中状态是准确的
- 内存队列仅用于快速调度和轮询响应（避免每次查 SQLite）

#### 过期清理

health check 中执行，清理 SQLite 历史记录：
- `completed` / `failed` → 超过 7 天删除
- `rolled_back` → 快照过期后一同删除
- 清理前检查：当前无 queued/running 任务引用同一 project（避免并发冲突）



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

## Wiki 页面手动编辑

用户可以通过前端编辑器直接修改 wiki 页面内容，用于修正 LLM 错误提取、补充遗漏信息、调整 wikilink 等场景。

### 编辑 API

```
PUT /api/knowledge/pages/{path}
Content-Type: application/json

{
  "content": "## Summary\n更新后的 markdown 内容...",
  "edit_summary": "修正了 Transformer 的提出年份，补充了参数量数据"
}
```

### 编辑流程

```
用户打开页面 → 前端渲染预览
                      │
              [点击"编辑"按钮]
                      │
                      ▼
              切换到编辑模式（Markdown 源码编辑器）
                      │
             用户修改内容 → 实时预览（可选）
                      │
              [点击"保存"]
                      │
                      ▼
              后端 PUT 处理：
              ├─ 1. 权限校验（需要 Editor 角色）
              ├─ 2. 保存编辑前快照到 wiki/.edits/{page}/
              ├─ 3. 更新页面 Markdown
              ├─ 4. 更新 frontmatter last_updated
              ├─ 5. 扫描新 wikilink → 检测 broken links → 提示或自动创建 stub
              ├─ 6. 写入 audit_log
              └─ 7. 触发增量图谱重建（仅受影响节点）
```

### 编辑快照

与摄入快照分开管理，粒度更细（单页面级别）：

```
wiki/.edits/
├── sources/
│   └── attention-paper/
│       ├── 2026-05-09T14-30-00_u-abc.md   # 编辑前快照
│       ├── 2026-05-09T16-22-00_u-xyz.md
│       └── .manifest.json                   # 快照索引
├── entities/
│   └── Self-Attention/
│       └── 2026-05-09T15-10-00_u-abc.md
└── concepts/
    └── Transformer/
        └── ...
```

`manifest.json` 记录每页的编辑链：
```json
{
  "page": "sources/attention-paper.md",
  "edits": [
    {"timestamp": "2026-05-09T14:30:00", "user": "u_abc", "summary": "修正 Transformer 提出年份"},
    {"timestamp": "2026-05-09T16:22:00", "user": "u_xyz", "summary": "补充参数量数据"}
  ]
}
```

### 页面历史 API

```
GET /api/knowledge/pages/{path}/history

→ {
  "page": "sources/attention-paper.md",
  "created_by": "ingest task_123",
  "edits": [
    {"version": 3, "timestamp": "...", "user": "u_xyz", "summary": "..."},
    {"version": 2, "timestamp": "...", "user": "u_abc", "summary": "..."},
    {"version": 1, "timestamp": "...", "user": "ingest", "summary": "初始摄入"}
  ]
}
```

- 前端可以展示编辑历史列表，点击某版本查看当时的页面内容
- 回滚到历史版本通过 `PUT` 接口重新写入（内容 = 历史快照），形成新版本而非覆盖历史

### Wikilink 自动修正

编辑保存时，后端扫描新增和删除的 `[[wikilinks]]`：

| 变更 | 处理 |
|------|------|
| 新增 `[[NewPage]]`，目标不存在 | 提示用户"链接到尚未存在的页面，将自动创建 stub" |
| 删除 `[[OldPage]]`，无其他页面引用 | OldPage 变为 orphan，下次 lint 报告标记 |
| 修改 `[[OldName]]` → `[[NewName]]` | 不自动重命名页面（可能其他页面也在引用旧名），lint 标记 |

编辑保存成功后，前端 toast：「页面已保存。新增 2 个 wikilink，其中 1 个目标页面不存在，已自动创建 stub。」

### 编辑并发控制

- 编辑保存使用乐观锁：请求携带 `If-Match: <SHA256 of current page>`
- 如果页面在用户编辑期间被他人修改，返回 409 Conflict：「页面已被 u_xyz 修改，请刷新后重新编辑」
- 前端对比差异，帮助用户合并

### 编辑安全

- Markdown 内容经过与摄入相同的 XSS 防护（markdown-it + DOMPurify）
- 编辑保存同样触发 wikilink 验证（不允许 `[[../../raw/secret]]`）
- 编辑操作同样写入审计日志，标记 `action = "page_edit"`

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

### 审计日志 vs 应用日志 边界

| 维度 | 审计日志 | 应用日志 |
|------|---------|---------|
| **记录内容** | 谁在什么时候做了什么 | 系统内部发生了什么 |
| **受众** | 管理员、合规审查 | 开发者、运维 |
| **存储** | SQLite + wiki/log.md | 文件系统（JSON Lines） |
| **不可变性** | 不可删除 | 按 retention 轮转 |
| **查询方式** | API 查询 + CSV 导出 | tail / grep / jq / 日志聚合 |
| **包含敏感数据** | 否（仅元信息） | 可能（堆栈、请求体片段） |

---

## 应用日志

所有后端组件使用统一的日志框架，覆盖 LLM 调用、文件操作、摄入流程、异常堆栈等系统运行信息。

### 日志框架

```python
# app/logging_config.py
import logging
import json
import time
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

class StructuredFormatter(logging.Formatter):
    """JSON Lines 结构化日志，方便 grep / jq / 日志聚合工具解析。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%f%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": f"{record.module}:{record.funcName}:{record.lineno}",
        }

        # 附加上下文字段（通过 logging adapter 或 extra 传入）
        for key in ("project_id", "user_id", "task_id", "request_id", "duration_ms"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        # 异常信息
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }
            if record.exc_text:
                log_entry["error"]["traceback"] = record.exc_text.split("\n")

        return json.dumps(log_entry, ensure_ascii=False, default=str)
```

### 初始化

```python
def setup_logging(log_dir: Path, level: str = "INFO"):
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper()))

    # Handler 1: 结构化 JSON → 文件（按大小轮转）
    app_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=10,              # 保留 10 个轮转文件
        encoding="utf-8",
    )
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(StructuredFormatter())
    root.addHandler(app_handler)

    # Handler 2: 结构化 JSON → 错误专用文件
    err_handler = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=20 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(StructuredFormatter())
    root.addHandler(err_handler)

    # Handler 3: 可读格式 → stdout（开发环境）
    if level.upper() == "DEBUG":
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s"
        ))
        root.addHandler(console)
```

### 日志级别约定

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| **DEBUG** | 开发调试细节 | SQL 查询语句、LLM prompt 全文、wikilink 扫描中间结果 |
| **INFO** | 正常业务流程 | 摄入开始/完成、文件上传成功、图谱构建耗时、API 响应码 |
| **WARNING** | 可恢复的异常 | LLM 重试、文件锁等待、快照清理跳过、内存使用偏高 |
| **ERROR** | 需要关注的错误 | 摄入失败、LLM API 不可达、磁盘写入失败、JSON 解析失败 |
| **CRITICAL** | 服务级故障 | 数据库损坏、数据目录不可访问、所有 LLM 后端不可用 |

### 日志覆盖点

#### LLM 调用（LLMEngine）

```python
logger.info(
    "LLM 调用开始",
    extra={
        "task_id": task_id,
        "model": "deepseek-v4-flash",
        "prompt_len": len(prompt),
        "max_tokens": 8192,
    },
)

# ... API 调用 ...

logger.info(
    "LLM 调用完成",
    extra={
        "task_id": task_id,
        "duration_ms": elapsed_ms,
        "response_len": len(response),
        "tokens_used": response.get("usage", {}).get("total_tokens"),
    },
)

if elapsed_ms > 30000:
    logger.warning(
        f"LLM 调用耗时偏高: {elapsed_ms}ms",
        extra={"task_id": task_id, "duration_ms": elapsed_ms},
    )

if retry_count > 0:
    logger.warning(
        f"LLM 调用第 {retry_count} 次重试",
        extra={"task_id": task_id, "retry_count": retry_count, "reason": last_error},
    )
```

#### 文件操作（FileService / ConvertEngine）

```python
logger.info("文件上传", extra={"file": filename, "size_bytes": size, "project_id": project_id})
logger.info("文件转换开始", extra={"source": src, "format": fmt})
logger.info("文件转换完成", extra={"duration_ms": ms, "output_size": size})
logger.error("文件转换失败", exc_info=True, extra={"source": src, "format": fmt})
```

#### 摄入流程（IngestService）

```python
logger.info("摄入开始", extra={"task_id": tid, "file": path, "user": uid})
logger.info("摄入步骤", extra={"task_id": tid, "step": s, "step_name": name})
logger.info("摄入完成", extra={"task_id": tid, "duration_ms": ms, "pages_created": n})
logger.error("摄入失败", exc_info=True, extra={"task_id": tid, "failed_step": s, "error_code": code})
```

#### HTTP 请求（FastAPI Middleware）

```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid4())
    t0 = time.time()

    response = await call_next(request)

    duration_ms = (time.time() - t0) * 1000
    logger.info(
        f"{request.method} {request.url.path} → {response.status_code}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 1),
            "user_agent": request.headers.get("user-agent", ""),
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response
```

#### 并发 / 锁（LockManager）

```python
logger.debug("获取锁", extra={"scope": scope, "identifier": id_})
logger.warning("锁等待超时，检测死锁", extra={"lock": str(path), "timeout": t})
logger.warning("强制释放残留锁", extra={"lock": str(path), "pid": pid, "age": age})
```

### 日志存储

```
data/logs/
├── app.log              # 当前应用日志（JSON Lines，最大 50MB）
├── app.log.1            # 轮转历史
├── app.log.2
│   ...
├── app.log.10           # 最旧（10 代）
├── error.log            # 当前错误日志（JSON Lines，最大 20MB）
├── error.log.1
│   ...
└── error.log.5
```

### 日志查询辅助

提供命令行工具 `tools/logs.py`：

```bash
# 按级别过滤
python tools/logs.py --level ERROR

# 按项目过滤
python tools/logs.py --project proj_123

# 按时间范围过滤
python tools/logs.py --since "2026-05-09 14:00" --until "2026-05-09 15:00"

# 按 task_id 追踪完整链路
python tools/logs.py --task-id uuid

# 输出最近 100 条
python tools/logs.py --tail 100

# 实时跟踪
python tools/logs.py --follow
```

### 日志安全

- **不记录完整文件内容**：LLM prompt 中长内容截断为摘要（`prompt_len` 字段），DEBUG 级别才记录全文
- **不记录 API Key**：通过 litellm 内置的 key masking，环境变量中的 key 不会出现在日志
- **堆栈信息仅在 ERROR 级别记录**：避免 INFO 日志中泄露内部路径结构
- **日志文件权限**：0600（仅 owner 可读写）
- **随备份导出**：备份包中可选包含日志目录

---

## 前端设计

### 页面与路由

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | 登录 | JWT 认证 |
| `/:projectId` | 知识库主页 | 源文件管理 + 查询（Tab 切换） |
| `/:projectId/graph` | 知识图谱 | AntV G6 v5 交互式图谱 |
| `/:projectId/settings` | 设置 | 项目信息、LLM 参数覆盖、备份恢复、审计日志 |

所有项目内页面路由包含 `:projectId` 路径参数，前端根据当前项目 ID 加载对应数据。

### 项目切换器

位于侧边栏顶部，是用户切换工作上下文的入口。

```
┌─────────────────────────┐
│  🧠 LLM Wiki            │  ← 品牌标识
│                         │
│  ┌─────────────────────┐│
│  │ AI 研究知识库    ▾  ││  ← 项目切换器（当前项目）
│  └─────────────────────┘│
│                         │
│  📖 知识库              │  ← 导航项（相对当前项目）
│  🔗 知识图谱            │
│  ⚙️ 设置               │
│                         │
│  ─────────────────────  │
│  + 新建项目             │  ← 快捷入口
│  📋 所有项目            │  ← 项目列表
└─────────────────────────┘
```

点击项目切换器展开下拉面板：

```
┌──────────────────────────────┐
│  🔍 搜索项目...              │  ← 输入过滤（> 5 个项目时显示）
│                              │
│  ● AI 研究知识库             │  ← 当前选中（圆点标记）
│    3 个活跃任务              │  ← 摄入进行中提示
│                              │
│  ○ 竞品分析                  │
│    最后摄入: 2 小时前        │
│                              │
│  ○ 会议记录归档              │
│    📦 已归档                 │  ← 归档标记
│                              │
│  ────────────────────────────│
│  ☐ 显示已归档项目 (2)        │  ← 默认隐藏归档
│  ────────────────────────────│
│  + 新建项目                  │
└──────────────────────────────┘
```

#### 项目切换行为

```
用户切换项目
    │
    ▼
1. 取消当前项目所有在途请求（AbortController）
2. 路由跳转 /:newProjectId（保持当前子页面，如 /graph → /newId/graph）
3. Pinia stores 重置（files/wiki/graph 清空）
4. 重新加载新项目数据（目录树、wiki 页面树、图谱数据）
5. 更新文档标题（document.title = "项目名 — LLM Wiki"）
6. 保存上次访问项目到 localStorage，下次登录自动进入
```

#### 无项目状态

用户登录后但未加入任何项目：

```
┌─────────────────────────┐
│  🧠 LLM Wiki            │
│                         │
│  欢迎使用 LLM Wiki       │
│                         │
│  你还没有加入任何项目    │
│                         │
│  ┌──────────────────┐   │
│  │  🚀 创建第一个项目 │   │
│  └──────────────────┘   │
│                         │
│  或联系管理员将你        │
│  加入已有项目            │
└─────────────────────────┘
```

#### Pinia 项目 Store

```typescript
// src/stores/project.ts
export const useProjectStore = defineStore('project', () => {
  const projectId = ref<string | null>(null)
  const project = ref<Project | null>(null)
  const projects = ref<ProjectSummary[]>([])

  // 路由守卫在每次导航时调用
  async function setCurrentProject(id: string) {
    if (id === projectId.value) return  // 相同项目，跳过

    // 取消旧项目请求
    cancelAllProjectRequests()

    projectId.value = id
    const detail = await projectApi.get(id)
    project.value = detail

    // 触发其他 store 重新加载
    const filesStore = useFilesStore()
    const wikiStore = useWikiStore()
    const graphStore = useGraphStore()
    await Promise.all([
      filesStore.loadDirTree(id),
      wikiStore.loadPageTree(id),
      graphStore.loadStats(id),
    ])

    document.title = `${detail.name} — LLM Wiki`
  }

  return { projectId, project, projects, setCurrentProject }
})
```

#### 全局 404 / 无权限页面

- 路由 `/:projectId` 中 projectId 不存在 → 「项目不存在或你无权访问」
- 用户被移除项目后刷新页面 → 同上
- 提供「返回项目列表」按钮

### 导航结构
侧边栏 3 项 + 顶部项目切换器：
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
- **摄入进度**：5 步进度条（转换→LLM 提取→写页面→更新索引→[重建图谱]），Step 5 根据 `auto_graph_rebuild` 设置条件执行

### 摄入失败处理

摄入调用链路长（文件转换 → LLM API → JSON 解析 → 写页面 → 图计算），每个环节都可能失败。失败原因和恢复方式差异大，需分类设计。

#### 失败分类与响应

```
摄入 Pipeline
  ├─ 步骤 1: 文件格式转换 (markitdown)
  │   └─ 失败 → 类型：CONVERSION_ERROR
  │       原因：文件损坏 / 加密 PDF / 不支持的编码
  │       可重试？ 否（换工具或手动转换）
  │
  ├─ 步骤 2: LLM API 调用
  │   └─ 失败 → 类型：LLM_API_ERROR
  │       原因：超时 / 限流 429 / 5xx / 网络中断
  │       可重试？ 是（指数退避自动重试，最多 3 次）
  │
  ├─ 步骤 3: LLM 响应解析
  │   └─ 失败 → 类型：LLM_PARSE_ERROR
  │       原因：JSON 格式错误 / 缺少必要字段 / 返回非 JSON 文本
  │       可重试？ 是（提示 LLM 修正格式，重试 1 次）
  │
  ├─ 步骤 4: Wiki 页面写入
  │   └─ 失败 → 类型：IO_ERROR
  │       原因：磁盘满 / 权限不足 / 文件被锁定
  │       可重试？ 否（需运维介入）
  │
  └─ 步骤 5: 图谱重建（条件执行）
      └─ 条件：仅在 features.auto_graph_rebuild = true 时执行
              为 false 時跳过，摄入状态标记为 completed_without_graph
      └─ 失败 → 类型：GRAPH_ERROR
          原因：NetworkX 内存溢出 / JSON 序列化失败
          可重试？ 部分（wiki 已写入成功，图谱可稍后手动重建）
```

### 摄入 Pipeline 与独立图谱构建的关系

#### 决策表

| 场景 | 摄入 Pipeline Step 5 | 图谱更新方式 |
|------|---------------------|-------------|
| `auto_graph_rebuild: true` | 自动执行（摄入成功 → 立即重建） | 摄入 task 内部完成 |
| `auto_graph_rebuild: false` | 跳过（摄入完成但带提示） | 用户手动调用 `POST /api/graph/build` |
| 手动编辑 wiki 页面 | N/A（不触发摄入） | 前端提示或用户手动调用 |
| Re-ingest（refresh） | 同 `auto_graph_rebuild` 设置 | 同上 |
| Rollback 摄入 | 强制自动重建（不可跳过） | 回滚 task 内部完成 |
| 用户手动 `POST /api/graph/build` | N/A | 独立 task，走任务队列 |

#### 摄入完成后前端提示

当 `auto_graph_rebuild: false` 时，摄入 status = `completed_without_graph`：

```
摄入完成 — 3 个页面已更新

图谱未更新（自动重建已关闭）

[🔗 立即重建图谱]   [查看页面]   [关闭]
```

#### 独立 graph/build 走任务队列

`POST /api/graph/build` 创建 `action: "graph_build"` 的持久化任务，与摄入任务共享同一项目写锁：

```
POST /api/graph/build { project_id: "xxx" }
  → 创建 task (action="graph_build", status="queued")
  → 写入 task_queue 表
  → 加入 ProjectQueue（排队等待项目写锁）
  → 返回 task_id

GET /api/ingestion/status/{task_id}
  → { status: "running", progress: 75, ... }
  → 图谱构建同样通过摄入状态 API 查询进度
```

独立图谱构建与摄入中的 Step 5 使用**完全相同的代码路径**（`GraphService.rebuild()`），区别仅在于触发方式（自动 vs 手动）。

```python
class GraphService:
    def rebuild(self, project_id: str, triggered_by: str) -> GraphResult:
        """
        triggered_by: "ingestion_step5" | "manual_build" | "rollback" | "page_edit"
        仅用于日志区分，逻辑完全一致。
        """
```

#### API 返回格式

```json
// GET /api/ingestion/status/{task_id}
{
  "task_id": "uuid",
  "status": "failed",
  "failed_step": 2,
  "failed_step_name": "LLM 知识提取",
  "error": {
    "code": "LLM_API_TIMEOUT",
    "category": "llm_api_error",
    "message": "DeepSeek API 响应超时（已等待 60 秒）",
    "detail": "模型接口 10.0.1.5:8000/v1/chat/completions 未在 60s 内响应",
    "retryable": true,
    "retry_count": 3,
    "max_retries": 3,
    "retry_strategy": "exponential_backoff",
    "suggestions": [
      "检查 DeepSeek 服务是否正常运行",
      "如果模型负载高，可在设置中调大超时时间",
      "尝试减小文件体积后重新上传"
    ]
  },
  "created_at": "2026-05-09T14:30:00+08:00",
  "failed_at": "2026-05-09T14:31:05+08:00"
}
```

#### 自动重试策略

| 错误类型 | 重试次数 | 退避策略 | 总耗时上限 |
|----------|---------|---------|-----------|
| LLM_API_TIMEOUT | 3 | 指数退避: 5s → 15s → 45s | ~130s |
| LLM_API_RATE_LIMITED (429) | 3 | 读取 Retry-After header，无则 30s → 60s → 120s | ~3min |
| LLM_API_5XX | 3 | 线性: 10s → 20s → 40s | ~70s |
| LLM_PARSE_ERROR | 1 | 无退避，立即重试（提示 LLM 修正格式） | ~30s |
| CONVERSION_ERROR | 0 | 不重试 | — |
| IO_ERROR | 0 | 不重试 | — |

重试期间前端显示："第 2 次重试中（3s 后）..."

#### 用户操作

每种失败状态提供差异化操作入口：

```
摄入失败 — 错误类型决定可用操作
│
├─ LLM_API_ERROR / LLM_PARSE_ERROR（可重试）
│   ├── [🔄 重新摄入] — 使用相同文件重新触发（不重新上传）
│   ├── [📋 查看原始错误] — 展开技术详情（折叠面板）
│   └── [⚙️ LLM 设置] — 跳转到设置页调参
│
├─ CONVERSION_ERROR（格式问题）
│   ├── [📥 下载原始文件] — 用户手动转换后重新上传
│   ├── [📋 查看转换日志] — markitdown 的错误输出
│   └── [📖 支持格式说明] — 链接到帮助文档
│
├─ IO_ERROR（磁盘/权限）
│   ├── [📋 查看错误详情] — 含建议（联系管理员）
│   └── [📞 通知管理员] — 复制错误信息
│
└─ GRAPH_ERROR（图谱失败，wiki 已写入）
    ├── [✅ 接受] — wiki 已写入，稍后手动重建图谱
    └── [🔄 重建图谱] — 立即重试图谱构建
```

#### 前端失败状态 UI

```
┌─────────────────────────────────────────────────────────┐
│  📄 attention.pdf                                      │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  摄入失败                                          │ │
│  │                                                    │ │
│  │  ⏱ LLM 知识提取阶段                                 │ │
│  │  DeepSeek API 响应超时（已等待 60 秒）               │ │
│  │  已自动重试 3 次，全部失败                           │ │
│  │                                                    │ │
│  │  可能原因：模型服务负载过高或暂时不可用                │ │
│  │                                                    │ │
│  │  [📋 查看技术详情]                                  │ │
│  │                                                    │ │
│  │  [🔄 重新摄入]   [⚙️ 调整 LLM 设置]   [🗑 删除文件]  │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

#### 全局摄入状态面板

在侧边栏底部或右上角显示小图标，汇总当前项目的摄入状态：

- 🟢 绿色圆点：上一次摄入成功，X 分钟前
- 🟡 黄色圆点：摄入进行中（第 X/5 步）
- 🔴 红色圆点：上一次摄入失败，点击查看详情
- ⚪ 灰色圆点：暂无摄入记录

点击图标展开下拉面板，显示最近 5 次摄入记录的简要状态。

#### 设计原则

- **错误信息说人话**："LLM API 响应超时（已等待 60 秒）"而非 "HTTP 504 from upstream"
- **告诉用户能做什么**：每个错误附带 2-3 条具体建议，不给"请联系管理员"这种空洞文案
- **可重试的就自动重试**：网络抖动、API 限流等瞬时故障用户不应感知
- **自动重试耗尽后才向用户暴露**：只有真正需要用户决策的失败才打断用户
- **失败不等于数据丢失**：文件在 raw/ 中保留，wiki 未写入是干净状态，用户可以安心重试

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

### Markdown 渲染与 XSS 防护

Wiki 页面的内容来源链路：用户上传文件 → markitdown 转换 → LLM 生成 markdown → 前端渲染。每个环节都可能引入恶意内容，前端渲染是最后一道防线。

#### 渲染 Pipeline

```
后端返回 markdown 字符串
        │
        ▼
    markdown-it 解析为 HTML
        │
        ▼
    DOMPurify 清洗 HTML → v-html 挂载
```

#### markdown-it 配置

```typescript
// src/lib/markdown.ts
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({
  html: false,          // 禁用 raw HTML 标签
  linkify: true,        // 自动识别 URL 转为链接
  breaks: true,         // 换行 → <br>
  typographer: false,   // 禁用智能引号（中文内容会出问题）
})

// 白名单：仅允许安全协议
const ALLOWED_URI_SCHEMES = ['http', 'https', 'mailto']

export function renderMarkdown(raw: string): string {
  // 1. markdown → HTML
  const html = md.render(raw)

  // 2. DOMPurify 清洗
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'p', 'br', 'hr',
      'ul', 'ol', 'li',
      'blockquote', 'pre', 'code',
      'strong', 'em', 's', 'del', 'ins', 'mark',
      'a', 'img',
      'table', 'thead', 'tbody', 'tr', 'th', 'td',
      'span', 'div',
    ],
    ALLOWED_ATTR: [
      'href', 'target', 'rel',      // <a>
      'src', 'alt', 'title',        // <img>
      'class',                       // 代码高亮 class
      'id',                          // 锚点跳转
    ],
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
    // 禁止 javascript: data: vbscript: 等危险协议
  })

  return clean
}
```

#### Wikilink 预处理

markdown-it 不识别 `[[PageName]]` 语法，需在解析前将 wikilink 转为安全链接：

```typescript
function preprocessWikilinks(raw: string, projectId: string): string {
  // [[PageName]] → [PageName](/wiki/pages/PageName)
  // [[PageName|显示文本]] → [显示文本](/wiki/pages/PageName)
  return raw
    .replace(/\[\[([^\]|]+)\]\]/g, (_, page) => {
      const slug = page.trim()
      return `[${slug}](/projects/${projectId}/pages/${encodeURIComponent(slug)})`
    })
    .replace(/\[\[([^\]]+)\|([^\]]+)\]\]/g, (_, page, text) => {
      const slug = page.trim()
      return `[${text.trim()}](/projects/${projectId}/pages/${encodeURIComponent(slug)})`
    })
}
```

#### 安全层级总览

| 层级 | 措施 | 拦截内容 |
|------|------|---------|
| markdown-it | `html: false` | `<script>`、`<iframe>`、`<style>` 等 raw HTML 标签 |
| Wikilink 预处理 | `encodeURIComponent` | `[[../../etc/passwd]]` 路径穿越 |
| DOMPurify | 标签/属性白名单 | `onclick`、`onerror`、`onload` 等事件处理器 |
| DOMPurify | URI 协议白名单 | `javascript:alert(1)` 伪协议 |
| CSP Header | 后端响应头 | 作为纵深防御，限制 script-src 来源 |
| 后端存储 | 文件名规范化（见上传安全） | `<img src=​"raw/../../../etc/shadow">` |

#### CSP 响应头（纵深防御）

后端 Nginx 或 FastAPI 中间件追加：

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;
```

- `script-src 'self'` — 禁止内联脚本和外部脚本注入
- `img-src 'self' data:` — 仅允许同源图片和 base64 data URI
- `style-src 'unsafe-inline'` — 允许内联样式（markdown 渲染的 style 属性不可避免）

#### Vue 组件使用

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown, preprocessWikilinks } from '@/lib/markdown'

const props = defineProps<{ raw: string; projectId: string }>()

const rendered = computed(() => {
  const withLinks = preprocessWikilinks(props.raw, props.projectId)
  return renderMarkdown(withLinks)
})
</script>

<template>
  <!-- DOMPurify 已清洗，直接 v-html 安全 -->
  <div class="wiki-content" v-html="rendered" />
</template>
```

---

## 前端请求管理

所有前端 API 请求通过统一的请求管理层（`src/api/`）发起，组件和 composable 不直接调用 Axios。

### 架构

```
组件 / Composable
       │
       ▼
  src/api/*.ts          ← 各模块 API 函数（auth.ts / files.ts / ...）
       │
       ▼
  src/api/client.ts     ← 统一 Axios 实例 + 拦截器
       │
       ▼
  后端 FastAPI :8000
```

### client.ts — Axios 实例

```typescript
// src/api/client.ts
import axios from 'axios'
import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

const client: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器：自动附加 JWT
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// 响应拦截器：统一错误处理 + Token 刷新
client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      try {
        await auth.refreshToken()
        // 重试原请求
        return client.request(error.config!)
      } catch {
        auth.logout()
        router.push('/login')
      }
    }
    return Promise.reject(error)
  }
)

export default client
```

### 错误码映射

| HTTP 状态码 | 含义 | 前端处理 |
|-------------|------|----------|
| 400 | 请求参数错误 | Toast 显示 `response.data.detail` |
| 401 | Token 过期 | 自动刷新 Token，失败则跳登录 |
| 403 | 权限不足 | Toast "无权执行此操作" |
| 404 | 资源不存在 | 返回 null，由调用方处理 |
| 409 | 并发冲突 | 返回当前 task_id，前端提示"操作排队中" |
| 422 | 参数校验失败 | 表单字段内联错误提示 |
| 423 | 资源锁定 | 提示"操作繁忙，请稍后重试"，3s 后自动重试 |
| 429 | 请求过于频繁 | 显示 Retry-After 倒计时 |
| 5xx | 服务端错误 | Toast "服务器异常"，上报 Sentry（如有） |

### 请求取消

长时间查询和文件上传支持用户主动取消：

```typescript
// src/api/client.ts
import { ref } from 'vue'

// 全局请求取消 Map
export const pendingRequests = new Map<string, AbortController>()

export function createCancelableRequest(key: string) {
  pendingRequests.get(key)?.abort()   // 取消前任请求
  const controller = new AbortController()
  pendingRequests.set(key, controller)
  return { signal: controller.signal, key }
}

export function cancelRequest(key: string) {
  pendingRequests.get(key)?.abort()
  pendingRequests.delete(key)
}
```

使用场景：
- 用户快速切换知识库项目 → 取消前一个项目的未完成请求
- 用户在查询结果返回前输入新问题 → 取消上一次查询
- 用户取消文件上传

### 加载状态管理

```typescript
// src/api/client.ts — 全局请求计数器
import { ref } from 'vue'

export const activeRequests = ref(0)

client.interceptors.request.use((config) => {
  activeRequests.value++
  return config
})

client.interceptors.response.use(
  (response) => { activeRequests.value--; return response },
  (error) => { activeRequests.value--; return Promise.reject(error) }
)

// 组件中使用：顶部全局 Loading 条
// <ProgressBar v-if="activeRequests > 0" />
```

单个操作的加载状态由各 API 函数返回 Promise，调用方自行管理 `isLoading` ref。

### 模块 API 示例

```typescript
// src/api/files.ts
import client from './client'
import type { FileItem, DirTree, UploadResponse } from '@/types'

export const filesApi = {
  /** 获取目录树 */
  getDirTree(projectId: string, subdir?: string) {
    return client.get<DirTree>('/files/dirs', { params: { project_id: projectId, dir: subdir } })
  },

  /** 上传文件（multipart，带进度回调） */
  uploadFile(projectId: string, subdir: string, file: File, onProgress?: (pct: number) => void) {
    const form = new FormData()
    form.append('project_id', projectId)
    form.append('subdir', subdir)
    form.append('file', file)
    return client.post<UploadResponse>('/files/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => onProgress?.(Math.round((e.progress ?? 0) * 100)),
    })
  },

  /** 删除文件（需确认） */
  deleteFile(fileId: string) {
    return client.delete(`/files/${fileId}`)
  },
}
```

### 设计原则

- **组件不直接调 Axios** — 所有请求经过 `src/api/`，便于统一改 baseURL/超时/拦截逻辑
- **API 函数按资源模块拆分** — 与后端 API 路由一一对应
- **错误不吞没** — 拦截器统一处理后仍向调用方 reject，让上层感知错误
- **取消优于等待** — 页面切换或重复操作时主动取消旧请求
- **加载状态分层** — 全局进度条（activeRequests）+ 局部按钮 loading（各组件自主管理）

---

## API 调用流程

```
1. 用户上传文件
   POST /api/files/upload (multipart) { project_id, subdir, file }
   → 文件保存到 raw/{subdir}/file
   → 后台触发摄入任务
   → 返回 task_id

2. 前端轮询摄入进度（自适应轮询，见下方设计）
   GET /api/ingestion/status/{task_id}
   → { step: 3, total: 5, steps: [...], elapsed: 13.1s }

3. 摄入完成后自动重建图谱
   前端 GET /api/graph/data → 渲染 AntV G6

4. 用户查询知识库
   POST /api/knowledge/query { question }
   → LLM 综合回答 + [[wikilink]] 引用 + 来源页面列表
```

---

## 实时状态更新：自适应轮询

不引入 WebSocket。v1 使用 HTTP 自适应轮询，理由：

- 摄入任务 10–120 秒完成，秒级延迟完全可接受
- 轮询无状态，前端断开重连无恢复逻辑
- FastAPI + Nginx 零额外配置
- WebSocket 连接管理、鉴权、断线重连的复杂度 ≥ 收益

v2 可选升级为 **Server-Sent Events (SSE)**：比 WebSocket 轻量（HTTP 单向推送），FastAPI 原生支持，Nginx 兼容好。

### 自适应轮询策略

```typescript
// src/composables/useTaskPolling.ts

function getPollingInterval(step: number, status: string): number {
  // 任务排队中：慢轮询
  if (status === 'queued') return 5000

  // 摄入进行中，按步骤阶段调整
  switch (step) {
    case 1: return 3000  // 文件转换（快，3s 足够）
    case 2: return 2000  // LLM API 调用（最耗时但最需要感知进度）
    case 3: return 3000  // 写入页面（快）
    case 4: return 3000  // 更新索引（快）
    case 5: return 5000  // 重建图谱（慢）
    default: return 3000
  }
}
```

| 任务状态 | 轮询间隔 | 理由 |
|---------|---------|------|
| `queued`（排队中） | 5s | 排队时间不确定，低频轮询减少无效请求 |
| `running` step 1–4 | 2–3s | 摄入进行中，需要感知进度 |
| `running` step 5（图谱） | 5s | 图谱构建较慢，降低轮询频率 |
| `completed` / `failed` | 停止轮询 | 终态 |

### 退避策略

网络错误或 429 时自动退避：

```
正常: 3s → 3s → 3s
出错: 3s → 6s → 12s → 24s → 30s(max) → 恢复后重置为 3s
```

### 前端实现

```typescript
// src/composables/useTaskPolling.ts
import { ref, onUnmounted } from 'vue'
import { ingestionApi } from '@/api/ingestion'

export function useTaskPolling(taskId: string) {
  const task = ref<TaskStatus | null>(null)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let retryCount = 0

  function start() {
    poll()
  }

  async function poll() {
    try {
      const result = await ingestionApi.getStatus(taskId)
      task.value = result
      error.value = null
      retryCount = 0  // 成功后重置退避计数

      if (result.status === 'completed' || result.status === 'failed') {
        return  // 终态，停止轮询
      }

      const interval = getPollingInterval(result.step, result.status)
      timer = setTimeout(poll, interval)
    } catch (e) {
      error.value = e.message
      retryCount++
      const backoff = Math.min(3000 * Math.pow(2, retryCount), 30000)
      timer = setTimeout(poll, backoff)
    }
  }

  function stop() {
    if (timer) { clearTimeout(timer); timer = null }
  }

  onUnmounted(stop)

  return { task, error, start, stop }
}
```

### 多任务轮询合并

同一页面上可能有多个活跃任务（不同文件的摄入并行）。前端合并为一个批量轮询请求：

```
POST /api/ingestion/statuses
body: { "task_ids": ["t1", "t2", "t3"] }

→ {
  "tasks": {
    "t1": { "status": "running", "step": 2, ... },
    "t2": { "status": "completed", ... },
    "t3": { "status": "queued", ... }
  }
}
```

文件管理页的文件列表中，每个文件如果是「摄入中」状态，通过批量轮询更新状态图标。

### 全局摄入状态指示器更新

侧边栏的状态圆点也通过轮询更新（低频 30s 一次，查最近一个任务的终态）：

```typescript
// 使用递归 setTimeout，确保上一次请求完成后再启动下一次
let timer: ReturnType<typeof setTimeout>

function schedulePoll() {
  timer = setTimeout(async () => {
    try {
      const history = await ingestionApi.getHistory({ limit: 1 })
      latestStatus.value = history.data[0]?.status ?? 'none'
    } catch {
      // 静默失败，不影响下次轮询
    } finally {
      schedulePoll()  // 请求完成后才安排下一次
    }
  }, 30000)
}

schedulePoll()

// 组件卸载时
onUnmounted(() => clearTimeout(timer))
```

### 为什么不用 setInterval

所有轮询统一使用**递归 `setTimeout`**，不使用 `setInterval`：

| 问题 | `setInterval` | 递归 `setTimeout` |
|------|--------------|-------------------|
| 请求堆积 | 如果上次请求耗时 > 间隔，新请求立即触发，可能堆积多个并发请求 | 上次请求完成后才安排下一次，永远只有一个在途请求 |
| 回调异常 | 某次回调抛出异常，后续仍继续执行（可能重复失败） | 异常被 try/catch 捕获，不影响下一次调度 |
| 清理 | 需要保存 interval ID 并在 onUnmounted 中 clearInterval | 同样需要保存 timeout ID，但递归链自然断裂更容易 |
| 退避调整 | 动态改变间隔需要 clearInterval + 重新 setInterval | 直接传入新的延迟值即可 |

递归 `setTimeout` 的核心原则：**下一次轮询在上一次请求完成后才开始计时**，请求本身不重叠。

## 配置管理

### 配置来源与优先级

配置按以下优先级加载（高→低）：

1. **环境变量** `LLM_WIKI_*` — 最高优先级，Docker / systemd 部署首选
2. **`.env` 文件** — 项目根目录，开发环境
3. **`config.yaml`** — 配置文件，生产部署
4. **代码内默认值** — 最低优先级

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ── 应用 ──
    app_name: str = "LLM Wiki"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"         # DEBUG | INFO | WARNING | ERROR

    # ── 数据目录 ──
    data_dir: str = "./data"        # 所有数据存储根目录

    # ── 默认 LLM（全局默认，项目可覆盖）──
    llm_provider: str = "openai_compatible"  # deepseek | glm | openai_compatible
    llm_model: str = "deepseek/deepseek-v4-flash"  # litellm model id
    llm_api_base: str = "http://localhost:8000/v1"  # OpenAI 兼容 API 地址
    llm_api_key: str = ""           # 必填，无默认值
    llm_temperature: float = 0.3
    llm_max_tokens: int = 8192
    llm_timeout: int = 120          # 秒
    llm_max_retries: int = 3
    llm_extra_headers: dict = {}    # 自定义 HTTP 头（如 X-Auth-Token）
    llm_fast_model: str = ""        # 轻量任务模型，空则复用 llm_model

    # ── 服务 ──
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 2                # Gunicorn workers
    secret_key: str = ""            # JWT 签名密钥，必填，启动时校验

    # ── 安全 ──
    max_upload_size_mb: int = 100
    cors_origins: list[str] = ["*"]
    registration_open: bool = False  # 是否开放注册

    # ── 保留策略 ──
    snapshot_retention_days: int = 30
    task_history_days: int = 7
    log_retention_days: int = 90

    model_config = {
        "env_prefix": "LLM_WIKI_",
        "env_file": ".env",
        "yaml_file": "config.yaml",
    }
```

### config.yaml 示例

```yaml
# config.yaml — 生产部署配置文件
app_name: "AI 研究知识库"
debug: false
log_level: "INFO"

data_dir: "/data/llm-wiki"

llm:
  provider: "openai_compatible"
  model: "deepseek/deepseek-v4-flash"       # 改为 glm/glm-47 切换 GLM-47
  api_base: "http://10.0.1.5:8000/v1"      # OpenAI 兼容 API 地址
  api_key: "${LLM_WIKI_LLM_API_KEY}"       # 引用环境变量
  temperature: 0.3
  max_tokens: 8192
  extra_headers: {}                         # 自定义 HTTP 头

service:
  host: "0.0.0.0"
  port: 8000
  workers: 4
  secret_key: "${LLM_WIKI_SECRET_KEY}"

security:
  max_upload_size_mb: 100
  cors_origins:
    - "http://wiki.internal.example.com"
  registration_open: false

retention:
  snapshot_days: 30
  task_history_days: 7
  log_days: 90
```

### 启动校验

FastAPI startup 阶段执行必填项校验：

```python
# 启动失败，如果缺少必要配置
if not settings.llm_api_key:
    raise ConfigError("LLM_WIKI_LLM_API_KEY 未设置。请设置环境变量或在 config.yaml 中配置。")
if not settings.secret_key:
    raise ConfigError("LLM_WIKI_SECRET_KEY 未设置。请生成一个随机字符串：openssl rand -hex 32")
```

---

## 数据库 Schema 与初始化

### SQLite 数据库文件

```
data/
├── users.db           # 用户、项目成员
├── tasks.db           # 任务队列（已在上文定义）
├── audit.db           # 审计日志
└── projects/          # 项目数据（文件系统）
```

### users.db

```sql
-- 初始化时自动创建

CREATE TABLE users (
    id          TEXT PRIMARY KEY,          -- UUID
    username    TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,           -- bcrypt
    display_name TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL DEFAULT 'user',  -- admin | user
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,             -- ISO 8601
    last_login  TEXT
);

CREATE TABLE projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',   -- active | archived
    created_by  TEXT NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE project_members (
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'editor',  -- owner | editor | viewer
    joined_at   TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);

-- 项目设置（JSON 存储，灵活扩展）
CREATE TABLE project_settings (
    project_id  TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    settings    TEXT NOT NULL DEFAULT '{}',      -- JSON blob
    updated_at  TEXT NOT NULL
);
```

### audit.db

```sql
-- 用户操作审计日志（详情见上方审计日志章节）

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,            -- ISO 8601
    action      TEXT NOT NULL,            -- upload | overwrite | move | delete | ingest | graph_build | page_edit | page_rollback | ...
    user_id     TEXT NOT NULL,
    username    TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    target      TEXT NOT NULL,            -- 文件路径或页面路径
    detail      TEXT,                     -- JSON
    result      TEXT NOT NULL,            -- success | failed | partial
    error       TEXT                      -- 失败原因
);

CREATE INDEX idx_audit_project_time ON audit_log(project_id, timestamp);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_action ON audit_log(action);
```

### Schema 迁移

使用 **Alembic** 管理 SQLite schema 版本：

```
backend/
├── alembic/
│   ├── versions/
│   │   ├── 001_initial_users.py
│   │   ├── 002_task_queue.py
│   │   └── 003_project_settings.py
│   └── env.py
└── alembic.ini
```

```bash
# 初始化（首次部署）
alembic upgrade head

# 升级到最新版本
alembic upgrade head

# 回退上一个版本
alembic downgrade -1

# 查看当前版本
alembic current

# 生成迁移脚本（模型变更后）
alembic revision --autogenerate -m "add feature X table"
```

---

## 初始部署流程

### 首次部署步骤

```bash
# 1. 克隆仓库
git clone <repo-url> /opt/llm-wiki
cd /opt/llm-wiki/backend

# 2. 创建虚拟环境
python3.10 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 安装可选 PDF 后端
pip install pymupdf4llm           # 推荐
# pip install marker-pdf          # 复杂排版需要
# pip install arxiv2markdown      # arXiv 论文需要

# 5. 生成配置
cp config.example.yaml config.yaml
# 编辑 config.yaml：设置 data_dir、llm.api_base、llm.api_key

# 6. 生成 JWT 密钥
export LLM_WIKI_SECRET_KEY=$(openssl rand -hex 32)

# 7. 初始化数据库
alembic upgrade head

# 8. 创建管理员
python tools/manage.py create-admin --username admin --password <password>

# 9. 验证安装
python tools/manage.py check
# → [✓] 配置文件有效
# → [✓] 数据目录可写: /data/llm-wiki
# → [✓] LLM 连接成功: deepseek/deepseek-v4-flash @ http://10.0.1.5:8000/v1
# → [✓] 数据库初始化完成
# → [✓] PDF 后端: pymupdf4llm ✓ / marker-pdf ✗ / arxiv2markdown ✗

# 10. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 管理工具

```bash
# 创建管理员
python tools/manage.py create-admin --username admin --password xxx

# 重置密码
python tools/manage.py reset-password --username admin --new-password xxx

# 列出用户
python tools/manage.py list-users

# 禁用/启用用户
python tools/manage.py set-user --username xxx --active false

# 查看系统状态
python tools/manage.py check

# 手动触发全项目 re-ingest
python tools/manage.py refresh-all --project-id xxx

# 清理过期数据（快照、日志、已完成任务）
python tools/manage.py cleanup --dry-run   # 预览
python tools/manage.py cleanup             # 执行
```

### 前端构建与部署

```bash
cd frontend

# 构建
npm install
npm run build          # → dist/

# Nginx 配置
server {
    listen 80;
    server_name wiki.internal.example.com;

    root /opt/llm-wiki/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 环境变量速查

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LLM_WIKI_SECRET_KEY` | ✅ | — | JWT 签名密钥，至少 32 字节随机字符串 |
| `LLM_WIKI_LLM_API_KEY` | ✅ | — | LLM API Key |
| `LLM_WIKI_LLM_API_BASE` | ❌ | `http://localhost:8000/v1` | LLM 接口地址（OpenAI 兼容协议） |
| `LLM_WIKI_LLM_MODEL` | ❌ | `deepseek/deepseek-v4-flash` | litellm model id |
| `LLM_WIKI_LLM_PROVIDER` | ❌ | `openai_compatible` | 提供商标识（deepseek/glm/openai_compatible） |
| `LLM_WIKI_DATA_DIR` | ❌ | `./data` | 数据存储根目录 |
| `LLM_WIKI_PORT` | ❌ | `8000` | 服务监听端口 |
| `LLM_WIKI_WORKERS` | ❌ | `2` | Gunicorn worker 数 |
| `LLM_WIKI_LOG_LEVEL` | ❌ | `INFO` | 日志级别 |

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
| Markdown 渲染 | markdown-it + DOMPurify |
| 图谱渲染 | AntV G6 v5 (离线自托管，MIT 协议) |
| 后端框架 | FastAPI (Python 3.10+) |
| 认证 | JWT (python-jose) |
| LLM 调用 | litellm（OpenAI 兼容协议）→ DeepSeek v4 flash / GLM-47 / 任意兼容模型 |
| 图计算 | NetworkX + Louvain |
| 文件转换 | markitdown |
| 数据库 | SQLite（用户/项目/审计日志） |
| 存储 | 文件系统（wiki/raw/graph） |
| 前端部署 | Nginx 静态托管 + 反向代理 |
| 后端部署 | Uvicorn / Gunicorn |

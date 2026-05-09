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
│   ├── api/                    # 统一请求管理层
│   │   ├── client.ts           # Axios 实例 + 拦截器
│   │   ├── auth.ts             # 认证 API
│   │   ├── files.ts            # 文件管理 API
│   │   ├── ingestion.ts        # 摄入 API
│   │   ├── knowledge.ts        # 知识查询 API
│   │   ├── graph.ts            # 图谱 API
│   │   └── maintenance.ts      # 备份/健康/审计 API
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
│   ├── composables/            # useAuth / useWiki / useGraph
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
- `POST /api/ingestion/trigger` — 触发摄入（单文件或批量）
- `GET /api/ingestion/status/{task_id}` — 摄入进度（5 步分阶段）
- `GET /api/ingestion/history` — 历史记录（含快照状态）
- `POST /api/ingestion/rollback/{task_id}` — 回滚摄入（从快照恢复）

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

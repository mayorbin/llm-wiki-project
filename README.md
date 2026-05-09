# LLM Wiki

基于 LLM 的知识库产品。上传文件 → 自动摄入 → 构建 Wiki 知识库 → 生成知识图谱。支持团队协作、多项目管理和 REST API。

## 架构

```
浏览器 (Vue3 SPA) → Nginx :80 → FastAPI :8000 → SQLite + 文件系统 + LLM
```

前后端分离部署。后端三层架构（API → Service → Engine），前端暖奶油极简文档风格。

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url>
cd llm-wiki-project
```

### 2. 安装后端

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. 配置

**必须**设置两个环境变量：

```bash
# LLM API 密钥（DeepSeek / GLM-47 / 任意 OpenAI 兼容接口）
export LLM_WIKI_LLM_API_KEY=sk-your-key

# JWT 签名密钥（生成随机字符串）
export LLM_WIKI_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

可选：设置 LLM 接口地址（默认 `http://localhost:8000/v1`）：

```bash
export LLM_WIKI_LLM_API_BASE=http://your-llm-server:8000/v1
export LLM_WIKI_LLM_MODEL=deepseek/deepseek-v4-flash   # 或 glm/glm-47
```

三种配置方式（优先级：环境变量 > `.env` > `config.yaml`）：

**方式一：`.env` 文件（推荐开发环境）**

```bash
cp .env.example .env
# 编辑 .env，填入实际值
```

**方式二：`config.yaml`（推荐生产环境）**

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml，替换 ${LLM_WIKI_LLM_API_KEY} 等占位符
```

**方式三：系统环境变量**

直接设置环境变量，优先级最高，适合 Docker / systemd 部署。

### 4. 启动后端

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

验证：

```bash
curl http://localhost:8000/api/ping
# → {"status":"ok","version":"0.1.0"}
```

### 5. 安装前端

```bash
cd frontend
npm install
```

### 6. 启动前端

```bash
npm run dev
```

浏览器打开 `http://localhost:5173`。

### 7. 构建生产版本

```bash
cd frontend && npm run build   # → dist/
```

Nginx 配置参考 `deploy/nginx.conf`。Docker 部署参考 `deploy/docker-compose.yml`。

## 配置参考

| 环境变量 | 必填 | 默认值 | 说明 |
|---------|------|--------|------|
| `LLM_WIKI_LLM_API_KEY` | ✅ | — | LLM API 密钥 |
| `LLM_WIKI_SECRET_KEY` | ✅ | — | JWT 签名密钥（≥32 字节随机字符串） |
| `LLM_WIKI_LLM_MODEL` | ❌ | `deepseek/deepseek-v4-flash` | litellm model id |
| `LLM_WIKI_LLM_API_BASE` | ❌ | `http://localhost:8000/v1` | LLM 接口地址 |
| `LLM_WIKI_LLM_PROVIDER` | ❌ | `openai_compatible` | 提供商标识 |
| `LLM_WIKI_DATA_DIR` | ❌ | `./data` | 数据存储根目录 |
| `LLM_WIKI_PORT` | ❌ | `8000` | 服务端口 |
| `LLM_WIKI_LOG_LEVEL` | ❌ | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `LLM_WIKI_LLM_TEMPERATURE` | ❌ | `0.3` | LLM 温度参数（0.0-2.0） |
| `LLM_WIKI_LLM_MAX_TOKENS` | ❌ | `8192` | 最大输出 token 数 |
| `LLM_WIKI_LLM_TIMEOUT` | ❌ | `120` | LLM 调用超时（秒） |

启动时若缺少 `LLM_WIKI_LLM_API_KEY` 或 `LLM_WIKI_SECRET_KEY`，服务会报错退出。

## 支持的大模型

所有兼容 OpenAI Chat Completions 协议的模型均可使用（通过 [litellm](https://github.com/BerriAI/litellm) 统一入口）：

| 模型 | 配置 |
|------|------|
| DeepSeek v4 flash | `model: deepseek/deepseek-v4-flash` |
| GLM-47 | `model: glm/glm-47` |
| vLLM / Ollama | `model: openai/<name>` |

项目级可覆盖模型参数（temperature、max_tokens 等），无需重启服务。

## 项目结构

```
├── backend/               # Python FastAPI 后端
│   ├── app/
│   │   ├── main.py        # 应用入口 + 健康检查
│   │   ├── config.py      # 配置管理（多优先级）
│   │   ├── api/           # 路由层（7 个模块）
│   │   ├── services/      # 业务逻辑层
│   │   ├── engines/       # 核心引擎（LLM/Wiki/Graph/Convert）
│   │   ├── models/        # Pydantic 数据模型
│   │   └── storage/       # SQLite + 文件系统封装
│   ├── tests/unit/        # 209 个单元测试
│   └── config.example.yaml
│
├── frontend/              # Vue3 + TypeScript 前端
│   ├── src/
│   │   ├── views/         # 页面组件（5 个）
│   │   ├── api/           # API 客户端（7 个模块）
│   │   ├── stores/        # Pinia 状态管理
│   │   ├── router/        # Vue Router + 导航守卫
│   │   ├── composables/   # 自适应轮询 composable
│   │   └── lib/           # markdown-it + DOMPurify
│   └── tests/
│
├── deploy/                # 部署配置
│   ├── nginx.conf
│   ├── docker-compose.yml
│   └── Dockerfile.backend
│
├── docs/                  # 设计文档 + 实现计划
└── llm-wiki-agent/        # 参考项目（不依赖）
```

## API 端点

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/refresh` | 刷新 Token |
| GET | `/api/auth/me` | 当前用户信息 |
| POST | `/api/auth/logout` | 登出 |

### 项目管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects` | 项目列表 |
| POST | `/api/projects` | 创建项目 |
| PATCH | `/api/projects/{id}` | 更新项目 |
| DELETE | `/api/projects/{id}` | 删除项目 |
| GET | `/api/projects/{id}/members` | 成员列表 |
| POST | `/api/projects/{id}/members` | 添加成员 |
| POST | `/api/projects/{id}/transfer` | 转让所有权 |
| GET/PATCH | `/api/projects/{id}/settings` | 项目设置 |
| GET | `/api/projects/{id}/health` | 项目健康检查 |

### 文件管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/DELETE | `/api/files/dirs` | 目录管理 |
| POST | `/api/files/upload` | 上传文件 |
| GET | `/api/files` | 文件列表 |
| GET | `/api/files/{id}/download` | 下载文件 |
| DELETE | `/api/files/{id}` | 删除文件 |
| POST | `/api/files/move` | 移动文件 |
| POST | `/api/files/detect-changes` | 检测变更 |
| POST | `/api/files/refresh` | 重新摄入 |

### 摄入
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ingestion/trigger` | 触发摄入 |
| POST | `/api/ingestion/retry/{id}` | 重试 |
| GET | `/api/ingestion/status/{id}` | 进度查询 |
| POST | `/api/ingestion/rollback/{id}` | 回滚 |

### 知识查询
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/knowledge/query` | LLM 问答 |
| GET | `/api/knowledge/pages` | 页面树 |
| GET | `/api/knowledge/pages/{path}` | 读取页面 |
| PUT | `/api/knowledge/pages/{path}` | 编辑页面 |

### 图谱
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/graph/data` | 图谱数据 |
| POST | `/api/graph/build` | 构建图谱 |
| GET | `/api/graph/stats` | 统计信息 |

### 维护
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/backup/export` | 导出备份 |
| POST | `/api/backup/import` | 导入备份 |
| POST | `/api/lint` | 语义检查 |
| GET | `/api/audit-log` | 审计日志 |
| GET | `/api/ping` | 存活探针 |
| GET | `/api/health` | 就绪探针 |

### 全局管理（Admin only）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PATCH/DELETE | `/api/admin/users*` | 用户管理 |
| GET | `/api/admin/projects` | 全平台项目 |
| POST | `/api/admin/projects/{id}/takeover` | 接管项目 |

## 角色权限

| 角色 | 权限 |
|------|------|
| **Owner** | 全部权限（含删除项目、转让所有权、管理成员） |
| **Editor** | 上传/摄入/管理文件/编辑 Wiki/构建图谱/导出备份 |
| **Viewer** | 只读查询、浏览 Wiki、查看图谱、下载文件 |
| **Admin** | 全局跨项目权限（用户管理、接管无主项目、全平台审计日志） |

## 文档

- [设计规格文档](docs/superpowers/specs/2026-05-08-llm-wiki-product-design.md)
- [实现计划](docs/superpowers/plans/2026-05-09-llm-wiki-product.md)

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + Pinia + AntV G6 v5 + markdown-it + DOMPurify |
| 后端 | FastAPI (Python 3.10+) + litellm + NetworkX + markitdown |
| 存储 | SQLite (WAL) + 文件系统 (Markdown) |
| 认证 | JWT (HS256) + bcrypt |
| 部署 | Nginx + Docker Compose |

## License

MIT

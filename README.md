# daedalus-runner

大福的跑腿小弟。一套完整的"派活 → 干活"agent 执行栈。

> 2026-10-10 由 Daedalus（Rust 执行引擎）+ hermes-delegate-runtime（Python 派活层）合并而成。
> 合并原因：两个项目实际绑定使用，分开只会造成误会。

## 架构

```
大福（Muse）
 └─ dispatch/ ── 派活层（Python）
 │    TaskSpec → 选 backend → 批量派发 → 收结果
 │    后端：DaedalusBackend → HTTP POST /api/tasks
 └─ daemon/ ─── 执行层（Rust）
 │    daedalusd：agent loop → 调工具 → 调 LLM → outbox → SQLite
 └─ proxy/ ──── 凭证层（Python）
      本地 8899 → 注入保险库凭证 → opencode-go → LLM
```

## 三档 agent（config/managed-agents.yaml）

| agent | 模型 | 用途 | 成本 |
|-------|------|------|------|
| trivial-worker | longcat-2.5-preview-free | 杂活：格式、测试、文件操作 | 免费 |
| code-worker | deepseek-v4-flash | 写代码、修 bug | $0.15/1M |
| think-worker | deepseek-v4-pro | 设计、review | $0.66/1M |

路由：大福按任务难度选档（人肉网关 v0.1）。

## 工具（daemon）

daemon 内置工具（`daemon/daedalusd/src/tools/`）：

| 工具 | 用途 |
|------|------|
| file_read / file_write | 读 / 写工作区文件 |
| terminal | 执行 shell 命令 |
| web_fetch | 抓网页，去 HTML 取正文 |
| web_search | Tavily 搜索：走本地代理 :8899 注入凭证，返回标题/链接/摘要，查资料、查文档、查时事 |
| task_done | 收尾：summary + 改动文件清单 |

## 启动

```bash
bash scripts/start-all.sh
# 代理 :8899 → daemon :9800，健康检查 http://127.0.0.1:9800/api/health
```

## 派活（Python）

```python
import sys; sys.path.insert(0, 'dispatch')
from tools.delegate_runtime import TaskSpec, DaedalusBackend
b = DaedalusBackend(base_url='http://127.0.0.1:9800')
rid = b.dispatch(TaskSpec(agent_id='code-worker', goal='...'))
result = b.get_result(rid)  # 轮询
```

## 自愈机制

派活前自动体检（`dispatch/tools/delegate_runtime/backend.py` 的 `ensure_daedalus_alive`）：
检查 daemon（:9800/api/health）和代理（:8899/v1/models），哪个挂了就跑 `scripts/start-all.sh` 自动拉起，等 3 秒复检。
体检跑在调用方进程里，死不了。可用环境变量 `DAEDALUS_NO_AUTOHEAL=1` 关掉。

## 目录

| 目录 | 内容 | 来源 |
|------|------|------|
| `daemon/` | Rust 执行引擎（daedalusd + CLI） | gu87/daedalus |
| `dispatch/` | Python 派活库 | gu87/hermes-delegate-runtime（含 v0.3 适配补丁） |
| `proxy/` | auth 代理 + 启动脚本 | 新写 |
| `config/` | models.yaml / managed-agents.yaml / SOUL.md | 运行配置 |
| `scripts/` | start-all.sh | 启动脚本 |

## 注意

- `daemon/target/` 未包含，重编：`cd daemon && cargo build`
- 原仓库（gu87/daedalus、gu87/hermes-delegate-runtime）保留不动，这是本地统一工作区
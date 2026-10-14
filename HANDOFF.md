# DeepAgents 课程项目交接文档

> 更新日期：2026-10-15
> 课程：Datawhale《Deep Agents 实战》 https://datawhalechina.github.io/deepagents-in-action/
> 进度：pre01 完成；pre02 开发技能已装入项目（详见 §10）；待办 3/4 进行中

---

## 1. 当前状态（一句话）

教程 pre01 已完整跑通：在 **WSL2 Ubuntu** 中通过 agentseek 创建了 `deepagents/research` 模板项目，前后端可启动，研究 Agent 已能出带来源的研究报告。持久化使用**教程原版的内嵌 SeekDB**（Linux 生效）。

## 2. 两套环境（最重要的边界）

| | Windows 原生（旧路线，已废弃） | WSL2 Ubuntu（现役） |
|---|---|---|
| 项目位置 | `F:\学习\项目尝试\deepagents\research_deepagent` | `~/projects/research_deepagent`（WSL 内） |
| 持久化 | SQLite 降级（`SEEKDB_EMBED=false`） | 内嵌 SeekDB（默认 `true`） |
| 状态 | **待删除**（见 §6） | ✅ 现役 |
| Python | `代码\.venv`（hello_world 实验用，保留） | uv 管理（`uv tool` + 模板自带 `.venv`） |

**边界规则（教程明确要求）：**
- 项目只放 WSL 的 Linux 文件系统（`~/projects/`），**不要**放 `/mnt/c`、`/mnt/d` 下；
- **不混用** Windows 与 WSL 的 Python / uv / Node.js / npm / Git；
- 项目命令（agentseek、npm 等）只在 **Ubuntu 终端**跑（提示符 `wangsuhan@LAPTOP-21UKF654:~$`）；
- PowerShell 只做 Windows 侧操作（`wsl -l -v`、删文件等）；
- VS Code 使用方式：Ubuntu 终端里 `cd ~/projects/research_deepagent && code .`，窗口左下角出现 `WSL: Ubuntu` 才是正确打开方式。

## 3. WSL 内环境明细

- WSL2 + Ubuntu，VERSION=2（`wsl -l -v` 验证过）；Linux 用户 `wangsuhan`
- uv：`~/.local/bin`（curl 脚本安装）
- agentseek v0.1.6：`uv tool install --upgrade agentseek`
- Node v22.14.0：**手动 tar 包装在 `/usr/local`**（npmmirror 下载）；注意 Windows 的 npm（`/mnt/d/nodejs/npm`）会混进 PATH，`which npm` 必须指向 `/usr/local/bin/npm`
- npm 镜像：npmmirror（已 `npm config set registry`）
- Python 包镜像：阿里云（单次命令带 `UV_INDEX_URL=...` 前缀）

## 4. 网络边界（反复踩过的坑）

- **GitHub 直连不稳定**：`git ls-remote` 通，但大文件克隆会断（GnuTLS 错误）。
- 已做：`git config --global http.version HTTP/1.1` + `http.postBuffer 524288000`（WSL 内 git）。
- 模板仓库已克隆到 WSL：`~/agentseek-templates`（main 分支）。**重建项目用本地路径**：
  ```bash
  agentseek create ~/agentseek-templates/templates/deepagents/research --no-input
  ```
  教程的 `--checkout main` 需要 agentseek 另行拉取目录仓库，会失败（`catalog repository fetch failed`），故不用。
- WSL 内走 Windows 代理**未配置成功**（需代理软件开 Allow LAN + 用宿主机 IP 172.22.x.x，不是 127.0.0.1）；目前所有流程已绕开对代理的依赖。
- PyPI/npm/GitHub 慢或断时：PyPI 用阿里云镜像、npm 用 npmmirror、git 用 HTTP/1.1 重试。

## 5. 凭据（只记位置，本文档不存明文）

- 模型 key / 接口地址 / 模型 ID：现役配置在 `~/projects/research_deepagent/.env`（抄自旧 Windows 项目同名文件）
- TAVILY_API_KEY：同在上述 `.env`；**注意：曾在截图中暴露过，建议去 app.tavily.com 轮换**
- LangSmith：见 §10 的最新状态。启用需在 `.env` 中：
  ```env
  LANGSMITH_TRACING=true
  LANGSMITH_API_KEY=<key>
  LANGSMITH_PROJECT=deepagents-course
  ```

## 6. 待办清单（按优先级）

1. **轮换 Tavily key**（截图泄露过）——需用户在 app.tavily.com 操作；
2. **删除 Windows 侧旧项目** `F:\学习\项目尝试\deepagents\research_deepagent`（确认 WSL 侧稳定后再删）；
3. **卸载 Windows 侧 agentseek**：PowerShell 执行 `uv tool uninstall agentseek`（uv 本身建议保留）；
4. pre02：开启 LangSmith Trace，重新跑一次研究，用 `langsmith-trace` 技能分析。

## 7. 日常操作速查（都在 Ubuntu 终端、项目目录内）

```bash
cd ~/projects/research_deepagent
agentseek doctor          # 静态体检
agentseek dev             # 启动前后端（终端保持开着）
agentseek doctor --live   # 另开终端验证服务在线
# 浏览器：http://127.0.0.1:5174（WSL2 端口自动转发到 Windows）
```

- 重装前端依赖（换 node/npm 后需要）：`rm -rf frontend/node_modules && agentseek task frontend`
- 后端依赖：`UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple agentseek task sync`
- **改 `.env`（模型 / key / base 地址）后必须重启 `agentseek dev` 才生效**：模型配置在进程启动时读死（`src/research_deepagent/agent.py` 模块导入时 `load_dotenv()` 并构造模型客户端），uvicorn 的 `--reload` 只监听 `.py` 文件，不监听 `.env`。
- **Ctrl+C 停不掉后端**：`agentseek dev` 被中断时只杀了父进程和前端 vite（5174），2024 后端与 SeekDB 是守护化子进程会残留，且仍带旧配置。彻底重启：
  ```bash
  pkill -f agentseek-api; pkill -f agentseek_api.runtime_entrypoint; pkill -f pylibseekdb/seekdb
  agentseek dev
  ```
  （2026-10-15 踩过：半重启后浏览器 5174"拒绝连接"，后端仍报旧模型的 403 免费额度错误。）

## 8. 已知问题与无关紧要的噪音

- 后端启动时打印 `SHOW FULL TABLES ... unsupported syntax. Falling back` —— SeekDB 初始化的无害警告，忽略；
- `[sample_graphs] skipped xxx: No module named 'graphs'` —— 无害，忽略；
- LangSmith Studio 顶部"Upgrade your agent server"黄条 —— 版本提示，忽略；
- Windows 侧 PATH 会渗入 WSL（`/mnt/d/nodejs`），已通过在 `/usr/local` 装 Linux node 压过优先级；彻底隔离可改 `/etc/wsl.conf` 的 `[interop] appendWindowsPath=false`（未做，不影响使用）。

## 9. 边界：本交接不覆盖的内容

- `代码\` 目录下的 hello_world 实验（`deepagents` 库直用路线）与课程模板是**两套独立东西**，未合并，也不需要合并；
- 教程后续章节（pre02 起）的实操未开始；
- Docker、远程 SeekDB/OceanBase、向量检索增强：课程不需要，仅在未来需要"语义记忆/RAG"时再考虑（方案已讨论：Docker 跑向量库或 WSL 内嵌，见会话记录）；
- 代理软件的 Allow LAN 修复：未做，因为现有流程已绕开。

## 10. 2026-10-15 增补（ZCode 会话）

- **pre02 技能安装已完成**：`langchain-dev-guide`、`langsmith-trace` 已由 skills CLI 装入 `.agents/skills/`（含 `skills-lock.json`），`.claude/skills/` 有软链接；ZCode 原生读取 `.agents/skills/`，两个技能在 ZCode 会话中已生效。
- **交接文档本身已存入 WSL 项目**（本文件），后续以此文件为准。
- 待办 3/4 执行结果见本节追加。

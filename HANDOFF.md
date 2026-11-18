# 给接手 Agent：先读这里

## 暂停状态

用户要求：“先暂停，把目前所有做完和未完成的都打包上传到 Git，回家继续；不仅要展示，也要代码。”

本 checkpoint 保留全部自编代码。**不要继续假设上一版已经可交付。先报告现状，再根据用户指令继续。**

GitHub 目标账号：`azhang50-commits`。两个已连接的 GitHub MCP 账号属于其他身份，不要用它们代替目标账号写入。

## 用户需求如何收敛

用户负责 BoxLite 的 GTM/SEO/建联，希望做一个可以给潜在客户直接看的产品 demo。

用户否定了：文章上下文工具、软件评测代理、建联名单工作台，以及预制落地页实验室——这些方案与 BoxLite 的独立环境卖点关系弱。

当前目标是 **真实的独立执行环境对比**。用户再次强调：只有日志、点击“运行”而看不懂代码没有意义；要像游戏或视频一样，亲眼看到卡住、坏掉和另一个任务是否被影响。

最终正在开发的方案：两个实际运行在 Box 里的自动弹球游戏。正常物理、碰撞与得分在 Python 游戏进程内推进；浏览器只读取状态并绘制。

## 真实资源与架构

| 角色 | Box ID | 说明 |
|---|---|---|
| A / worker | `FouKpyrRRw8u` | 原始 playground；执行文件测试和游戏 A，shared 模式也运行 B |
| B / controller | `Njek7EQEp57M` | 承载 HTTP 服务、固定任务调度与 isolated 模式游戏 B |
| 旧失败部署 | `nOaK7jwG7l9O` | 保留、已停止过；不要假设已删除，不要未经授权销毁 |

两个主要 Box 为 1 CPU / 512 MiB，原配置闲置 300 秒自动停止。未设置无限常驻。

网页和后端在 Box B `/app`：

- `/app/server.py`：HTTP 路由。
- `/app/isolation/`：项目代码。
- `/app/isolation/play/`：游戏 UI。
- `/home/boxlite/box-meaning-private/config.json`：真实服务端密钥配置，权限 600，位于网页目录外。
- `/home/boxlite/isolation-lab/<run>/`：虚构文件隔离测试数据、真实脚本和结果。
- `/home/boxlite/game-lab/game_worker.py`：两个 Box 中实际启动的游戏脚本。

游戏状态公开端口：

- A：`https://9101-d-466f754b7079725252773875.proxy.boxlite.ai`
- shared B（与 A 同一个 Box）：`https://9102-d-466f754b7079725252773875.proxy.boxlite.ai`
- isolated B：`https://9102-d-4e6a656b374551457035374d.proxy.boxlite.ai`

状态入口为 `/state`，含 round ID、Box ID、PID、实际 tick、score、球和砖块状态。CORS 为 `*`，只暴露虚构游戏状态，不接受任意代码。

## 已完成并验证的部分

### 文件隔离版本（旧的可运行阶段）

- 用同一段 `agent_task.py` 分别执行共享/独立实验。
- A 正常统计 70 条线索，同时尝试跨任务读取/删除 B 的 `private.txt`。
- 共享：在同一个 Box 中放 A/B 文件，A 读到并删除 B 文件，B 的 `task_b.py` 因缺文件失败。
- 独立：B 文件与 B 的任务在另一台真实 Box 中；A 找不到该文件，B 的任务仍成功。
- 网页触发新一轮运行、两种模式切换、文件/代码快照、实际 Box ID、原始 JSON 下载曾验收通过。
- 见 `evidence/evidence.json`，run ID `ee8719f1c649`。
- `evidence/shared.jpg` 和 `evidence/isolated.jpg` 是**文件实验**截图，不是游戏截图。

### 游戏版本（当前 WIP）

已写：

- `game_worker.py`：标准库 HTTP 服务 + 约 40Hz 的真实弹球状态推进，自动操控挡板，观众可同时观察两局。
- `game_backend.py`：启动 shared/isolated 两种布局；通过 BoxLite API 在 A 执行固定故障命令。
- 故障命令只匹配 `/home/boxlite/game-lab/game_worker.py` 的演示游戏进程，不匹配网页服务、其他程序或本机进程。
- shared 时 A/B 是同一 Box 内的两个真实进程；故障清理命令停止两者。
- isolated 时 A 游戏在 A Box，B 游戏在 B Box；命令仅在 A 执行；后端用 B tick 增长验证它继续运行。
- 游戏前端有“启动”“让 A 出故障”“带我看一遍”、状态、帧、PID、Box ID、代码说明、证据下载。
- 主入口 `index.html` 已改为重定向 `play/`；旧页面保留为 `files.html`。
- 操作采用异步 job，前端 80 秒等待上限、请求超时；后端 GameEngine 有 65 秒截止时间。
- 用户明确同意把 API Key 存在 B 的私密服务端配置。实际 Key 没有归档。

已实测：

```text
STARTED shared 7690769f8053
VERIFIED shared killed [3, 6] B_STOPPED True
```

这次确认两个游戏的 tick 都增长，之后故障代码停止 A/B 两个进程。

## 尚未完成 / 不能声称验证过

1. `qa_games.py` 切换到 isolated 的启动轮询遇到 HTTP 502，脚本中断。
2. 因此没有完整的 `game-evidence.json`；不能称“独立游戏已全部验收通过”。
3. 没有对最新游戏 UI 做完整浏览器验收，包括跨域状态读取、游戏画面、故障后 B 持续运动、自动完整演示、手机布局。
4. 最后补了 `touch_controller()`：只在用户显式 start/fault 时向控制 Box 执行 `true`，刷新活动时钟，避免演示中闲置停止；不改无限常驻配置。
5. 最后也补了前端竞态：故障确认后，不允许较早在途的 HTTP 帧响应把“进程已停止”覆盖回“运行中”。
6. 最后部署正在运行时，用户要求暂停；工具执行被中断，没有拿到该次部署的最终返回值。**本地源码是最新的，远程可能是部分或完整更新，必须重新核对。**
7. `CURRENT` 和 job map 在内存中，B 重启后丢失；保存了 `play/last-session.json`，但当前还没有完整恢复逻辑。
8. `qa_games.py` 会写 `outputs/box-demo/game-evidence.json`，新 clone 先 `mkdir -p outputs/box-demo`。
9. `GameEngine.api` 的 urllib 超时不等同 DNS 的硬截止。虽然不再改网络策略，仍应检查整体任务不会无限等待。
10. API 冷启动和预览代理有间歇性 502/连接延迟；不能用前端动画掩盖失败。

## 建议接手后的第一轮工作

不要先继续画 UI，先把以下真实闭环跑通：

1. 确认本地源码与远程文件是否一致，读取两个 Box 当前状态。
2. 确认 A 出站仍为 enabled/空 allowlist，B 运行正常；不再做网络开关实验。
3. 按 README 配置本机私密 key 与 controller-config；不要提交它们。
4. 核对现有 `game_urls`，仅必要时重新运行 `setup_game_tunnels.py`。
5. 将最终代码重新部署，确认 HTTP 服务已重启并加载 `game_backend.py`。
6. 跑 `qa_games.py`，保存 shared 和 isolated 的完整结果；GET 502 可重试，POST 不要盲目重发导致重复操作。
7. 打开 `/isolation/play/`：先 shared，真实看到两局动，触发故障，确认都停；再 isolated，确认只有 A 停，B 的 tick/得分继续增长。
8. 验证“带我看一遍”确实调用真实 API，不播放假结果；失败应清楚显示错误并允许重试。
9. 修复卡住体验：所有请求有期限、任务可观察、模式切换不会展示旧场景为新场景。
10. 保存真实游戏截图、下载 JSON，更新 README 的完成状态，再交付。

## 部署工具细节

本机当时用 Python 3.12 + `boxlite==0.11.0`。SDK 的 WebSocket stdout/wait 曾返回 -1 或网络错误；REST 创建 execution 后轮询状态、下载 JSON 文件更可靠，部署脚本已采用这个路径。

`deploy_isolation.py`：

- 读取本机 `work/boxlite-connect/credentials.json`。
- 合并并保存本机私密 controller-config。
- 上传 `work/box-demo` 到 B `/app/isolation`，上传 `work/box-root/server.py` 到 `/app/server.py`。
- API Key 通过 SDK 文件复制放到网页目录外，权限 600。
- 仅停止精确命令行 `python3 -u /app/server.py` 的旧网页进程，让 PID1 的监督循环重新启动它，不停整台 Box。
- 保留早期 `work/` 布局，避免改路径让工具无法找到源码。

首次下载 SDK 时本机 Python pip 的 CA 不正常；系统 `/usr/bin/curl` TLS 可用。曾从 PyPI 官方下载 macOS arm64 wheel 再本地安装。这个归档不含该二进制或虚拟环境。新机器优先正常 pip 安装，不要直接关 TLS 校验。

## 不要重复的方向与操作

- 不要把“能联网/不能联网”当成“独立/不独立”。用户明确纠正过。
- 先前的整机出站 disabled 测试没有完成，还一度遗留 A disabled；后来已显式恢复 enabled/空 allowlist。后续代码已移除网络实验。
- 不要用文件夹分开就声称独立虚拟机；页面必须显示真实 Box ID/代码/进程。
- 不要假装模型正在生成代码：本版是固定可审计脚本，模型接口仅预留。
- 不要把共享对照说成“所有普通云服务器都不安全”。普通独立 VM 也能隔离，卖点是 BoxLite 的 SDK/API 与环境管理。
- 不要在持有 API Key 的控制 Box B 中开放任意用户代码执行。若以后加入代码编辑器，执行应限制到 A 或新的独立 worker，并另做资源/权限设计。
- 不要未经用户明确指示删除已有 Box。自动审批以前拒绝了删除旧环境；旧失败 Box 被保留。
- 不要设置无限常驻；以前自动审批拒绝了关闭自动停止的长期公开运行配置。

## 权限和 Git

本地真实密钥不在归档；新机器需要用户通过私密方式提供。远程私密配置已经由用户明确授权，但这不授权把密钥提交到 Git。

本工具执行环境里没有可用 `gh` 或现成 Git credential；原目录不是 Git 仓库。用户指定的目标账号是 `azhang50-commits`，Chrome 的该账号已登录。当前正在做交接上传，而非继续产品开发。

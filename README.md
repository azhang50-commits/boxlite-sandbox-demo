# BoxLite Sandbox Demo — complete handoff

完整代码已打包，包含已完成和未完成部分；不是只有展示页面。

- **`boxlite-complete-source.zip`**：62 个源码/文档/证据文件，保留原 `work/` 目录布局。
- **`boxlite-complete.bundle`**：完整本地 Git 仓库快照，可直接恢复全部源码和提交。
- **[HANDOFF.md](HANDOFF.md)**：接手 agent 必须先读，列明已完成、未完成、已验证、未验证、部署资源、问题和下一步。
- **[AGENTS.md](AGENTS.md)**：接手约束。

## 回家继续

```sh
git clone https://github.com/azhang50-commits/boxlite-sandbox-demo.git
cd boxlite-sandbox-demo
git clone boxlite-complete.bundle boxlite-source
cd boxlite-source
```

也可以直接解压 `boxlite-complete-source.zip`。恢复后先读 `HANDOFF.md` 和源码根目录 `README.md`。

## 暂停时状态

文件隔离实验已验证；真实双游戏的共享模式已验证。独立游戏、完整自动演示和最终热修复部署还未完成验收，不能当作完成版。用户要求在此暂停。

API Key、实际认证配置、虚拟环境和 SDK 二进制没有上传。家里的机器需要通过私密方式配置密钥。

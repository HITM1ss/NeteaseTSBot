# Repository Guidelines（仓库指南）

## 项目结构与模块组织

- `backend/`：Python/FastAPI API、数据模型、音乐源适配器和语音服务客户端。
- `web/`：Vue 3 + TypeScript + Vite 控制台（包括 `web/src/components/`、`web/src/views/` 和工具模块）。
- `voice-service/`：Rust TeamSpeak 音频客户端与 gRPC 服务；`proto/` 存放服务定义。
- `tests/`：后端回归测试和管理员配置测试；`vendor/`：固定版本的本地 Rust crate。
- 根目录中的 `Makefile`、`Dockerfile*`、`docker-compose*.yml`、`run-*.sh` 和 `scripts/` 提供部署辅助功能；运行时数据和日志已被忽略。

## 构建、测试与开发命令

- `make backend-setup`：创建 `backend/.venv` 并安装 Python 依赖。
- `npm --prefix web ci && npm --prefix web run build`：安装前端依赖并构建生产包。
- `cargo build --manifest-path voice-service/Cargo.toml`：构建 Rust 服务；`make all` 执行完整的安装与构建流程。
- `backend/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`：运行后端测试套件。
- 本地开发按需运行 `backend/.venv/bin/uvicorn backend.main:app --reload`、`npm --prefix web run dev` 和 `./run-voicemake.sh`。`docker compose up -d --build` 可验证打包后的服务栈。

## 编码风格与命名约定

Python 使用 4 个空格和类型标注；函数、模块采用 `snake_case`，类采用 `PascalCase`。测试类以 `Tests` 结尾，测试方法以 `test_` 开头。TypeScript/Vue 遵循现有的 2 空格缩进，值和函数使用 `camelCase`，组件文件使用 `PascalCase.vue`。Rust 提交前运行 `cargo fmt`；不要手动编辑 `backend/_generated/` 等生成文件。

## 测试指南

使用 `unittest` 在 `tests/` 下添加针对性回归测试；使用 mock、临时 SQLite 数据库和临时文件，避免依赖真实音乐 API 或 TeamSpeak。提交前运行完整测试发现命令。前端和语音服务改动至少应通过 `npm --prefix web run build` 与 `cargo build --manifest-path voice-service/Cargo.toml`；仓库未设置覆盖率门槛。

## 提交与拉取请求指南

遵循现有的 Conventional Commit 格式，例如 `feat(admin): add ...`、`fix(auth): ...` 或 `docs(config): ...`；主题应简短、使用祈使语气并注明作用域。PR 应说明影响、列出涉及模块、附上测试/构建结果，并注明配置或迁移变更。界面改动请附截图、关联 Issue，并脱敏 Cookie、Token、凭据和敏感日志。

## 安全与配置提示

将 `tsbot.env.example` 复制为 `tsbot.env`；不要提交该文件、Cookie、Token、数据库或日志。管理员凭据和生成的运行时文件都应视为机密，附在 Issue 或 PR 中的诊断输出必须先脱敏。

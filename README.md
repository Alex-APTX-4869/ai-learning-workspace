# AI Learning Workspace · 学习空间

An AI-assisted personal learning workspace built with Vue 3, TypeScript, FastAPI, and PostgreSQL.

它把课程规划、AI 生成目录、知识点管理和学习阅读整合在一个“璃云白”界面中，并通过持久化、并发校验和结构化模型输出保证内容可靠保存。

## 项目亮点

- 前后端分层：Vue 3 Composition API + TypeScript，FastAPI + SQLAlchemy 2.0。
- AI 结构化生成：Pydantic 校验模型返回，异常或脏数据不会写入数据库。
- 数据一致性：生成期间检测课程变更，避免旧结果覆盖新内容。
- 可恢复体验：路由可刷新、课程内容持久化、错误状态可重试。
- 自动化验证：后端覆盖核心课程流程，前端构建包含 TypeScript 检查。

## 当前可用

- 创建、搜索、编辑课程，以可刷新、可复制地址的卡片链接进入课程目录。
- 生成章节和小节，再按章生成知识点；成功后自动保存到 PostgreSQL。
- 点击小节打开学习弹窗，左侧切换知识点，右侧阅读已有简介。
- 刷新、返回列表、切换课程时保留已保存内容。

参考资料上传、完整讲义与练习制作、Python 运行和 AI 辅导尚未实现。界面相应位置明确显示“待接入”，具体设计见下方文档。

## 本地启动

克隆仓库后，在项目根目录创建 Python 环境并安装后端依赖：

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
python -m uvicorn backend.main:app --reload
```

按需填写 `.env` 中的 PostgreSQL 和模型配置。另开一个终端安装并启动前端：

```sh
cd frontend
npm ci
npm run dev
```

访问 http://localhost:5173 。需要本机 PostgreSQL 正在运行，且 `.env` 包含 `DATABASE_URL`、`NUS_API_KEY`、`NUS_URL`、`NUS_MODEL`。密钥只由后端读取，仓库只保留无密钥的 `.env.example`。

前端开发服务器把 `/api` 请求转给 `http://127.0.0.1:8000`。首页只请求课程摘要，进入课程才请求完整目录。发布构建时需要配置同源 `/api` 反向代理，或者构建前设置 `VITE_API_BASE_URL` 并调整后端允许的来源。Vite 的开发代理不会随静态构建部署。

若默认端口被其他项目占用，可以把后端启动在 `8001`，再这样启动前端：`VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174`。

已有表直接复用，启动时只创建缺失表。旧版内存中的课程不会自动成为数据库记录；本次改版没有清空数据库。旧版 `POST /ai/course-outline` 和 `/ai/chapter-points` 保留为不保存的生成接口，新界面使用带课程 ID 的保存接口。

## 结构和后续方案

- [目录与职责](docs/architecture.md)
- [内容制作与资料库](docs/agent-roadmap.md)

从 `frontend/src/pages/` 阅读页面组合，再进入 `features/` 看对应功能。后端从 `backend/main.py` 开始，沿路由、服务、数据模型阅读；AI 提示词集中在 `backend/ai/prompts.py`。

## 检查

```sh
pip install -r backend/requirements-dev.txt
python -m unittest backend.tests.test_courses -v
```

测试使用独立临时数据库，并替代真实模型调用，不消耗 NUS 额度。

前端在 `frontend` 目录运行 `npm run build`，同时完成 TypeScript 检查和正式构建。

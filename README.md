# 学习空间

Vue 3 + TypeScript + FastAPI + PostgreSQL 的个人 AI 学习工作台，采用“璃云白”界面。

## 当前可用

- 创建、搜索、编辑课程，以可刷新、可复制地址的卡片链接进入课程目录。
- 需求确认支持 Agent 申请补问、用户审批；选项解释以 Markdown 流式显示。
- 创建课程前由 AI 给出三档需求确认深度，也可自定义题数；逐题回答并确认需求档案后才创建课程。
- 创建第一步可上传 PDF/DOCX/图片，标注总述、指定章节、补充参考及 PDF 页段；先查看解析问题，再分段分析资料并开始需求确认。
- 资料解析/分析在后台进行，支持刷新恢复、显式重试与已完成摘要复用；课程内可回看原文件、标注和解析报告。
- 生成章节和小节，再按章生成知识点；成功后自动保存到 PostgreSQL。
- 点击小节打开学习弹窗，左侧切换知识点，右侧阅读简介和已生成内容。
- 按需生成讲解卡片、示例、练习与 Python 代码实验，支持自主阅读和交互讲师带学。
- 带学将知识卡片与问答放在同一对话列；选择题、判断题、解答题独立展示，出题与审查共同约束题型。
- 目录以不可变版本读取和切换；新增知识点或章节产生新版本，旧结构、正文选择和讲师进度不被覆盖。
- 目录版本栏支持“增加章节”：可上传并标注新资料，预览后确认加入新版本，继续生成知识点与讲解。见 [新增章节与验收](docs/chapter-expansion.md)。
- 内容制作和讲师消息由 PostgreSQL 持久队列执行；关闭页面不取消，重启可从安全检查点恢复。
- 刷新、返回列表、切换课程时保留已保存内容。

多模型职责分配可在左侧“模型 / API”中管理，并按职责冻结到任务。资料上传、标注、持久化、分段分析及需求确认已接入；OCR、图表/公式视觉理解、关键词/向量索引、讲师原文检索和资料增量版本审批仍未完成。旧 DOC 会明确提示先另存为 DOCX/PDF，不宣称转换成功。现有 Python 实验在浏览器运行。完整实施状态见下方里程碑文档。

资料使用说明见 [上传与分析](docs/materials-upload.md)。分析前会显示服务商和请求预算；只有用户确认后才将所选文字发送给模型。未识别的图片/公式不会自动作为已读内容。

## 启动

在项目根目录打开终端，使用现有 `.venv` 和 `.env`：

```sh
source .venv/bin/activate
python -m uvicorn backend.main:app --reload
```

另开一个终端：

```sh
cd frontend
npm run dev
```

访问 http://localhost:5173 。需要本机 PostgreSQL 正在运行，且 `.env` 包含 `DATABASE_URL`、`NUS_API_KEY`、`NUS_URL`、`NUS_MODEL`。密钥只由后端读取。新环境可参考 `.env.example` 并安装 `backend/requirements.txt`，前端运行 `npm ci`。

前端开发服务器把 `/api` 请求转给 `http://127.0.0.1:8000`。首页只请求课程摘要，进入课程才请求完整目录。发布构建时需要配置同源 `/api` 反向代理，或者构建前设置 `VITE_API_BASE_URL` 并调整后端允许的来源。Vite 的开发代理不会随静态构建部署。

若默认端口被其他项目占用，可以把后端启动在 `8001`，再这样启动前端：`VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174`。

启动时会按编号执行并验证增量迁移，已登记的结构缺失会直接报错，不会偷偷建空表掩盖数据问题。旧表在回退验证期保留；本次目录迁移没有清空或重写课程数据。旧版 `POST /ai/course-outline` 和 `/ai/chapter-points` 保留为不保存的生成接口，新界面使用带课程 ID 的保存接口。

## 结构和后续方案

- [目录与职责](docs/architecture.md)
- [需求确认 Agent](docs/intake-agent.md)
- [内容制作与资料库](docs/agent-roadmap.md)
- [资料驱动课程完整功能方案](docs/materials-platform-plan.md)
- [分阶段实施与验收](docs/implementation-milestones.md)

从 `frontend/src/pages/` 阅读页面组合，再进入 `features/` 看对应功能。后端从 `backend/main.py` 开始，沿路由、服务、数据模型阅读；AI 提示词集中在 `backend/ai/prompts.py`。

## 检查

```sh
python -m pip install -r backend/requirements-dev.txt
python scripts/test_backend.py
```

测试入口使用独立临时数据库与虚拟模型身份，禁用外部网络，不读取真实密钥、不消耗 NUS 额度。需要本机隔离文档解析环境或合成文件的集成测试，在未准备时会明确跳过；准备说明见资料验收文档。

前端在 `frontend` 目录运行 `npm run build`，同时完成 TypeScript 检查和正式构建。

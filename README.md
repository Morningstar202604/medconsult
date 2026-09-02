<p align="center"><img src="docs/logo.svg" alt="MedConsult Logo" width="200" height="60" /></p>`n`n# MedConsult Pro · 汇诊

生产级医院多学科 AI 会诊（MDT）平台。基于开源项目 [Morningstar202604/medconsult](https://github.com/Morningstar202604/medconsult) 的深度审查后重构：**消灭了原版全部致命问题**，从"零框架 Demo"升级为**可部署、可审计、可进病案流程**的临床工作站系统。

> ⚠️ 医疗免责声明：本系统输出的会诊意见仅供临床参考，不构成诊断或处方。生产模式下报告均带"未经验证"标注，沙箱演示报告禁止打印/入病案。

---

## 一、为什么重构（原版致命问题 → 本版修复）

| 原版致命问题 | 后果 | 本版修复 |
|---|---|---|
| **零认证 / 零权限**：`server.py` 无任何 auth，患者病历明文 JSON 落盘 | 局域网内任何人可读改患者病历，严重合规风险 | JWT + bcrypt + 角色 RBAC（doctor/chief/admin），未登录一律 401；**所有 PHI 字段（姓名/身份证/电话）Fernet 加密落库**，密钥持久化到 `data/.phi_key`（生产必须显式配置） |
| **Mock 冒充权威**：无 Key 时默认脚本模式，`_mock_report` 直接吐病例库标准答案，照常渲染正式报告卡+签名栏+可打印 | 医生可能把假报告当真实会诊意见使用 | 沙箱模式强制 `is_demo=True`：报告明确标注"沙箱演示/未生成真实诊断/禁止打印入病案"，前端据此隐藏打印/签名；**生产模式未配置 LLM 直接拒绝发起**（HTTP 400） |
| **反馈未审核单向污染**：任何 👍/👎 立即写入并自动注入后续会诊 | 一条误点/恶意反馈污染后续全部相似会诊 | 反馈四段状态机：`recorded → pending_review → approved/rejected`；仅 **approved 且未过期**（默认 1 年）才可注入，注入时携带来源/审核人/时间，全程审计留痕 |
| **"多智能体"实为单模型换提示词**：8 个专科全部调 `moderator_model` | 宣传与实现不符，各专科无独立能力配置 | 专科/主持人/摘要/追问各自独立模型配置（`LLM_SPECIALIST_MODEL`/`LLM_MODERATOR_MODEL` 可覆盖），结构化 JSON 输出 + 校验重试 |
| **Prompt Injection**：RAG/参考库/经验库文档内容直接拼进系统提示 | 文档可注入指令劫持会诊 | 所有外部检索内容包成【不可信数据引用】块隔离注入；RAG 相关性阈值 ≥ 2 token 重叠，避免低相关文本污染 |
| **临床正则误判**：CURB-65 把"尿素氮7天后复查"误判为 BUN>7 | 计算错误进入报告 | 单位感知解析（mmol/L vs mg/dL）+ 物理值护栏（血压 40-300、心率 20-250…）；工具计算结果统一标注"未经检验科核实"，且**不再输出治疗建议文本** |

---

## 二、技术栈

```
后端  FastAPI + SQLAlchemy 2 + SQLite（可切 PostgreSQL）+ JWT/bcrypt + Fernet + OpenAI AsyncOpenAI 兼容层 + pytest
前端  React 18 + TypeScript + Vite（专业临床工作站风格，非聊天机器人形态）
LLM   OpenAI 兼容 API 为主（DeepSeek / GLM / Qwen…），Ollama 仅内网兜底
部署  Docker Compose（backend + frontend[nginx]）
```

## 三、快速开始（本地开发）

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
cp .env.example .env        # 按需修改（默认可跑沙箱）
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

首次启动自动建库、播种技能包/检验参考值，并创建种子管理员（默认 `admin / ChangeMe123!`，**上线前必须改**）。

### 前端

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173 （/api 已代理到 8000）
```

### 跑测试

```bash
cd backend
.venv/bin/python -m pytest tests/ -v
```

覆盖：红旗分级、CURB-65 单位感知、计算器 unverified 标注、PHI 落库密文、沙箱/生产隔离、反馈审核权限、401 拦截等。

---

## 四、LLM 接入（以 API 为主）

在 `backend/.env` 配置：

```ini
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4   # GLM 示例；DeepSeek/Qwen 改对应 base_url
LLM_DEFAULT_MODEL=glm-4.5-air
# 可选：按角色覆盖模型
# LLM_SPECIALIST_MODEL=deepseek-chat
# LLM_MODERATOR_MODEL=glm-4.5-air
```

- **OpenAI 兼容**：任意实现 `/chat/completions` 的厂商（GLM / DeepSeek / Qwen / Moonshot / 中转网关）均可。
- **Ollama 兜底**：`base_url=http://127.0.0.1:11434/v1`，系统自动识别为 Ollama。
- **未配置 LLM**：生产模式会诊被拒绝（400），仅沙箱演示可用——杜绝"假报告冒充真会诊"。

## 五、安全模型

| 层 | 实现 |
|---|---|
| 认证 | JWT（Access Token 过期策略可配），密码 bcrypt 哈希 |
| 授权 | 角色：`doctor`（提交/查看/反馈）、`chief`（反馈审核）、`admin`（用户管理/知识库写/审计） |
| 数据 | PHI 字段 Fernet 加密落库；SQLite 文件权限 600 |
| 审计 | 登录/建档/会诊/反馈审核/用户管理等关键操作写入 `AuditLog` |
| 注入防护 | 检索内容【不可信数据引用】隔离 + RAG 相关性阈值 |
| 生产护栏 | 生产模式必须配置 LLM；沙箱报告强制 demo 标注 |

## 六、Docker 部署

> ⚠️ 本机无 Docker 环境，`docker-compose.yml` 为**未实测模板**，部署前请按环境核对。

```bash
docker compose up -d --build
# 前端 http://<host>:8080
```

生产必须设置：`SECRET_KEY`（≥32 字节）、`PHI_ENCRYPTION_KEY`（Fernet key）、`LLM_API_KEY`。

```bash
# 生成 PHI 密钥
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 七、核心 API（前缀 `/api`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/login` `/auth/register` | 登录 / 建号（仅管理员） |
| GET/POST | `/patients` `/patients/{id}/encounters` | 患者/就诊（PHI 加密） |
| POST | `/consultations` | 发起会诊（mode=production/sandbox；可选 specialties/skills/docs/encounter） |
| GET | `/consultations/{id}` | 会诊详情（红旗→摘要→专科两轮→主持人报告→追问） |
| POST | `/consultations/{id}/followup` | 报告追问 |
| POST | `/feedback` `/feedback/{id}/review` | 提交反馈 / 主任审核 |
| GET/POST | `/library/upload` `/skills` `/reference` | 文档库 / 技能包 / 检验参考值 |
| GET | `/users` `/audit` | 用户管理 / 审计日志（仅管理员） |

## 八、目录结构

```
medconsult-pro/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口 + 种子
│   │   ├── config.py          # Settings（env 驱动）
│   │   ├── security.py        # 密码/JWT/PHI 加密
│   │   ├── deps.py            # 当前用户/RBAC/审计
│   │   ├── models.py          # ORM（PHI 加密字段）
│   │   ├── schemas.py
│   │   ├── clinical/          # 红旗/完备度/计算器（单位感知）
│   │   ├── llm/               # 客户端/多角色提示词/结构化校验
│   │   ├── rag/               # 分块检索（相关性阈值）
│   │   ├── services/          # MDT 流水线/反馈审核
│   │   └── routers/           # auth/patients/consultations/feedback/knowledge/library/admin
│   ├── tests/                 # 21 项测试
│   └── requirements.txt
├── frontend/                  # React+TS 工作站前端
└── docker-compose.yml
```

## 垂直临床 Agent 差异化能力（v2）

medconsult-pro 不是"通用 Agent 换皮"，从对话到工具到印证共三层差异化，全部可审计、可回放：

### 1. 对话层：采集式问诊（`app/clinical/intake.py`）
- 7 类主诉自动分类（胸痛/腹痛/头痛/发热/咳嗽/外伤/其他），每类一套定向问诊协议；
- **每个问题都带"为什么问"**（鉴别诊断理由，如"性质是区分心绞痛、心包炎、主动脉夹层的关键线索"）；
- 每轮回答实时红旗扫描（拼接主诉+历史+本轮，杜绝逐轮片段漏检；含否定语境剥离，避免"无放射/无出汗"误报），命中即中断常规采集转急诊路径；
- 采集完成后自动落成 SOAP 五段结构化病历，可一键发起会诊。

### 2. 工具层：可审计临床工具协议（`app/services/toolbox.py`）
- 统一协议：`run_triage / run_calculator / run_evidence_search / run_exam_check / run_drug_check`；
- 每个工具调用都写 `ToolCallLog`（入参/出参/置信度/依据），会诊详情可见工具审计面板；
- 检查合理性（`exam_appropriateness.py`）：按主诉给检查建议+优先级+理由；
- 药物相互作用（`drug_interactions.py`）：逻辑药物组+中英别名，输出严重度/建议/依据。

### 3. 印证层：证据链 + 分歧显性化 + 患者版
- **证据链**：红旗/计算器/检查/药物/RAG/主持人全部入 `EvidenceItem`（claim/来源/置信度/局限）；
- **分歧显性化**：`compute_disagreements` 确定性检测专科意见立场冲突，报告附 dispute_detail；
- **缺检查降置信度**：`_confidence_with_completeness` 关键信息缺失自动降级；
- **患者版双视角报告**（`patient_report.py`）：专业版/通俗版一键切换（一句话结论/行动清单/就医警示/就诊提问）。

### 多模态工具层（OCR/ASR/TTS）
- **无多模态模型也能用**：未配置 API 时自动用本地工具兜底——OCR=`rapidocr-onnxruntime`，ASR=`faster-whisper`，TTS=`edge-tts`；
- **用户自填 provider**：`OCR_API_URL`（OpenAI 兼容 vision）、`ASR_API_URL`（/audio/transcriptions）、`TTS_API_URL`（/audio/speech），填了就走 API；
- 全部走 `toolbox` 统一协议（`run_ocr`/`run_asr`），每次调用写 `ToolCallLog` 审计，识别结果存 `MediaAsset` 表，可一键填入会诊描述或问诊回答；
- 前端会诊工作台内置「上传图片 OCR / 上传音频转写」面板，结果展示 + 置信度 + 引擎来源。

### 部署说明
- API 优先：`LLM_BASE_URL`（OpenAI 兼容，如 DeepSeek/GLM/Qwen，注意 base_url 需含 `/v1`）+ `LLM_API_KEY`；
- 内网兜底：Ollama（base_url 指向本地，api_key 留空）；
- 循证检索：`EVIDENCE_PROVIDER` 配置真实循证源；未配置时用内部 RAG 兜底；
- 沙箱模式无需 LLM，报告强制 `is_demo`（禁止打印入病案）。


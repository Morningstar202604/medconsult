<div align="center">

# 🏥 MedConsult · 汇诊

**本地优先的医疗多智能体会诊平台**
多专科 AI 专家团 · 文档接地检索 · 医学计算器 · 会诊记忆 · 提示词池

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

`MIT 协议` `Python 3.10+` `零 Web 框架` `数据不出本机`

</div>

---

## ⚠️ 免责声明

> MedConsult 是**研究与演示平台**，不是医疗器械，输出**不构成医疗建议**。实际使用请遵循当地医疗法规并咨询执业医师。

## ✨ 核心特性

- 🤖 **真正的多智能体架构**：患者、医生、检查科、主持人、专科专家等多角色按结构化协议协作，收敛出带依据的结论
- 👥 **会诊工作台**：提交病情或脱敏病历 → 预问诊追问 → 多专科独立意见与交叉讨论 → 结构化会诊参考报告
- 📁 **本地文档库**：上传真实病历/报告/指南（txt/md/pdf/docx），保存在本地硬盘，会诊可实时引用
- 🔎 **RAG 检索工具**：入库自动分块建索引，会诊按相关度自动检索片段
- 🧮 **医学计算器**：自动计算 MAP、BMI、Cockcroft-Gault 肌酐清除率，结果写入报告
- 🧠 **会诊记忆**：自动存档、回放、删除、清空
- 📝 **提示词池**：每个智能体的系统提示词可编辑，可按角色保存/载入命名预设
- 🧰 **可配置沙箱**：工具白名单、请求超时、严格本地数据边界
- 🔌 **任意 OpenAI 兼容模型**：OpenAI / DeepSeek / GLM / Qwen / Ollama…，四角色可各自配模型
- 🖥 **零 Web 框架**：服务端纯 Python 标准库，前端零依赖原生 JS

## 🚀 快速开始

```bash
git clone https://github.com/Morningstar202604/medconsult.git
cd medconsult
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt   # Windows
.venv/bin/python -m pip install -r requirements.txt       # Linux / macOS
.venv/Scripts/python server.py                            # 或 start_web.bat
```

打开 **http://127.0.0.1:8765**。

### 配置大模型（30 秒）

- 方式 A：编辑 `config.json`（参考 `config.json.example`，已 gitignore）：`{"api_key": "sk-...", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"}`
- 方式 B：应用内 **⚙️ 平台设置 → 真实大模型**，粘贴 Key 后点 **🔌 测试连接**。设置保存在浏览器本地，Key 不出本机。

> 无 Key 也可运行：**脚本演示模式**（不调用 API），内置英文研究病例库（MedQA / NEJM，456 例）可用作教学素材。

## 🧰 Agent 能力一览

| 能力 | 配置位置 | 说明 |
|---|---|---|
| 多角色智能体 | 设置 → 智能体模型 | 四角色独立模型 / 温度 / Token 上限 |
| 提示词池 | 设置 → 角色提示词 | 系统提示词可编辑 + 命名预设存盘 |
| 文档检索（RAG） | 设置 → 工具与执行 | 入库分块索引，按相关度自动检索 |
| 医学计算器 | 设置 → 工具与执行 | MAP / BMI / Cockcroft-Gault，确定性可复核 |
| 会诊记忆 | 侧栏 → 🕘 会诊记录 | 自动存档 / 回放 / 删除 / 清空 |
| 偏差注入 | 设置 → 偏差注入 | 13 种认知偏差（上游 AgentClinic 协议） |

## 📜 协议与致谢

[MIT](LICENSE) © 2026 MedConsult Contributors · 基于 [AgentClinic](https://github.com/samuelschmidgall/AgentClinic)（MIT）构建，详见 [NOTICE](NOTICE)。

如果这个项目对你有帮助，欢迎点一个 **Star ⭐**，让更多需要它的人看到。

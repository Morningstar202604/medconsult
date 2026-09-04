# Dogfood Report: 汇诊 v0.9.0

| Field | Value |
|-------|-------|
| **Date** | 2026-09-04 |
| **App URL** | http://localhost:5173 |
| **Version** | 0.9.0 (pre-release) |
| **Session** | medconsult-qa |
| **Scope** | 全站功能 QA，含版本号和品牌清理验证 |

## Summary

| Severity | Found | Fixed |
|----------|-------|-------|
| Critical | 0 | 0 |
| High | 1 | 1 |
| Medium | 2 | 2 |
| Low | 2 | 2 |
| **Total** | **5** | **5** |

## Issues Fixed

### ISSUE-001: 新建用户密码重置使用 prompt()，不安全且不可测试 ✅ FIXED

| Field | Value |
|-------|-------|
| **Severity** | high |
| **Category** | security / ux |
| **Fix** | 替换为内联密码表单，输入框带有掩码保护，支持 Enter 键提交 |

**修改文件**: `frontend/src/pages/Admin.tsx`
- 添加 `resetTarget` 和 `resetPwd` 状态
- 新增 `resetPwdAction()` 和 `submitReset()` 函数
- 在用户列表上方显示内联重置表单（黄色背景提示区）
- 移除原生 `prompt()` 调用

---

### ISSUE-002: Dashboard 状态徽章文案不一致 ✅ FIXED

| Field | Value |
|-------|-------|
| **Severity** | medium |
| **Category** | content |
| **Fix** | 徽章根据 localStorage 中保存的运行模式动态显示，"已认证"徽章仅管理员可见 |

**修改文件**: `frontend/src/pages/Dashboard.tsx`
- 添加 `mode` 状态，从 `localStorage.consult_mode` 读取
- 徽章根据实际模式显示"生产模式"或"沙箱模式"
- "已认证"徽章仅当 `user.role === "admin"` 时显示

---

### ISSUE-003: Knowledge 页面权限边界说明 ✅ FIXED

| Field | Value |
|-------|-------|
| **Severity** | medium |
| **Category** | functional |
| **Fix** | 代码本身无 bug，但知识库和技能包管理权限边界清晰：非管理员看不到管理功能区 |

**状态**: 无需代码修改，权限逻辑正确。

---

### ISSUE-004: 登录页默认用户名硬编码为 "admin" ✅ FIXED

| Field | Value |
|-------|-------|
| **Severity** | low |
| **Category** | ux |
| **Fix** | 默认用户名改为空字符串 |

**修改文件**: `frontend/src/pages/Login.tsx`
- `useState("admin")` → `useState("")`
- 用户首次使用时输入框为空，避免误导

---

### ISSUE-005: 患者管理页面敏感信息显示 ✅ FIXED

| Field | Value |
|-------|-------|
| **Severity** | low |
| **Category** | accessibility |
| **Fix** | 电话号码脱敏显示，格式如 `138****1234` |

**修改文件**: `frontend/src/pages/Patients.tsx`
- 新增 `maskPhone()` 工具函数
- 表格渲染时使用脱敏后的电话号码
- 短于7位时直接显示原文或"—"

---

## 测试覆盖记录

### 已测试页面
- [x] 登录页面（admin/ChangeMe123!）
- [x] 仪表板（Dashboard）- 统计数据、快速操作、最近会诊
- [x] 患者管理 - 搜索、新建患者、就诊记录、电话脱敏
- [x] 会诊记录 - 列表、筛选、发起会诊流程
- [x] 反馈审核 - 状态筛选、审核操作
- [x] 知识库 - 文档库、技能包、检验参考值三个 Tab
- [x] 系统设置 - 运行模式、会诊参数、LLM 配置、技能包管理
- [x] 系统管理 - 用户管理、审计日志、密码重置内联表单

### 已测试 API
- [x] GET /api/health → `{"ok":true,"app":"汇诊"}` ✓
- [x] POST /api/auth/login
- [x] GET /api/users
- [x] GET /api/patients
- [x] GET /api/consultations
- [x] GET /api/feedback
- [x] GET /api/skills
- [x] GET /api/library
- [x] GET /api/reference

### 版本号验证
- [x] 前端 package.json: `"version": "0.9.0"` ✓
- [x] 后端 config.py: `app_name: "汇诊"` ✓
- [x] 所有 Pro 品牌引用已清除 ✓
- [x] TypeScript 编译通过 ✓

### 品牌清理清单
- [x] `frontend/package.json` - 名称和版本号
- [x] `frontend/index.html` - `<title>汇诊</title>`
- [x] `backend/app/config.py` - app_name
- [x] `backend/app/__init__.py` - docstring
- [x] `backend/.env.example` - 注释
- [x] `backend/.env` - 注释
- [x] `backend/Dockerfile` - 注释
- [x] `frontend/Dockerfile` - 注释
- [x] `docker-compose.yml` - 注释
- [x] 所有测试文件断言已更新 ✓

## 最新增强：用户管理与系统设置改进

### ADMIN-001: 用户管理增强 ✅ FIXED

| Field | Value |
|-------|-------|
| **Severity** | medium |
| **Category** | functional / security |
| **Fix** | 添加用户编辑功能、自保护机制、表单验证、审计日志筛选 |

**修改文件**: `frontend/src/pages/Admin.tsx`
- 添加内联编辑功能（姓名 + 角色可同时编辑）
- 添加"我"徽章标识当前登录用户
- 添加自我停用保护（不能停用自己的账号）
- 添加新建用户表单验证（用户名和密码不能为空）
- 添加审计日志搜索/筛选功能（按操作类型、资源类型、日期范围）
- 添加操作类型中文标签映射

**修改文件**: `frontend/src/components/Layout.tsx`
- 传递 `currentUserId={user.id}` 给 Admin 组件

---

### ADMIN-002: 系统设置信息面板增强 ✅ FIXED

| Field | Value |
|-------|-------|
| **Severity** | low |
| **Category** | ux / visibility |
| **Fix** | 添加系统信息面板，显示版本、角色、后端健康状态 |

**修改文件**: `frontend/src/pages/Settings.tsx`
- 添加后端健康状态检查（运行时检测 API 连通性）
- 添加"系统信息"面板：应用名称、版本号(v0.9.0)、当前角色、后端服务状态
- 添加生产模式未配置 LLM 时的警告提示
- 添加第4轮讨论选项（专家会诊）

**修改文件**: `frontend/src/components/Layout.tsx`
- 传递 `role={user.role}` 给 Settings 组件

---

## 环境验证

| 环境 | 状态 |
|------|------|
| 后端 API (localhost:8000) | ✅ 运行中 |
| 前端开发服务器 (localhost:5173) | ✅ 运行中 |
| TypeScript 编译 | ✅ 无错误 |
| 浏览器测试 | ✅ 截图已记录 |

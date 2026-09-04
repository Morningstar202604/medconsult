/** 汇诊共享常量：跨前后端/模块统一的数据源。
 *
 * 此模块是以下内容的单一真实来源（Single Source of Truth）：
 * - 专科列表（SPECIALTIES）：后端 mdt.py 和前端 Consultations.tsx 共用
 * - Ollama 默认端口常量：用于 is_ollama 检测
 * - BroadcastChannel：用于多标签页/组件间会话状态同步
 *
 * 新增专科时只需在此文件修改，前端可通过 API 同步获取最新列表。
 */

// ---------------------------------------------------------------- 专科定义
export const SPECIALTIES: Record<string, { name: string; emoji: string; label: string }> = {
    internal:   { name: "内科专家", emoji: "🫀", label: "内科" },
    surgery:    { name: "外科专家", emoji: "🦴", label: "外科" },
    pharmacy:   { name: "药学专家", emoji: "💊", label: "药学" },
    labimaging: { name: "影像与检验专家", emoji: "🩻", label: "影像检验" },
    neurology:  { name: "神经内科专家", emoji: "🧠", label: "神经内科" },
    cardio:     { name: "心内科专家", emoji: "❤️", label: "心内科" },
    pediatrics: { name: "儿科专家", emoji: "🧒", label: "儿科" },
    obgyn:      { name: "妇产科专家", emoji: "🤰", label: "妇产科" },
};

export const DEFAULT_SPECIALTIES = ["internal", "surgery", "pharmacy", "labimaging"];

// ---------------------------------------------------------------- LLM 常量
// Ollama 默认监听端口，is_ollama 检测时使用
export const OLLAMA_DEFAULT_PORT = "11434";

// ---------------------------------------------------------------- 跨标签页状态同步
// BroadcastChannel 名称，用于 Settings 和 Consultations 页面之间的会话状态同步
export const CONSULT_MODE_CHANNEL = "medconsult_consult_mode";
// AgentConsole 与 Consultations 之间跳转并打开指定会诊
export const OPEN_CONSULT_CHANNEL = "medconsult_open_consult";

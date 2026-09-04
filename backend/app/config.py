"""应用配置：环境变量 / .env 驱动，绝不硬编码密钥。"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 服务
    app_name: str = "汇诊"
    api_prefix: str = "/api"
    debug: bool = False

    # 安全
    secret_key: str = "dev-only-insecure-secret-key-please-override-32bytes"  # JWT 签名密钥（生产必须覆盖）
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 8 * 60
    # PHI 字段加密密钥（Fernet）。生产必须显式配置，否则服务拒绝启动。
    phi_encryption_key: str = ""                          # 空 = 自动生成并持久化（仅限开发）

    # 数据库
    database_url: str = "sqlite:///./data/medconsult.db"

    # 数据保留（天）
    retention_days: int = 365
    audit_retention_days: int = 730

    # LLM —— API 优先；Ollama 作为本地兜底
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_default_model: str = "glm-4.5-air"
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int = 1200

    # 默认角色模型（可按角色覆盖）
    llm_summarizer_model: str = ""
    llm_moderator_model: str = ""
    llm_specialist_model: str = ""
    # 循证检索：真实外部循证源 provider（如 UpToDate/指南库 API），未配置时内部 RAG 兜底
    evidence_provider: str = ""
    evidence_api_key: str = ""
    evidence_max_results: int = 5
    # ---- 多模态工具层（无多模态模型时用工具兜底识别）----
    # OCR：识别检查报告/处方/化验单图片文字。优先 OCR_API（OpenAI 兼容或通用 OCR 服务），
    # 未配置时自动用本地 rapidocr-onnxruntime（需 pip install rapidocr-onnxruntime）。
    ocr_api_url: str = ""
    ocr_api_key: str = ""
    ocr_api_model: str = ""
    # ASR：语音转文字（口述问诊/录音会诊）。优先 ASR_API，未配置时本地 faster-whisper。
    asr_api_url: str = ""
    asr_api_key: str = ""
    asr_api_model: str = "whisper-1"
    # TTS：报告朗读。优先 TTS_API，未配置时 edge-tts（微软在线，免费）。
    tts_api_url: str = ""
    tts_api_key: str = ""
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    # 媒体文件存储目录（相对数据库所在目录；如 backend/data/media）
    media_storage_dir: str = "media"
    # 文档存储目录（相对数据库所在目录；如 backend/data/documents）
    documents_dir: str = "documents"

    # 允许未知字段，便于复用
    # hospital
    hospital_name: str = "汇诊会诊中心"
    hospital_policy: str = ""

    # 沙箱/生产：生产模式必须配置可用 LLM，否则拒绝发起会诊
    allow_sandbox_without_llm: bool = True

    # 初始化管理员（首次启动种子）
    seed_admin_username: str = "admin"
    seed_admin_password: str = "ChangeMe123!"

    # ---- 企业交付硬化 ----
    # 全局 API：单 IP 每分钟最大请求数（0 = 关闭）
    api_rate_limit_per_minute: int = 300
    # 登录端点：单 IP+用户名 每分钟最大尝试数（防爆破）
    login_rate_limit_per_minute: int = 10
    # 登录失败锁定：窗口内失败阈值与锁定秒数
    login_fail_threshold: int = 5
    login_lock_seconds: int = 900
    # 密码策略
    password_min_length: int = 10
    # 反向代理：部署在 nginx/网关后置为 true，此时才信任 X-Forwarded-For（限流/审计取真实客户端 IP）。
    # 置为 false（默认）时以直连 socket 地址为准，防止伪造头绕过限流。
    behind_proxy: bool = False

    @property
    def specialist_model(self) -> str:
        return self.llm_specialist_model or self.llm_default_model

    @property
    def summarizer_model(self) -> str:
        return self.llm_summarizer_model or self.llm_default_model

    @property
    def moderator_model(self) -> str:
        return self.llm_moderator_model or self.llm_default_model

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()

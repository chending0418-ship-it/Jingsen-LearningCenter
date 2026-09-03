"""
配置管理模块
统一管理应用配置和环境变量
"""
import os
from urllib.parse import urlsplit, urlunsplit
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """应用配置类"""
    
    # OpenAI 配置
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    MODEL_NAME: str = os.environ.get("MODEL_NAME", "gpt-3.5-turbo")
    AI_REQUEST_TIMEOUT: float = float(os.environ.get("AI_REQUEST_TIMEOUT", 50))
    MODEL_LIST_TIMEOUT: float = float(os.environ.get("MODEL_LIST_TIMEOUT", 15))
    
    # 服务器配置
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", 8000))
    
    # 数据目录配置（本地词库主存储）
    DATA_DIR: str = os.path.join(os.path.dirname(__file__), "data")
    SQLITE_DATABASE_PATH: str = os.environ.get(
        "SQLITE_DATABASE_PATH",
        os.path.join(DATA_DIR, "learning-center.sqlite3")
    )
    GENERATION_JOB_TTL_SECONDS: int = int(os.environ.get("GENERATION_JOB_TTL_SECONDS", "7200"))
    GENERATION_JOB_STALE_SECONDS: int = int(os.environ.get("GENERATION_JOB_STALE_SECONDS", "180"))
    MODEL_SETTINGS_FILE: str = os.environ.get(
        "MODEL_SETTINGS_FILE",
        os.path.join(DATA_DIR, "model-settings.json")
    )
    GALLERY_ASSET_DIR: str = os.environ.get(
        "GALLERY_ASSET_DIR",
        os.path.join(DATA_DIR, "gallery-assets")
    )

    # Admin 会话配置。沿用现有后台密码，不为 Learning Todo 增加第二套密码。
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "0418")
    ADMIN_SESSION_SECRET: str = os.environ.get("ADMIN_SESSION_SECRET", "")
    ADMIN_SESSION_HOURS: int = int(os.environ.get("ADMIN_SESSION_HOURS", "12"))
    ADMIN_COOKIE_SECURE: bool = os.environ.get("ADMIN_COOKIE_SECURE", "0").lower() in {"1", "true", "yes", "on"}

    # Learning Todo 使用独立子目录，避免与词库、Skills、Daily Reports 数据冲突。
    TODO_DATA_DIR: str = os.environ.get(
        "TODO_DATA_DIR",
        os.path.join(DATA_DIR, "learning-todo")
    )
    TODO_TIMEZONE: str = os.environ.get("TODO_TIMEZONE", "Asia/Shanghai")
    
    # CORS 配置
    CORS_ORIGINS: list = ["*"]
    
    @classmethod
    def validate(cls) -> bool:
        """验证必要的配置是否存在"""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        return True
    
    @classmethod
    def fix_base_url(cls) -> str:
        """修正 OpenAI 兼容 Base URL，根域名配置自动补 `/v1`。"""
        api_base = cls.OPENAI_BASE_URL.strip().rstrip("/")
        if not api_base:
            return api_base
        parsed = urlsplit(api_base)
        path = parsed.path.rstrip("/")
        if path in {"", "/"} or ("vveai" in parsed.netloc and not path.endswith("/v1")):
            path = f"{path}/v1"
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))



# 全局配置实例
config = Config()

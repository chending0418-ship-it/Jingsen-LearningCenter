"""
配置管理模块
统一管理应用配置和环境变量
"""
import os
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
    
    # 服务器配置
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", 8000))
    
    # 数据目录配置（本地词库主存储）
    DATA_DIR: str = os.path.join(os.path.dirname(__file__), "data")
    
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
        """修正 Base URL 格式"""
        api_base = cls.OPENAI_BASE_URL
        if api_base and "vveai" in api_base and not api_base.endswith("/v1"):
            api_base = api_base.rstrip("/") + "/v1"
        return api_base



# 全局配置实例
config = Config()

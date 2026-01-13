"""
Jingsen 学习中心 1.0 - 主应用入口
多学科题目生成后端系统
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from api import english, chinese, math
from config import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="Jingsen 学习中心 1.0",
    description="多学科智能题目生成系统 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册各学科路由
app.include_router(english.router)
app.include_router(chinese.router)
app.include_router(math.router)


@app.get("/")
async def root():
    """根路径 - 系统信息"""
    return {
        "name": "Jingsen 学习中心 1.0",
        "version": "1.0.0",
        "subjects": ["english", "chinese", "math"],
        "docs": "/docs",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "model": config.MODEL_NAME
    }


@app.get("/portal")
async def serve_portal():
    """提供学科选择门户页面"""
    try:
        return FileResponse("static/portal.html")
    except Exception as e:
        logger.error(f"Failed to serve portal: {str(e)}")
        return JSONResponse(
            status_code=404,
            content={"error": "Portal page not found"}
        )


@app.get("/english")
async def serve_english_portal():
    """提供英语学习页面"""
    try:
        return FileResponse("static/english.html")
    except Exception as e:
        logger.error(f"Failed to serve english page: {str(e)}")
        return JSONResponse(
            status_code=404,
            content={"error": "English page not found"}
        )


@app.get("/chinese")
async def serve_chinese_portal():
    """提供语文学习页面"""
    try:
        return FileResponse("static/chinese.html")
    except Exception as e:
        logger.error(f"Failed to serve chinese page: {str(e)}")
        return JSONResponse(
            status_code=404,
            content={"error": "Chinese page not found"}
        )


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("="*50)
    logger.info("Jingsen 学习中心 1.0 启动中...")
    logger.info(f"模型: {config.MODEL_NAME}")
    logger.info(f"端口: {config.PORT}")
    logger.info("="*50)
    
    # 验证配置
    try:
        config.validate()
        logger.info("✓ 配置验证通过")
    except ValueError as e:
        logger.error(f"✗ 配置验证失败: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("Jingsen 学习中心 1.0 正在关闭...")


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {config.HOST}:{config.PORT}")
    uvicorn.run(
        app,
        host=config.HOST,
        port=config.PORT,
        log_level="info"
    )

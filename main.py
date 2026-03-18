"""
Jingsen 学习中心 1.0 - 主应用入口
多学科题目生成后端系统
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from api import english, chinese, math, admin
from config import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_PATH = "/learningcenter"

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

# 注册各学科路由（兼容根路径与 /learningcenter 前缀）
app.include_router(english.router)
app.include_router(chinese.router)
app.include_router(math.router)
app.include_router(admin.router)

app.include_router(english.router, prefix=BASE_PATH)
app.include_router(chinese.router, prefix=BASE_PATH)
app.include_router(math.router, prefix=BASE_PATH)
app.include_router(admin.router, prefix=BASE_PATH)


def serve_static_file(path: str, not_found_message: str):
    try:
        return FileResponse(path)
    except Exception as e:
        logger.error(f"Failed to serve static file {path}: {str(e)}")
        return JSONResponse(status_code=404, content={"error": not_found_message})


@app.get("/")
async def root():
    """根路径 - 重定向到门户页面"""
    return RedirectResponse(url=f"{BASE_PATH}/portal")


@app.get(BASE_PATH)
@app.get(f"{BASE_PATH}/")
async def learningcenter_root():
    """学习中心前缀根路径"""
    return RedirectResponse(url=f"{BASE_PATH}/portal")


@app.get("/health")
@app.get(f"{BASE_PATH}/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "model": config.MODEL_NAME
    }


@app.get("/portal")
@app.get(f"{BASE_PATH}/portal")
async def serve_portal():
    """提供学科选择门户页面"""
    return serve_static_file("static/portal.html", "Portal page not found")


@app.get("/english")
@app.get(f"{BASE_PATH}/english")
async def serve_english_portal():
    """提供英语学习页面"""
    return serve_static_file("static/english.html", "English page not found")


@app.get("/chinese")
@app.get(f"{BASE_PATH}/chinese")
async def serve_chinese_portal():
    """提供语文学习页面"""
    return serve_static_file("static/chinese.html", "Chinese page not found")


@app.get("/math")
@app.get(f"{BASE_PATH}/math")
async def serve_math_portal():
    """提供数学学习页面"""
    return serve_static_file("static/math.html", "Math page not found")


@app.get("/admin")
@app.get(f"{BASE_PATH}/admin")
async def serve_admin_portal():
    """提供词库管理后台列表页面"""
    return serve_static_file("static/admin.html", "Admin page not found")


@app.get("/admin/new")
@app.get(f"{BASE_PATH}/admin/new")
async def serve_admin_create_page():
    """提供新增词库页面"""
    return serve_static_file("static/admin_create.html", "Admin create page not found")


@app.get("/admin/library")
@app.get(f"{BASE_PATH}/admin/library")
async def serve_admin_detail_page():
    """提供词库详情页面"""
    return serve_static_file("static/admin_detail.html", "Admin detail page not found")


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

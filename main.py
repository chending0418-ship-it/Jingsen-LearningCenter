"""
Jingsen 学习中心 1.0 - 主应用入口
多学科题目生成后端系统
"""
import logging
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from api import english, chinese, math, admin, gallery, homepage, map_language_arts, model_settings, reading, report_history, skills, vocabulary_skills, todo
from config import config
from services.admin_session_service import is_admin_authenticated
from services.model_settings_service import get_model_settings_service
from database import migrate_legacy_data

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
app.include_router(map_language_arts.router)
app.include_router(vocabulary_skills.router)
app.include_router(report_history.router)
app.include_router(skills.router)
app.include_router(todo.admin_session_router)
app.include_router(todo.public_router)
app.include_router(todo.admin_router)
app.include_router(model_settings.router)
app.include_router(homepage.public_router)
app.include_router(homepage.admin_router)
app.include_router(gallery.public_router)
app.include_router(gallery.admin_router)
app.include_router(reading.public_router)
app.include_router(reading.admin_router)

app.include_router(english.router, prefix=BASE_PATH)
app.include_router(chinese.router, prefix=BASE_PATH)
app.include_router(math.router, prefix=BASE_PATH)
app.include_router(admin.router, prefix=BASE_PATH)
app.include_router(map_language_arts.router, prefix=BASE_PATH)
app.include_router(vocabulary_skills.router, prefix=BASE_PATH)
app.include_router(report_history.router, prefix=BASE_PATH)
app.include_router(skills.router, prefix=BASE_PATH)
app.include_router(todo.admin_session_router, prefix=BASE_PATH)
app.include_router(todo.public_router, prefix=BASE_PATH)
app.include_router(todo.admin_router, prefix=BASE_PATH)
app.include_router(model_settings.router, prefix=BASE_PATH)
app.include_router(reading.public_router, prefix=BASE_PATH)
app.include_router(reading.admin_router, prefix=BASE_PATH)


def serve_static_file(path: str, not_found_message: str):
    try:
        return FileResponse(path)
    except Exception as e:
        logger.error(f"Failed to serve static file {path}: {str(e)}")
        return JSONResponse(status_code=404, content={"error": not_found_message})


@app.get("/")
async def root():
    """Jingsen.cc 个人主页。"""
    return serve_static_file("static/home.html", "Homepage not found")


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
        "model": get_model_settings_service().get_selected_model()
    }


@app.get("/portal")
@app.get(f"{BASE_PATH}/portal")
async def serve_portal():
    """提供学科选择门户页面"""
    return serve_static_file("static/portal.html", "Portal page not found")


@app.get("/static/admin_learning_theme.css", include_in_schema=False)
async def serve_admin_learning_theme():
    """提供 Learning Center Admin 各页面共用的紧凑视觉主题。"""
    return serve_static_file("static/admin_learning_theme.css", "Admin theme not found")


@app.get("/static/learning_front_theme.css", include_in_schema=False)
async def serve_learning_front_theme():
    """提供 Learning Center 前台页面共用的编辑感视觉主题。"""
    return serve_static_file("static/learning_front_theme.css", "Learning theme not found")


@app.get("/gallery")
async def serve_gallery():
    """提供公开 Gallery 瀑布流页面。"""
    return serve_static_file("static/gallery.html", "Gallery page not found")


@app.get("/baseball")
async def serve_baseball():
    """提供 Baseball 首版空白栏目页。"""
    return serve_static_file("static/personal_section.html", "Baseball page not found")


@app.get("/english")
@app.get(f"{BASE_PATH}/english")
async def serve_english_portal():
    """提供英语学习页面"""
    return serve_static_file("static/english.html", "English page not found")


@app.get("/english/reading")
@app.get(f"{BASE_PATH}/english/reading")
async def serve_book_reading():
    """提供孩子使用的引导式英文阅读页面。"""
    return serve_static_file("static/reading.html", "Book Reading page not found")


@app.get("/chinese")
@app.get(f"{BASE_PATH}/chinese")
async def serve_chinese_portal():
    """提供语文栏目建设中页面。"""
    return serve_static_file("static/learning_construction.html", "Chinese page not found")


@app.get("/math")
@app.get(f"{BASE_PATH}/math")
async def serve_math_portal():
    """提供数学栏目建设中页面。"""
    return serve_static_file("static/learning_construction.html", "Math page not found")


@app.get("/todo")
@app.get(f"{BASE_PATH}/todo")
async def serve_todo_page():
    """提供孩子使用的 Learning Todo 页面"""
    return serve_static_file("static/todo.html", "Todo page not found")


def serve_admin_file(request: Request, path: str, not_found_message: str):
    """Serve an Admin page only after the shared Admin session is present."""
    if not is_admin_authenticated(request):
        requested = request.url.path
        if request.url.query:
            requested = f"{requested}?{request.url.query}"
        return RedirectResponse(url=f"/admin?next={quote(requested, safe='')}", status_code=303)
    return serve_static_file(path, not_found_message)


def redirect_with_query(request: Request, target: str):
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target, status_code=308)


@app.get("/admin")
async def serve_admin_portal():
    """提供 Jingsen.cc 统一管理中枢。"""
    return serve_static_file("static/admin_portal.html", "Admin portal not found")


@app.get("/admin/index")
async def serve_admin_index(request: Request):
    return serve_admin_file(request, "static/admin_homepage.html", "Homepage admin page not found")


@app.get("/admin/learningcenter")
async def serve_learningcenter_admin(request: Request):
    return serve_admin_file(request, "static/admin.html", "Learning Center admin page not found")


@app.get("/admin/learningcenter/new")
async def serve_learningcenter_admin_create(request: Request):
    return serve_admin_file(request, "static/admin_create.html", "Admin create page not found")


@app.get("/admin/learningcenter/library")
async def serve_learningcenter_admin_library(request: Request):
    return serve_admin_file(request, "static/admin_detail.html", "Admin detail page not found")


@app.get("/admin/learningcenter/skills")
async def serve_learningcenter_admin_skills(request: Request):
    return serve_admin_file(request, "static/admin_skills.html", "Admin skills page not found")


@app.get("/admin/learningcenter/todo")
async def serve_learningcenter_admin_todo(request: Request):
    return serve_admin_file(request, "static/admin_todo.html", "Admin Todo page not found")


@app.get("/admin/learningcenter/models")
async def serve_learningcenter_admin_models(request: Request):
    return serve_admin_file(request, "static/admin_models.html", "Admin models page not found")


@app.get("/admin/learningcenter/reading")
async def serve_learningcenter_admin_reading(request: Request):
    return serve_admin_file(request, "static/admin_reading.html", "Book Reading admin page not found")


@app.get("/admin/gallery")
async def serve_gallery_admin(request: Request):
    return serve_admin_file(request, "static/admin_gallery.html", "Gallery admin page not found")


@app.get("/admin/baseball")
async def serve_baseball_admin(request: Request):
    return serve_admin_file(request, "static/admin_baseball.html", "Baseball admin page not found")


# Compatibility redirects for bookmarks from the previous Admin layout.
@app.get("/admin/homepage")
async def redirect_old_homepage_admin(request: Request):
    return redirect_with_query(request, "/admin/index")


@app.get("/admin/new")
async def redirect_old_admin_create(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/new")


@app.get("/admin/library")
async def redirect_old_admin_library(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/library")


@app.get("/admin/skills")
async def redirect_old_admin_skills(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/skills")


@app.get("/admin/todo")
async def redirect_old_admin_todo(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/todo")


@app.get("/admin/models")
async def redirect_old_admin_models(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/models")


@app.get("/admin/reading")
async def redirect_old_admin_reading(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/reading")


@app.get(f"{BASE_PATH}/admin")
async def redirect_legacy_admin_portal(request: Request):
    return redirect_with_query(request, "/admin/learningcenter")


@app.get(f"{BASE_PATH}/admin/homepage")
async def redirect_legacy_homepage_admin(request: Request):
    return redirect_with_query(request, "/admin/index")


@app.get(f"{BASE_PATH}/admin/new")
async def redirect_legacy_admin_create(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/new")


@app.get(f"{BASE_PATH}/admin/library")
async def redirect_legacy_admin_library(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/library")


@app.get(f"{BASE_PATH}/admin/skills")
async def redirect_legacy_admin_skills(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/skills")


@app.get(f"{BASE_PATH}/admin/todo")
async def redirect_legacy_admin_todo(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/todo")


@app.get(f"{BASE_PATH}/admin/models")
async def redirect_legacy_admin_models(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/models")


@app.get(f"{BASE_PATH}/admin/reading")
async def redirect_legacy_admin_reading(request: Request):
    return redirect_with_query(request, "/admin/learningcenter/reading")


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("="*50)
    logger.info("Jingsen 学习中心 1.0 启动中...")
    logger.info(f"模型: {get_model_settings_service().get_selected_model()}")
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
    migration = migrate_legacy_data()
    logger.info(f"SQLite 数据库: {migration['database_path']}")

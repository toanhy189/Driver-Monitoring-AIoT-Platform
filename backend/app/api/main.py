from fastapi import APIRouter

from app.api.routes import alerts, commands, configs, devices, users, ws, rules, history, videos

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(commands.router)
api_router.include_router(devices.router)
api_router.include_router(configs.router)
api_router.include_router(alerts.router)
api_router.include_router(ws.router)
api_router.include_router(rules.router)
api_router.include_router(history.router)
api_router.include_router(videos.router)

@api_router.get("/health")
def health():
    return {
        "status": "OK"
    }

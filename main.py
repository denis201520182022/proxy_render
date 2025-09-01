from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OpenAI Proxy Service", version="1.0.0")

# OpenAI API settings
OPENAI_API_URL = "https://api.openai.com"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY environment variable is not set!")
    raise ValueError("OPENAI_API_KEY is required")

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "OpenAI Proxy"}

@app.get("/health")
async def health():
    return {"status": "healthy", "openai_key_set": bool(OPENAI_API_KEY)}

# Основная функция для проксирования
async def proxy_request(request: Request, path: str):
    """
    Общая функция для проксирования запросов к OpenAI API
    """
    try:
        # Получаем тело запроса
        body = await request.body()
        
        # Подготавливаем заголовки
        headers = dict(request.headers)
        
        # Удаляем заголовки, которые могут вызвать проблемы
        headers.pop("host", None)
        headers.pop("content-length", None)
        headers.pop("content-encoding", None)
        headers.pop("transfer-encoding", None)
        
        # Добавляем или заменяем Authorization заголовок
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
        
        # Формируем URL (всегда добавляем /v1 для OpenAI API)
        target_url = f"{OPENAI_API_URL}/v1/{path}"
        
        logger.info(f"Proxying {request.method} request to: {target_url}")
        
        # Выполняем запрос к OpenAI
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params
            )
        
        # Подготавливаем заголовки ответа
        response_headers = dict(response.headers)
        # Удаляем проблемные заголовки ответа
        response_headers.pop("content-length", None)
        response_headers.pop("content-encoding", None)
        response_headers.pop("transfer-encoding", None)
        
        # Обрабатываем содержимое ответа
        try:
            if response.headers.get("content-type", "").startswith("application/json"):
                content = response.json()
            else:
                content = response.text
        except:
            content = {"error": "Failed to parse OpenAI response"}
            
        logger.info(f"Response status: {response.status_code}")
        
        return JSONResponse(
            content=content,
            status_code=response.status_code,
            headers=response_headers
        )
        
    except httpx.TimeoutException:
        logger.error(f"Timeout while proxying request to {path}")
        raise HTTPException(status_code=504, detail="Gateway Timeout")
    except httpx.RequestError as e:
        logger.error(f"Request error while proxying to {path}: {str(e)}")
        raise HTTPException(status_code=502, detail="Bad Gateway")
    except Exception as e:
        logger.error(f"Unexpected error while proxying to {path}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Маршрут для запросов с /v1 префиксом
@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_openai_v1(request: Request, path: str):
    """Проксирует запросы с /v1 префиксом"""
    return await proxy_request(request, path)

# Маршрут для прямых запросов без /v1 (для совместимости с вашим ботом)
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_openai_direct(request: Request, path: str):
    """Проксирует прямые запросы без /v1"""
    # Исключаем системные маршруты
    system_routes = ["", "health", "docs", "openapi.json", "redoc"]
    if path in system_routes or path.startswith("docs") or path.startswith("openapi"):
        raise HTTPException(status_code=404, detail="Not found")
    
    logger.info(f"Direct route called: /{path}")
    return await proxy_request(request, path)

# Тестовый эндпоинт для проверки связи с OpenAI
@app.post("/test")
async def test_openai():
    """Тестовый эндпоинт для проверки связи с OpenAI"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{OPENAI_API_URL}/v1/models",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
            )
            
        if response.status_code == 200:
            models_data = response.json()
            return {
                "status": "success",
                "openai_status": response.status_code,
                "models_count": len(models_data.get("data", [])),
                "message": "OpenAI API connection successful"
            }
        else:
            return {
                "status": "error",
                "openai_status": response.status_code,
                "message": "OpenAI API returned error"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to connect to OpenAI API"
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
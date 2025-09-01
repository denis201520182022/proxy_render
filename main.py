from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
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
    return {"status": "healthy"}

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_openai(request: Request, path: str):
    """
    Проксирует все запросы к OpenAI API
    """
    try:
        # Получаем тело запроса
        body = await request.body()
        
        # Подготавливаем заголовки
        headers = dict(request.headers)
        
        # Удаляем заголовки, которые могут вызвать проблемы
        headers.pop("host", None)
        headers.pop("content-length", None)
        
        # Добавляем или заменяем Authorization заголовок
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
        
        # Формируем URL
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
        
        # Возвращаем ответ
        return JSONResponse(
            content=response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
            status_code=response.status_code,
            headers=dict(response.headers)
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
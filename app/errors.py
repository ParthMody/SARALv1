from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarHTTP
import logging

logger = logging.getLogger("saral")

def install_error_handlers(app):
    @app.exception_handler(StarHTTP)
    async def http_exc(_: Request, exc: StarHTTP):
        return JSONResponse({"error": f"HTTP_{exc.status_code}", "detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse({"error": "INTERNAL_ERROR", "detail": "Unexpected error"}, status_code=500)

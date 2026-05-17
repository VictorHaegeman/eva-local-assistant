from fastapi import HTTPException, Request

from app.config import settings


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def is_loopback_request(request: Request) -> bool:
    return _client_host(request) in LOOPBACK_HOSTS


def is_request_trusted(request: Request) -> bool:
    if is_loopback_request(request):
        return True

    expected_token = settings.eva_api_token.strip()
    if not expected_token:
        return False

    provided_token = request.headers.get("x-eva-api-token", "").strip()
    return provided_token == expected_token


def require_sensitive_access(request: Request) -> bool:
    if is_request_trusted(request):
        return True

    raise HTTPException(
        status_code=403,
        detail=(
            "Acces refuse: cette route controle une capacite sensible d'Eva. "
            "Utilise le PC local ou configure X-Eva-Api-Token."
        ),
    )


def api_security_status() -> dict[str, object]:
    return {
        "loopback_trusted": True,
        "api_token_configured": bool(settings.eva_api_token.strip()),
        "cors_origins": settings.parsed_cors_origins,
        "phone_sensitive_access": (
            "token_required" if settings.eva_api_token.strip() else "blocked"
        ),
    }

from supabase import create_client, Client, ClientOptions
from app.core.config import settings

_supabase_client: Client | None = None


def get_supabase_client() -> Client:
    """Retorna una instancia singleton del cliente de Supabase."""
    global _supabase_client
    if _supabase_client is None:
        url = settings.effective_supabase_url
        key = settings.effective_supabase_key
        if not url or not key:
            raise ValueError(
                "Credenciales de Supabase no configuradas. Revisa SUPABASE_URL y SUPABASE_KEY en el archivo .env"
            )
        _supabase_client = create_client(url, key, options=ClientOptions(
            postgrest_client_timeout=settings.SUPABASE_TIMEOUT_SECONDS,
        ))
    return _supabase_client

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import List
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, date
import os
import json
import redis
from contextlib import contextmanager

app = FastAPI(
    title="API Vendas Real Time",
    description="API para consultar vendas do dia atual por loja",
    version="1.0.0"
)

# Configurações do banco de dados
DB_CONFIG = {
    "host": os.getenv("BD_A7_HOST"),
    "port": int(os.getenv("BD_A7_PORT", 5432)),
    "database": os.getenv("BD_A7_NAME"),
    "user": os.getenv("BD_A7_USER"),
    "password": os.getenv("BD_A7_PASSWORD"),
}

# Configurações do Redis
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DB", 0)),
    "password": os.getenv("REDIS_PASSWORD"),
}

SECRET_KEY = os.getenv("SECRET_KEY")
CACHE_TTL = 300  # 5 minutos em segundos
CACHE_KEY = "vendas_realtime"


# Models
class VendaItem(BaseModel):
    codigo: str
    loja: str
    total_quantidade: float
    venda_total: float


class VendasResponse(BaseModel):
    data_consulta: str
    periodo_inicio: str
    periodo_fim: str
    total_registros: int
    fonte: str  # "cache" ou "database"
    vendas: List[VendaItem]


# Redis connection
def get_redis_client():
    try:
        client = redis.Redis(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=REDIS_CONFIG["db"],
            password=REDIS_CONFIG["password"],
            decode_responses=True
        )
        client.ping()
        return client
    except redis.ConnectionError as e:
        print(f"Aviso: Não foi possível conectar ao Redis: {e}")
        return None


# Autenticação
async def verify_secret_key(x_secret_key: str = Header(..., alias="X-Secret-Key")):
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="SECRET_KEY não configurada no servidor")
    if x_secret_key != SECRET_KEY:
        raise HTTPException(status_code=401, detail="Secret Key inválida")
    return x_secret_key


# Conexão com o banco
@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro de conexão com o banco: {str(e)}")
    finally:
        if conn:
            conn.close()


def get_cached_data(redis_client):
    """Busca dados do cache Redis"""
    if redis_client is None:
        return None
    try:
        cached = redis_client.get(CACHE_KEY)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Erro ao buscar cache: {e}")
    return None


def set_cached_data(redis_client, data):
    """Salva dados no cache Redis com TTL de 5 minutos"""
    if redis_client is None:
        return
    try:
        redis_client.setex(CACHE_KEY, CACHE_TTL, json.dumps(data))
    except Exception as e:
        print(f"Erro ao salvar cache: {e}")


@app.get("/")
async def root():
    return {"message": "API Vendas Real Time", "status": "online"}


@app.get("/health")
async def health_check():
    redis_client = get_redis_client()
    redis_status = "connected" if redis_client else "disconnected"
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "redis": redis_status
    }


@app.get("/vendas-realtime", response_model=VendasResponse)
async def get_vendas_realtime(secret_key: str = Depends(verify_secret_key)):
    """
    Consulta as vendas do dia atual agrupadas por loja.

    Os dados são cacheados no Redis por 5 minutos para não sobrecarregar o banco.

    Requer header X-Secret-Key com a chave de autenticação.
    """
    redis_client = get_redis_client()

    # Tentar buscar do cache primeiro
    cached_data = get_cached_data(redis_client)
    if cached_data:
        return VendasResponse(
            data_consulta=cached_data["data_consulta"],
            periodo_inicio=cached_data["periodo_inicio"],
            periodo_fim=cached_data["periodo_fim"],
            total_registros=cached_data["total_registros"],
            fonte="cache",
            vendas=[VendaItem(**v) for v in cached_data["vendas"]]
        )

    # Se não tem cache, buscar do banco
    hoje = date.today()
    ts_start = datetime.combine(hoje, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
    ts_end = datetime.combine(hoje, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")

    sql = """
        SELECT
            u.codigo,
            u.nome as loja,
            SUM(iv.quantidade) as total_quantidade,
            SUM(iv.valortotal::double precision) AS venda_total
        FROM itemvenda iv
        LEFT JOIN unidadenegocio u ON u.id = iv.unidadenegocioid
        WHERE iv.datahora >= %s
          AND iv.datahora <= %s
          AND iv.status = 'F'
        GROUP BY 1, 2
        ORDER BY venda_total DESC;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, (ts_start, ts_end))
                results = cursor.fetchall()

        vendas = [
            VendaItem(
                codigo=str(row["codigo"] or ""),
                loja=str(row["loja"] or ""),
                total_quantidade=float(row["total_quantidade"] or 0),
                venda_total=float(row["venda_total"] or 0)
            )
            for row in results
        ]

        data_consulta = datetime.now().isoformat()

        # Salvar no cache
        cache_data = {
            "data_consulta": data_consulta,
            "periodo_inicio": ts_start,
            "periodo_fim": ts_end,
            "total_registros": len(vendas),
            "vendas": [v.model_dump() for v in vendas]
        }
        set_cached_data(redis_client, cache_data)

        return VendasResponse(
            data_consulta=data_consulta,
            periodo_inicio=ts_start,
            periodo_fim=ts_end,
            total_registros=len(vendas),
            fonte="database",
            vendas=vendas
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar vendas: {str(e)}")


@app.delete("/cache")
async def clear_cache(secret_key: str = Depends(verify_secret_key)):
    """
    Limpa o cache do Redis forçando uma nova consulta ao banco.

    Requer header X-Secret-Key com a chave de autenticação.
    """
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.delete(CACHE_KEY)
            return {"message": "Cache limpo com sucesso"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao limpar cache: {str(e)}")
    return {"message": "Redis não disponível, nada a limpar"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8083))
    uvicorn.run(app, host="0.0.0.0", port=port)

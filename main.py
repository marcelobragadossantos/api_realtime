from fastapi import FastAPI, HTTPException, Header, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, date, timezone, timedelta
import os
import json
import redis
from contextlib import contextmanager
from calendar import monthrange

# Timezone de Brasília (UTC-3)
BRASILIA_TZ = timezone(timedelta(hours=-3))

app = FastAPI(
    title="API Vendas Real Time",
    description="API para consultar vendas por loja com filtros de data",
    version="1.2.1"
)

# Configuração CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
CACHE_KEY_PREFIX = "vendas_realtime"


# Models
class VendaItem(BaseModel):
    codigo: str
    loja: str
    regional: str = ""
    numero_vendas: int = 0
    total_quantidade: float
    venda_total: float
    custo: float = 0.0
    tempo_ultimo_envio: str = ""


class VendasResponse(BaseModel):
    data_consulta: str
    periodo_inicio: str
    periodo_fim: str
    total_registros: int
    fonte: str
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


def get_cache_key(ts_start: str, ts_end: str) -> str:
    """Gera chave de cache única para o período"""
    return f"{CACHE_KEY_PREFIX}:{ts_start}:{ts_end}"


def get_cached_data(redis_client, cache_key: str):
    """Busca dados do cache Redis"""
    if redis_client is None:
        return None
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Erro ao buscar cache: {e}")
    return None


def set_cached_data(redis_client, cache_key: str, data):
    """Salva dados no cache Redis com TTL de 5 minutos"""
    if redis_client is None:
        return
    try:
        redis_client.setex(cache_key, CACHE_TTL, json.dumps(data))
    except Exception as e:
        print(f"Erro ao salvar cache: {e}")


@app.get("/")
async def root():
    return {"message": "API Vendas Real Time", "status": "online"}


def now_brasilia():
    """Retorna datetime atual no fuso horário de Brasília"""
    return datetime.now(BRASILIA_TZ)


def today_brasilia():
    """Retorna date atual no fuso horário de Brasília"""
    return now_brasilia().date()


def parse_date(date_str: str) -> date:
    """Converte string para date no formato YYYY-MM-DD"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de data inválido: {date_str}. Use o formato YYYY-MM-DD"
        )


def get_month_range(data_ref: date) -> tuple:
    """Retorna o primeiro e último dia do mês de uma data de referência"""
    primeiro_dia = date(data_ref.year, data_ref.month, 1)
    ultimo_dia_num = monthrange(data_ref.year, data_ref.month)[1]
    ultimo_dia = date(data_ref.year, data_ref.month, ultimo_dia_num)
    return primeiro_dia, ultimo_dia


def fetch_vendas_from_db(ts_start: str, ts_end: str) -> List[VendaItem]:
    """Busca vendas do banco de dados para um período"""
    sql = """
        SELECT
            u.codigo,
            u.nome as loja,
            REPLACE(g.nome, 'REGIONAL ', '') as regional,
            COUNT(DISTINCT iv.vendaid) as numero_vendas,
            SUM(iv.quantidade) as total_quantidade,
            SUM(iv.valortotal::double precision) AS venda_total,
            SUM(m.custo * iv.quantidade::double precision) AS custo,
            vm.tempoultimoenvio as tempo_ultimo_envio
        FROM itemvenda iv
        LEFT JOIN unidadenegocio u ON u.id = iv.unidadenegocioid
        LEFT JOIN grupounidadenegocio g ON g.id = u.grupounidadenegocioid
        LEFT JOIN v_monitorsincronizacao vm ON vm.unidadenegocioid = u.id
        LEFT JOIN movimentacaoestoque m ON m.id = iv.movimentacaoestoqueid
        WHERE iv.datahora >= %s
          AND iv.datahora <= %s
          AND iv.status = 'F'
        GROUP BY 1, 2, 3, 8
        ORDER BY venda_total DESC;
    """

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, (ts_start, ts_end))
            results = cursor.fetchall()

    return [
        VendaItem(
            codigo=str(row["codigo"] or ""),
            loja=str(row["loja"] or ""),
            regional=str(row["regional"] or ""),
            numero_vendas=int(row["numero_vendas"] or 0),
            total_quantidade=round(float(row["total_quantidade"] or 0), 2),
            venda_total=round(float(row["venda_total"] or 0), 2),
            custo=round(float(row["custo"] or 0), 2),
            tempo_ultimo_envio=str(row["tempo_ultimo_envio"] or "")
        )
        for row in results
    ]


def get_vendas_periodo(redis_client, ts_start: str, ts_end: str) -> tuple:
    """
    Busca vendas de um período, primeiro tentando cache, depois banco.
    Retorna (vendas, fonte)
    """
    cache_key = get_cache_key(ts_start, ts_end)

    # Tentar cache primeiro
    cached_data = get_cached_data(redis_client, cache_key)
    if cached_data:
        vendas = [VendaItem(**v) for v in cached_data["vendas"]]
        return vendas, "cache"

    # Buscar do banco
    vendas = fetch_vendas_from_db(ts_start, ts_end)

    # Salvar no cache
    cache_data = {
        "data_consulta": now_brasilia().isoformat(),
        "periodo_inicio": ts_start,
        "periodo_fim": ts_end,
        "total_registros": len(vendas),
        "vendas": [v.model_dump() for v in vendas]
    }
    set_cached_data(redis_client, cache_key, cache_data)

    return vendas, "database"


def cache_month_data_background(data_referencia: date):
    """
    Função executada em background para cachear dados do mês.
    """
    try:
        redis_client = get_redis_client()
        primeiro_dia, ultimo_dia = get_month_range(data_referencia)
        ts_mes_start = datetime.combine(primeiro_dia, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        ts_mes_end = datetime.combine(ultimo_dia, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")

        cache_key = get_cache_key(ts_mes_start, ts_mes_end)

        # Só busca se não estiver em cache
        if not get_cached_data(redis_client, cache_key):
            print(f"Background: Cacheando dados do mês {data_referencia.month}/{data_referencia.year}")
            get_vendas_periodo(redis_client, ts_mes_start, ts_mes_end)
            print(f"Background: Cache do mês concluído")
    except Exception as e:
        print(f"Erro ao cachear dados do mês em background: {e}")


@app.get("/health")
async def health_check():
    redis_client = get_redis_client()
    redis_status = "connected" if redis_client else "disconnected"
    return {
        "status": "healthy",
        "timestamp": now_brasilia().isoformat(),
        "redis": redis_status
    }


@app.get("/vendas-realtime", response_model=VendasResponse)
async def get_vendas_realtime(
    background_tasks: BackgroundTasks,
    secret_key: str = Depends(verify_secret_key),
    data: Optional[str] = Query(None, description="Data específica (YYYY-MM-DD)"),
    data_inicio: Optional[str] = Query(None, description="Data início do período (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim do período (YYYY-MM-DD)")
):
    """
    Consulta as vendas agrupadas por loja.

    **Parâmetros de data (opcionais):**
    - Sem parâmetros: retorna vendas do dia atual
    - `data`: retorna vendas de uma data específica
    - `data_inicio` + `data_fim`: retorna vendas somadas do período

    Quando a consulta é de um dia específico, os dados do mês são cacheados
    em background para acelerar futuras consultas mensais.

    Os dados são cacheados no Redis por 5 minutos para não sobrecarregar o banco.

    Requer header X-Secret-Key com a chave de autenticação.
    """
    redis_client = get_redis_client()
    is_single_day = False
    data_referencia = None

    # Determinar período de consulta
    if data:
        # Data específica
        data_parsed = parse_date(data)
        ts_start = datetime.combine(data_parsed, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        ts_end = datetime.combine(data_parsed, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")
        is_single_day = True
        data_referencia = data_parsed
    elif data_inicio and data_fim:
        # Range de datas
        data_inicio_parsed = parse_date(data_inicio)
        data_fim_parsed = parse_date(data_fim)
        if data_inicio_parsed > data_fim_parsed:
            raise HTTPException(
                status_code=400,
                detail="data_inicio não pode ser maior que data_fim"
            )
        ts_start = datetime.combine(data_inicio_parsed, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        ts_end = datetime.combine(data_fim_parsed, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")
    elif data_inicio or data_fim:
        # Apenas um dos parâmetros de range foi informado
        raise HTTPException(
            status_code=400,
            detail="Para consultar um período, informe data_inicio e data_fim"
        )
    else:
        # Dia atual (comportamento padrão)
        hoje = today_brasilia()
        ts_start = datetime.combine(hoje, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        ts_end = datetime.combine(hoje, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")
        is_single_day = True
        data_referencia = hoje

    try:
        # Buscar vendas do período principal
        vendas, fonte = get_vendas_periodo(redis_client, ts_start, ts_end)
        data_consulta = now_brasilia().isoformat()

        # Se for consulta de um dia, cachear dados do mês em background
        if is_single_day and data_referencia:
            background_tasks.add_task(cache_month_data_background, data_referencia)

        return VendasResponse(
            data_consulta=data_consulta,
            periodo_inicio=ts_start,
            periodo_fim=ts_end,
            total_registros=len(vendas),
            fonte=fonte,
            vendas=vendas
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar vendas: {str(e)}")


@app.delete("/cache")
async def clear_cache(secret_key: str = Depends(verify_secret_key)):
    """
    Limpa todo o cache do Redis forçando novas consultas ao banco.

    Requer header X-Secret-Key com a chave de autenticação.
    """
    redis_client = get_redis_client()
    if redis_client:
        try:
            # Buscar e deletar todas as chaves com o prefixo
            keys = redis_client.keys(f"{CACHE_KEY_PREFIX}:*")
            if keys:
                redis_client.delete(*keys)
            return {"message": f"Cache limpo com sucesso ({len(keys)} chaves removidas)"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao limpar cache: {str(e)}")
    return {"message": "Redis não disponível, nada a limpar"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8083))
    uvicorn.run(app, host="0.0.0.0", port=port)

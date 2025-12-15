from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, date
import os
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

SECRET_KEY = os.getenv("SECRET_KEY")


# Models
class VendaItem(BaseModel):
    embalagemid: str
    unidadenegocioid: str
    total_quantidade: float
    venda_total: float


class VendasResponse(BaseModel):
    data_consulta: str
    periodo_inicio: str
    periodo_fim: str
    total_registros: int
    vendas: List[VendaItem]


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


@app.get("/")
async def root():
    return {"message": "API Vendas Real Time", "status": "online"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/vendas-realtime", response_model=VendasResponse)
async def get_vendas_realtime(secret_key: str = Depends(verify_secret_key)):
    """
    Consulta as vendas do dia atual agrupadas por loja (unidadenegocioid) e embalagem.

    Requer header X-Secret-Key com a chave de autenticação.
    """
    hoje = date.today()
    ts_start = datetime.combine(hoje, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
    ts_end = datetime.combine(hoje, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")

    sql = """
        SELECT
            iv.embalagemid::text AS embalagemid,
            iv.unidadenegocioid::text AS unidadenegocioid,
            SUM(iv.quantidade) as total_quantidade,
            SUM(iv.valortotal::double precision) AS venda_total
        FROM itemvenda iv
        WHERE iv.datahora >= %s
          AND iv.datahora <= %s
          AND iv.status = 'F'
        GROUP BY 1, 2;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, (ts_start, ts_end))
                results = cursor.fetchall()

        vendas = [
            VendaItem(
                embalagemid=row["embalagemid"],
                unidadenegocioid=row["unidadenegocioid"],
                total_quantidade=float(row["total_quantidade"] or 0),
                venda_total=float(row["venda_total"] or 0)
            )
            for row in results
        ]

        return VendasResponse(
            data_consulta=datetime.now().isoformat(),
            periodo_inicio=ts_start,
            periodo_fim=ts_end,
            total_registros=len(vendas),
            vendas=vendas
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar vendas: {str(e)}")


@app.get("/vendas-por-loja")
async def get_vendas_por_loja(secret_key: str = Depends(verify_secret_key)):
    """
    Consulta as vendas do dia atual totalizadas por loja (unidadenegocioid).

    Requer header X-Secret-Key com a chave de autenticação.
    """
    hoje = date.today()
    ts_start = datetime.combine(hoje, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
    ts_end = datetime.combine(hoje, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")

    sql = """
        SELECT
            iv.unidadenegocioid::text AS unidadenegocioid,
            COUNT(DISTINCT iv.embalagemid) as total_produtos,
            SUM(iv.quantidade) as total_quantidade,
            SUM(iv.valortotal::double precision) AS venda_total
        FROM itemvenda iv
        WHERE iv.datahora >= %s
          AND iv.datahora <= %s
          AND iv.status = 'F'
        GROUP BY 1
        ORDER BY venda_total DESC;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, (ts_start, ts_end))
                results = cursor.fetchall()

        lojas = [
            {
                "unidadenegocioid": row["unidadenegocioid"],
                "total_produtos": int(row["total_produtos"] or 0),
                "total_quantidade": float(row["total_quantidade"] or 0),
                "venda_total": float(row["venda_total"] or 0)
            }
            for row in results
        ]

        total_geral = sum(loja["venda_total"] for loja in lojas)

        return {
            "data_consulta": datetime.now().isoformat(),
            "periodo_inicio": ts_start,
            "periodo_fim": ts_end,
            "total_lojas": len(lojas),
            "total_geral": total_geral,
            "lojas": lojas
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar vendas: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

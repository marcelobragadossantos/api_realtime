# API Vendas Real Time

API para consultar vendas do dia atual por loja com cache Redis.

## Endpoints

### `GET /`
Health check basico.

### `GET /health`
Verifica status da API e conexao com Redis.

### `GET /vendas-realtime`
Retorna vendas do dia atual agrupadas por loja.

**Cache:** Os dados sao cacheados no Redis por 5 minutos para nao sobrecarregar o banco.

**Headers obrigatorios:**
- `X-Secret-Key`: Chave de autenticacao

**Resposta:**
```json
{
  "data_consulta": "2025-01-15T10:30:00",
  "periodo_inicio": "2025-01-15 00:00:00",
  "periodo_fim": "2025-01-15 23:59:59",
  "total_registros": 5,
  "fonte": "database",
  "vendas": [
    {
      "codigo": "001",
      "loja": "Loja Centro",
      "total_quantidade": 500,
      "venda_total": 15000.00
    }
  ]
}
```

O campo `fonte` indica se os dados vieram do `cache` ou do `database`.

### `DELETE /cache`
Limpa o cache do Redis forcando uma nova consulta ao banco.

**Headers obrigatorios:**
- `X-Secret-Key`: Chave de autenticacao

## Variaveis de Ambiente

Configure as seguintes variaveis no EasyPanel:

| Variavel | Descricao |
|----------|-----------|
| `BD_A7_HOST` | Host do banco PostgreSQL |
| `BD_A7_PORT` | Porta do banco (padrao: 5432) |
| `BD_A7_NAME` | Nome do banco de dados |
| `BD_A7_USER` | Usuario do banco |
| `BD_A7_PASSWORD` | Senha do banco |
| `SECRET_KEY` | Chave para autenticacao da API |
| `REDIS_HOST` | Host do Redis |
| `REDIS_PORT` | Porta do Redis (padrao: 6379) |
| `REDIS_DB` | Banco do Redis |
| `REDIS_PASSWORD` | Senha do Redis |

## Deploy no EasyPanel

1. Crie um novo servico no EasyPanel
2. Conecte o repositorio Git
3. Configure as variaveis de ambiente
4. Deploy!

## Exemplo de uso com curl

```bash
curl -X GET "https://sua-api.com/vendas-realtime" \
  -H "X-Secret-Key: sua_secret_key"
```

## Desenvolvimento local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variaveis de ambiente
cp .env.example .env
# Editar .env com suas configuracoes

# Executar
python main.py
```

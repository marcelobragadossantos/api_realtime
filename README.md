# API Vendas Real Time

API para consultar vendas do dia atual por loja.

## Endpoints

### `GET /`
Health check básico.

### `GET /health`
Verifica status da API.

### `GET /vendas-realtime`
Retorna vendas do dia atual agrupadas por loja e embalagem.

**Headers obrigatórios:**
- `X-Secret-Key`: Chave de autenticação

**Resposta:**
```json
{
  "data_consulta": "2025-01-15T10:30:00",
  "periodo_inicio": "2025-01-15 00:00:00",
  "periodo_fim": "2025-01-15 23:59:59",
  "total_registros": 100,
  "vendas": [
    {
      "embalagemid": "123",
      "unidadenegocioid": "1",
      "total_quantidade": 50,
      "venda_total": 1500.00
    }
  ]
}
```

### `GET /vendas-por-loja`
Retorna vendas do dia atual totalizadas por loja.

**Headers obrigatórios:**
- `X-Secret-Key`: Chave de autenticação

**Resposta:**
```json
{
  "data_consulta": "2025-01-15T10:30:00",
  "periodo_inicio": "2025-01-15 00:00:00",
  "periodo_fim": "2025-01-15 23:59:59",
  "total_lojas": 5,
  "total_geral": 50000.00,
  "lojas": [
    {
      "unidadenegocioid": "1",
      "total_produtos": 150,
      "total_quantidade": 500,
      "venda_total": 15000.00
    }
  ]
}
```

## Variáveis de Ambiente

Configure as seguintes variáveis no EasyPanel:

| Variável | Descrição |
|----------|-----------|
| `BD_A7_HOST` | Host do banco PostgreSQL |
| `BD_A7_PORT` | Porta do banco (padrão: 5432) |
| `BD_A7_NAME` | Nome do banco de dados |
| `BD_A7_USER` | Usuário do banco |
| `BD_A7_PASSWORD` | Senha do banco |
| `SECRET_KEY` | Chave para autenticação da API |

## Deploy no EasyPanel

1. Crie um novo serviço no EasyPanel
2. Conecte o repositório Git
3. Configure as variáveis de ambiente
4. Deploy!

## Exemplo de uso com curl

```bash
curl -X GET "https://sua-api.com/vendas-realtime" \
  -H "X-Secret-Key: sua_secret_key"
```

## Desenvolvimento local

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas configurações

# Executar
python main.py
```

# Guia de Integracao - API Vendas Real Time no Power BI

## Informacoes da API

| Item | Valor |
|------|-------|
| **URL Base** | `https://sua-url-easypanel.com` |
| **Endpoint** | `/vendas-realtime` |
| **Metodo** | GET |
| **Autenticacao** | Header `X-Secret-Key` |

---

## Passo a Passo no Power BI Desktop

### 1. Abrir o Editor de Consultas

1. Abra o **Power BI Desktop**
2. Clique em **Obter Dados** > **Consulta em Branco**
3. No Editor de Consultas, clique em **Editor Avancado**

### 2. Codigo M para Conectar na API

Cole o seguinte codigo no Editor Avancado:

```m
let
    // Configuracoes
    url = "https://SUA-URL-API.com/vendas-realtime",
    secretKey = "c456b90d8e8a11371b63822d3f08892f14f47e986eae0d49124dea3ee5eeea42",

    // Requisicao com header de autenticacao
    Source = Json.Document(
        Web.Contents(
            url,
            [
                Headers = [
                    #"X-Secret-Key" = secretKey,
                    #"Content-Type" = "application/json"
                ]
            ]
        )
    ),

    // Expandir lista de vendas
    vendas = Source[vendas],

    // Converter para tabela
    TabelaVendas = Table.FromList(vendas, Splitter.SplitByNothing(), null, null, ExtraValues.Error),

    // Expandir colunas
    Expandido = Table.ExpandRecordColumn(TabelaVendas, "Column1", {"codigo", "loja", "total_quantidade", "venda_total"}),

    // Definir tipos de dados
    TiposDefinidos = Table.TransformColumnTypes(Expandido, {
        {"codigo", type text},
        {"loja", type text},
        {"total_quantidade", type number},
        {"venda_total", Currency.Type}
    })
in
    TiposDefinidos
```

### 3. Ajustar a URL

Substitua `https://SUA-URL-API.com` pela URL real da sua API no EasyPanel.

### 4. Configurar Credenciais

Quando o Power BI pedir credenciais:
1. Selecione **Anonimo** (a autenticacao ja esta no header)
2. Clique em **Conectar**

---

## Codigo Alternativo - Com Metadados

Se quiser incluir data da consulta e periodo:

```m
let
    // Configuracoes
    url = "https://SUA-URL-API.com/vendas-realtime",
    secretKey = "c456b90d8e8a11371b63822d3f08892f14f47e986eae0d49124dea3ee5eeea42",

    // Requisicao
    Source = Json.Document(
        Web.Contents(
            url,
            [
                Headers = [
                    #"X-Secret-Key" = secretKey
                ]
            ]
        )
    ),

    // Extrair metadados
    dataConsulta = Source[data_consulta],
    periodoInicio = Source[periodo_inicio],
    periodoFim = Source[periodo_fim],
    fonte = Source[fonte],
    totalRegistros = Source[total_registros],

    // Converter vendas para tabela
    vendas = Source[vendas],
    TabelaVendas = Table.FromList(vendas, Splitter.SplitByNothing(), null, null, ExtraValues.Error),
    Expandido = Table.ExpandRecordColumn(TabelaVendas, "Column1", {"codigo", "loja", "total_quantidade", "venda_total"}),

    // Adicionar colunas de metadados
    ComDataConsulta = Table.AddColumn(Expandido, "data_consulta", each dataConsulta),
    ComFonte = Table.AddColumn(ComDataConsulta, "fonte_dados", each fonte),

    // Definir tipos
    TiposDefinidos = Table.TransformColumnTypes(ComFonte, {
        {"codigo", type text},
        {"loja", type text},
        {"total_quantidade", type number},
        {"venda_total", Currency.Type},
        {"data_consulta", type datetime},
        {"fonte_dados", type text}
    })
in
    TiposDefinidos
```

---

## Atualizacao Automatica

### No Power BI Service (Online)

1. Publique o relatorio no Power BI Service
2. Va em **Configuracoes do Conjunto de Dados**
3. Em **Atualizacao Agendada**, configure:
   - Frequencia: A cada 15 minutos (ou conforme necessidade)
   - Fuso horario: Brasilia

### Importante sobre Cache

A API tem cache de **5 minutos**. Isso significa:
- Consultas dentro de 5 min retornam dados do cache (mais rapido)
- Apos 5 min, busca dados novos do banco
- O campo `fonte_dados` indica se veio do "cache" ou "database"

---

## Estrutura dos Dados Retornados

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `codigo` | Texto | Codigo da loja |
| `loja` | Texto | Nome da loja |
| `total_quantidade` | Numero | Quantidade total de itens vendidos |
| `venda_total` | Moeda | Valor total de vendas |

---

## Exemplo de Resposta da API

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
    },
    {
      "codigo": "002",
      "loja": "Loja Shopping",
      "total_quantidade": 350,
      "venda_total": 12000.00
    }
  ]
}
```

---

## Testando a API

Antes de configurar no Power BI, teste a API com curl ou Postman:

### Curl
```bash
curl -X GET "https://SUA-URL-API.com/vendas-realtime" \
  -H "X-Secret-Key: c456b90d8e8a11371b63822d3f08892f14f47e986eae0d49124dea3ee5eeea42"
```

### Postman
1. Metodo: GET
2. URL: `https://SUA-URL-API.com/vendas-realtime`
3. Headers:
   - Key: `X-Secret-Key`
   - Value: `c456b90d8e8a11371b63822d3f08892f14f47e986eae0d49124dea3ee5eeea42`

---

## Troubleshooting

| Erro | Solucao |
|------|---------|
| 401 Unauthorized | Verifique se o X-Secret-Key esta correto |
| 500 Internal Server Error | Verifique as variaveis de ambiente no EasyPanel |
| Timeout | A API pode estar iniciando, aguarde alguns segundos |
| Dados vazios | Pode nao ter vendas no dia atual |

---

## Suporte

- Endpoint de health check: `GET /health`
- Limpar cache manualmente: `DELETE /cache` (com header X-Secret-Key)

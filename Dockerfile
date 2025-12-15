FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema para psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Expor porta
EXPOSE 8083

# Variavel de ambiente para porta (pode ser sobrescrita no EasyPanel)
ENV PORT=8083

# Comando para iniciar a aplicação
CMD uvicorn main:app --host 0.0.0.0 --port $PORT

# Usa a imagem oficial do uv numa etapa auxiliar para copiar apenas seus binários.
FROM ghcr.io/astral-sh/uv:0.11.3 AS uv
# Define a imagem final enxuta com Python 3.11, a versão mínima escolhida no projeto.
FROM python:3.11-slim

# Leva uv e uvx para a imagem final sem instalar uv via pip.
COPY --from=uv /uv /uvx /bin/

# Define a pasta de trabalho padrão para os comandos executados no container.
WORKDIR /app

# Cria um usuário sem privilégios de root para executar a aplicação.
RUN useradd --create-home --uid 10001 --user-group app

# Copia primeiro os manifests para aproveitar o cache de dependências do Docker.
COPY pyproject.toml uv.lock ./
# No caso deste desafio, instalamos dependências de desenvolvimento para facilitar testes e análise estática no container.
RUN uv sync --frozen --group dev --no-install-project
# Copia o código do pacote e o deixa acessível ao usuário sem privilégios.
COPY --chown=app:app carrefour_transpiler ./carrefour_transpiler

# Define o caminho compartilhado onde a aplicação temporariamente guarda imagens.
ENV CARREFOUR_IMAGE_STORAGE_PATH=/var/run/carrefour/images
# Permite executar diretamente os programas instalados no ambiente virtual.
ENV PATH=/app/.venv/bin:$PATH

# Executa os processos da aplicação como usuário não root.
USER app
# Mantém o serviço ativo para que comandos futuros possam usar `docker compose exec`.
CMD ["sleep", "infinity"]

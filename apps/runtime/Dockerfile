# Usa uma versão do uv compatível com o build backend declarado pelo app.
FROM ghcr.io/astral-sh/uv:0.12.20 AS uv
# Define a imagem final enxuta com Python 3.11, a versão mínima escolhida no projeto.
FROM python:3.11-slim

# Leva uv e uvx para a imagem final sem instalar uv via pip.
COPY --from=uv /uv /uvx /bin/

# Define a pasta de trabalho padrão para os comandos executados no container.
WORKDIR /app

# Cria um usuário sem privilégios de root para executar a aplicação.
RUN useradd --create-home --uid 10001 --user-group app

# Copia os manifests e o README, exigido pelo metadata do pacote.
COPY pyproject.toml uv.lock README.md ./
# No caso deste desafio, instalamos dependências de desenvolvimento para facilitar testes e análise estática no container.
RUN uv sync --frozen --group dev --no-install-project
# Copia o código-fonte do runtime para o contexto independente do app.
COPY --chown=app:app src ./src
# Copia os testes para que possam ser executados dentro da imagem.
COPY --chown=app:app tests ./tests
# Instala o pacote runtime no ambiente virtual criado por uv.
RUN uv sync --frozen --group dev
# Permite que o usuário do runtime grave caches sem executar como root.
RUN chown app:app /app

# Define o caminho compartilhado onde a aplicação temporariamente guarda imagens.
ENV CARREFOUR_IMAGE_STORAGE_PATH=/var/run/carrefour/images
# Permite executar diretamente os programas instalados no ambiente virtual.
ENV PATH=/app/.venv/bin:$PATH

# Executa os processos da aplicação como usuário não root.
USER app
# Mantém o serviço ativo para que comandos futuros possam usar `docker compose exec`.
CMD ["sleep", "infinity"]

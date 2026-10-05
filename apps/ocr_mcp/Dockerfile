# Usa a versão do uv fixada no projeto para instalar dependências sem pip.
FROM ghcr.io/astral-sh/uv:0.12.20 AS uv
# Usa Python 3.11 como runtime do servidor MCP.
FROM python:3.11-slim

# Copia uv para instalar dependências no ambiente virtual do app.
COPY --from=uv /uv /uvx /bin/

# Mantém a relação do monorepo necessária para resolver o workspace compartilhado.
WORKDIR /workspace/apps/ocr_mcp

# Cria usuário sem privilégios para executar o servidor.
RUN useradd --create-home --uid 10001 --user-group app

# Mantém o ambiente virtual em diretório próprio do container.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
# Copia o pacote compartilhado para sua posição relativa no monorepo da imagem.
COPY --from=observability . /workspace/packages/carrefour_observability/
# Copia manifests e README, usado pelos metadados do pacote.
COPY pyproject.toml uv.lock README.md ./
# Instala dependências de desenvolvimento para facilitar testes e análise no container.
RUN uv sync --frozen --group dev --no-install-project
# Copia o código-fonte do servidor OCR.
COPY --chown=app:app src ./src
# Copia os testes que podem ser executados dentro da imagem.
COPY --chown=app:app tests ./tests
# Instala o pacote OCR no ambiente virtual criado pelo uv.
RUN uv sync --frozen --group dev
# Garante que o usuário possa usar o diretório sem alterar dono de cada dependência.
RUN chown app:app /app /workspace/apps/ocr_mcp

# Define o diretório de imagens que o runtime monta como volume compartilhado.
ENV CARREFOUR_IMAGE_STORAGE_PATH=/var/run/carrefour/images
# Configura o Host HTTP esperado pela rede interna do Compose.
ENV CARREFOUR_OCR_ALLOWED_HOSTS=ocr-mcp:8000
# Prioriza os executáveis instalados no ambiente virtual do app.
ENV PATH=/app/.venv/bin:$PATH

# Executa o servidor sem privilégios de root.
USER app
# Inicia o servidor MCP usando HTTP+SSE na porta 8000.
CMD ["python", "-m", "carrefour_ocr_mcp"]

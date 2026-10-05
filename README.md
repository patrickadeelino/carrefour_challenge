# Carrefour Challenge

**Estado:** Fase 1 concluída; OCR e RAG estão disponíveis como serviços independentes. A API fictícia da subfase 2.3 já foi implementada e aguarda revisão antes dos testes de integração entre componentes.

O projeto constrói um agente exam scheduler a partir de uma especificação declarativa. A Fase 1 valida o JSON e gera uma factory Python para o Google ADK. A Fase 2 prepara os serviços e integrações do fluxo de atendimento.

## Fluxo da Fase 1

~~~text
specification.json -> validação Pydantic -> geração determinística de uma factory Python
~~~

A especificação escolhe tools por IDs registrados no projeto. Ela não aceita código, instruções livres, credenciais ou endereços de servidores MCP. A factory gerada recebe implementações aprovadas pelo runtime e valida que o conjunto de IDs corresponde exatamente ao declarado antes de criar o agente.

A geração produz código-fonte; não executa a factory nem inicia o agente. O código gerado define `create_agent(registered_tools)`, que instancia um `Agent` do Google ADK quando for chamado.

## Estado da Fase 2

O componente `TemporaryImageStore`, em `apps/runtime/src/carrefour_runtime/services/image_storage/temporary_store.py`, valida o conteúdo real da imagem, aceita `PNG` e `JPG` até 10 MB, grava os bytes sob um `UUID` com promoção atômica e remove imagens órfãs com mais de 30 minutos durante uma nova gravação.

O Docker Compose inicia os apps em containers independentes. O volume `tmpfs` de 64 MiB pode ser gravado pelo runtime e é montado como somente leitura no OCR. O comando `process --path <nome>` carrega a factory gerada, envia somente o UUID da imagem ao agente e captura o resultado estruturado de `extract_exams` por SSE. O RAG expõe `search_exams` por SSE e resolve nomes no catálogo fictício. A API de agendamento persiste reservas em SQLite e ainda não está conectada ao agente.

## Documentação

- [PRD da Fase 1](docs/PRD.md): objetivo, escopo e critérios de conclusão.
- [Plano da Fase 1](docs/phase1-plan.md): etapas acordadas e entregas concluídas.
- [Especificação técnica da Fase 1](docs/phase1-spec.md): formato do JSON, validações, tools e geração determinística.
- [System Design — arquitetura dos containers](docs/system-design.md): containers, integrações e fronteiras de confiança.
- [Plano da Fase 2](docs/phase2-plan.md): decisões e checklist das próximas subfases.
- [Workflow de desenvolvimento](docs/playbooks/development-workflow.md): ciclo de mudança, revisão, validação e transparência no uso de IA.
- [Playbook de logging](docs/playbooks/logging.md): eventos estruturados, 5 Ws e política de privacidade.
- [Playbook de testes](docs/playbooks/testing.md): organização e execução das suítes nos containers.
- [App runtime](apps/runtime/README.md): responsabilidades e limite do projeto Python executável.
- [App RAG MCP](apps/rag_mcp/README.md): catálogo, busca, transporte SSE, logs e validações.
- [Schedule API](apps/schedule_api/README.md): contrato HTTP, JWT local, DI, ciclo de vida do SQLite, logs, Swagger e testes.
- [Handoff da Fase 1](docs/HANDOFF_FASE_1.md): decisões e contexto para continuidade.
- [Exemplo de especificação](specification.json).

## Requisitos no host

- Docker Engine com Docker Compose
- Git para obter o repositório

Python, uv e as dependências do projeto são instalados dentro da imagem. Não é necessário instalar esses componentes no host.

## Construir e iniciar o container

~~~sh
docker compose up -d --build assistant-runtime ocr-mcp rag-mcp

# A API de agendamento é iniciada quando você quiser validar seu contrato.
docker compose up -d --build schedule-api
~~~

Cada app é construído de forma independente a partir de sua própria pasta, com `pyproject.toml` e `uv.lock` próprios. O repositório é montado em `/workspace` no runtime para acessar `specification.json` e as imagens de demonstração. Os containers executam como usuário não root. Se o GID do grupo do host não for 1000, configure `CARREFOUR_RUNTIME_GID` no arquivo `.env` do projeto.

O Compose principal constrói os alvos `dev`, com pytest, Ruff e Mypy disponíveis nos containers. Para construir e iniciar as imagens `runtime`, sem essas dependências, use o overlay:

~~~sh
docker compose -f compose.yaml -f compose.runtime.yaml up -d --build assistant-runtime ocr-mcp rag-mcp schedule-api
~~~

Os alvos `runtime` e `dev` compartilham as camadas das dependências de produção; ferramentas de desenvolvimento são acrescentadas apenas ao alvo `dev`.

O OCR precisa da chave do Cloud Vision no ambiente de execução. Para Compose local, adicione a variável ao `.env` ignorado pelo Git:

~~~dotenv
GOOGLE_CLOUD_VISION_API_KEY=sua-chave
GOOGLE_API_KEY=sua-chave-da-gemini
~~~

`GOOGLE_CLOUD_VISION_API_KEY` é entregue somente ao OCR. `GOOGLE_API_KEY` é entregue somente ao runtime para executar o modelo declarado na especificação. As chaves não são incluídas no build. O OCR atende em `http://ocr-mcp:8000/sse` e o RAG em `http://rag-mcp:8000/sse` dentro da rede Compose; nenhuma dessas portas é publicada no host.

Para parar o ambiente:

~~~sh
docker compose down
~~~

Todos os comandos de aplicação abaixo são executados dentro do container em execução. Eles devem ser chamados a partir da raiz do repositório no host.

## Validar e gerar o agente

Validar o exemplo:

~~~sh
docker compose exec assistant-runtime python -m carrefour_runtime validate specification.json
~~~

Gerar a factory Python:

~~~sh
docker compose exec assistant-runtime python -m carrefour_runtime generate specification.json --output generated/agent.py
~~~

O arquivo gerado é código-fonte. A execução e o despacho das tools são exercitados separadamente pelos testes com o `InMemoryRunner` do ADK e um modelo determinístico.

## Processar um pedido de exames

Gere primeiro `generated/agent.py`, mantenha os arquivos de entrada em `tests/fixtures/images/` e passe somente o nome do arquivo:

~~~sh
docker compose exec assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br_simplified.png
~~~

O comando valida o conteúdo PNG/JPG e o limite de 10 MB, cria uma cópia temporária identificada por UUID e executa a tool OCR. O caminho local e os bytes da imagem não entram no prompt. A saída normal é JSON `{"exams": [...]}` com código 0; uma revisão manual retorna `{"status":"review_required", ...}` com código 2; erros sanitizados são escritos em `stderr` com código 1. O runtime aceita um processamento por vez e remove a imagem temporária ao concluir.

Os eventos operacionais do runtime e do OCR são logs JSON enviados a `stderr`; `stdout` continua reservado ao resultado JSON. Ao usar `docker compose exec`, os dois canais aparecem no terminal. Para acompanhar os logs do servidor OCR, cujo processo é o principal do container:

~~~sh
docker compose logs -f ocr-mcp
~~~

Os eventos não incluem nome do arquivo, UUID da imagem, nomes de exames, texto bruto do OCR, imagem ou credenciais.

## Testes e análise estática

As imagens de desenvolvimento incluem pytest, Ruff e Mypy para executar verificações no container. A suíte padrão contém testes unitários e testes do fluxo ADK/MCP com um servidor SSE local e modelo determinístico; ela não chama Gemini nem Cloud Vision reais. O E2E manual descrito abaixo é a exceção: chama Cloud Vision real, mas mantém o modelo Gemini determinístico.

~~~sh
docker compose exec -w /workspace/apps/runtime assistant-runtime pytest -q
docker compose exec -w /workspace/apps/runtime assistant-runtime ruff check .
docker compose exec -w /workspace/apps/runtime assistant-runtime ruff format --check .
docker compose exec -w /workspace/apps/runtime assistant-runtime mypy
~~~

Os testes unitários e de transporte do OCR também rodam dentro do container:

~~~sh
docker compose exec -w /workspace/apps/ocr_mcp ocr-mcp pytest -q
docker compose exec -w /workspace/apps/ocr_mcp ocr-mcp ruff check .
docker compose exec -w /workspace/apps/ocr_mcp ocr-mcp ruff format --check .
docker compose exec -w /workspace/apps/ocr_mcp ocr-mcp mypy
~~~

Os testes unitários e de transporte do RAG também rodam dentro do container:

~~~sh
docker compose exec -w /workspace/apps/rag_mcp rag-mcp pytest -q
docker compose exec -w /workspace/apps/rag_mcp rag-mcp ruff check .
docker compose exec -w /workspace/apps/rag_mcp rag-mcp ruff format --check .
docker compose exec -w /workspace/apps/rag_mcp rag-mcp mypy
~~~

Os testes e a análise estática da API de agendamento também rodam no container:

~~~sh
docker compose exec -w /workspace/apps/schedule_api schedule-api pytest -q
docker compose exec -w /workspace/apps/schedule_api schedule-api pytest --cov --cov-report=term-missing
docker compose exec -w /workspace/apps/schedule_api schedule-api ruff check .
docker compose exec -w /workspace/apps/schedule_api schedule-api ruff format --check .
docker compose exec -w /workspace/apps/schedule_api schedule-api mypy
~~~

Quando `schedule-api` estiver em execução, seu Swagger está disponível somente
no host local em <http://localhost:8001/docs>. Consulte o README do app para
emitir o JWT local de demonstração e testar o `POST /appointments`.

## E2E manual com Cloud Vision real

Este E2E é optativo e fica fora da suíte padrão e do CI. Ele percorre o comando
`process --path`, o armazenamento temporário, o agente ADK, o OCR MCP por SSE e
o Cloud Vision real. O modelo do agente é substituído no teste por um modelo
determinístico, então esta validação não chama Gemini. Cada execução faz uma
requisição real ao Cloud Vision.

Configure `GOOGLE_CLOUD_VISION_API_KEY` no `.env` ignorado pelo Git e inicie os
serviços. Gere também a factory do agente uma vez:

~~~sh
docker compose up -d --build assistant-runtime ocr-mcp rag-mcp
docker compose exec assistant-runtime python -m carrefour_runtime generate specification.json --output generated/agent.py
~~~

Execute cada fixture separadamente. `-s` mostra o JSON retornado e o tempo total
do fluxo; o teste aceita somente esses dois nomes de arquivo:

~~~sh
docker compose exec -w /workspace/apps/runtime \
  -e RUN_LIVE_VISION_E2E=1 \
  -e E2E_IMAGE_NAME=exam_request_pt_br.png \
  -e CARREFOUR_GENERATED_AGENT_PATH=/workspace/generated/agent.py \
  assistant-runtime pytest -s tests/e2e/test_live_vision.py
~~~

~~~sh
docker compose exec -w /workspace/apps/runtime \
  -e RUN_LIVE_VISION_E2E=1 \
  -e E2E_IMAGE_NAME=exam_request_pt_br_simplified.png \
  -e CARREFOUR_GENERATED_AGENT_PATH=/workspace/generated/agent.py \
  assistant-runtime pytest -s tests/e2e/test_live_vision.py
~~~

O primeiro caso deve retornar cinco exames; o formulário deve retornar os seis
exames marcados. O teste compara o resultado esperado, confirma que o prompt
contém apenas o UUID, verifica que o original não mudou e que a cópia temporária
foi removida. O comando normal `python -m carrefour_runtime process --path`
continua usando o modelo da especificação; para esta validação sem Gemini, use
os comandos E2E acima.

## Referências do Google ADK

- [Runner e InMemoryRunner](https://github.com/google/adk-python/blob/main/docs/guides/runners/runner/index.md)
- [Estratégia de testes do ADK](https://github.com/google/adk-python/blob/main/contributing/adk_project_overview_and_architecture.md#testing--evaluation-strategy)
- [Integração de ferramentas MCP](https://github.com/google/adk-python/blob/main/src/google/adk/tools/mcp_tool/mcp_toolset.py)

## Transparência sobre o uso de IA

A IA apoiou a discussão de requisitos, decisões de arquitetura, implementação e documentação. O candidato direcionou as decisões de escopo e revisou as alterações. A geração do agente usa um template local determinístico; um LLM não escreve o arquivo Python gerado.

Os testes do agente usam um modelo determinístico de teste para exercitar o despacho das tools sem credenciais nem chamadas a serviços externos. Não foram feitas chamadas a Gemini real nos testes.

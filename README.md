# Carrefour Challenge

Este projeto transforma uma especificação JSON em um agente Google ADK que processa pedidos de exames e solicita agendamentos. O fluxo integra OCR e RAG via MCP/SSE com uma API FastAPI, e roda em serviços independentes orquestrados pelo Docker Compose.


| Serviço | Quantidade de testes | Coverage |
| --- | ---: | ---: |
| assistant-runtime | 132 | 88,0% |
| ocr-mcp | 112 | 96,2% |
| rag-mcp | 67 | 94,6% |
| schedule-api | 42 | 95,0% |

A cobertura considera o pacote de aplicação de cada serviço; os testes do pacote compartilhado de observabilidade não entram nesses percentuais.

## Documentação

- [PRD da Fase 1](docs/PRD.md): objetivo, escopo e critérios de conclusão.
- [Plano da Fase 1](docs/phase1-plan.md): etapas acordadas e entregas concluídas.
- [Especificação técnica da Fase 1](docs/phase1-spec.md): formato do JSON, validações, tools e geração determinística.
- [System Design — arquitetura dos containers](docs/system-design.md): containers, integrações e fronteiras de confiança.
- [Plano da Fase 2](docs/phase2-plan.md): decisões e checklist das próximas subfases.
- [HOW TO VALIDATE](HOW_TO_VALIDATE.md): testes automatizados e roteiro manual E2E com observabilidade.
- [Workflow de desenvolvimento](docs/playbooks/development-workflow.md): ciclo de mudança, revisão, validação e transparência no uso de IA.
- [Playbook de logging](docs/playbooks/logging.md): eventos estruturados, 5 Ws e política de privacidade.
- [Observabilidade local](docs/observability.md): OpenObserve, Collector, credenciais e comandos de operação.
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
ZAI_API_KEY=sua-chave-da-zai
~~~

`GOOGLE_CLOUD_VISION_API_KEY` é entregue somente ao OCR. O Compose entrega `GOOGLE_API_KEY` e `ZAI_API_KEY` ao runtime; a factory gerada usa a credencial do provedor/modelo declarado em `specification.json`. As chaves não são incluídas no build. O OCR atende em `http://ocr-mcp:8000/sse` e o RAG em `http://rag-mcp:8000/sse` dentro da rede Compose; nenhuma dessas portas é publicada no host.

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

O arquivo gerado é código-fonte. O comando `process` carrega a factory, conecta as implementações aprovadas das três tools e executa o agente pelo `InMemoryRunner` do ADK.

## Processar um pedido de exames

Gere primeiro `generated/agent.py`, mantenha os arquivos de entrada em `tests/fixtures/images/` e passe somente o nome do arquivo e o identificador local do usuário:

~~~sh
docker compose exec assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br_simplified.png --user user-1
~~~

O comando valida o conteúdo PNG/JPG e o limite de 10 MB, cria uma cópia temporária identificada por UUID e executa as tools OCR, catálogo e agendamento na ordem definida. O prompt recebe o UUID, nunca o caminho ou os bytes da imagem. A saída de sucesso apresenta nomes canônicos e horários em uma mensagem humanizada; respostas parciais informam separadamente agendamentos existentes, novos e sem disponibilidade. Resultados que exigem revisão exibem uma mensagem genérica e retornam código 2; erros sanitizados são escritos em `stderr` com código 1. O runtime aceita um processamento por vez e remove a imagem temporária ao concluir.

Os eventos operacionais do runtime e do OCR são logs JSON enviados a `stderr`; `stdout` fica reservado à mensagem funcional humanizada. Ao usar `docker compose exec`, os dois canais aparecem no terminal. Para acompanhar os logs do servidor OCR, cujo processo é o principal do container:

~~~sh
docker compose logs -f ocr-mcp
~~~

Os eventos não incluem nome do arquivo, UUID da imagem, nomes de exames, texto bruto do OCR, imagem ou credenciais.

## Testes e análise estática

As imagens de desenvolvimento incluem pytest, Ruff e Mypy para executar verificações no container. A suíte padrão contém testes unitários e testes do fluxo ADK/MCP/API com serviços locais e modelo determinístico; ela não chama provedores externos. A validação manual descrita abaixo percorre o comando normal com as credenciais configuradas e chama Vision e o modelo declarados na especificação.

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

## E2E manual do fluxo completo

Esta validação simula o uso pelo avaliador: sobe os containers independentes,
valida e gera o agente a partir da especificação e executa o comando normal
`process`. O runtime usa o provedor/modelo declarados em `specification.json`,
Cloud Vision faz o OCR, o RAG resolve os exames e a Schedule API persiste as
reservas. Não é um teste pytest nem substitui as suítes locais.

Configure `GOOGLE_CLOUD_VISION_API_KEY` e a chave do provedor/modelo da
especificação (`ZAI_API_KEY` no exemplo atual) no `.env` ignorado pelo Git. O
Compose local também fornece um segredo JWT de demonstração se
`CARREFOUR_SCHEDULE_JWT_SECRET` não estiver definido. Em seguida, construa e
inicie todos os serviços e gere o agente:

~~~sh
docker compose up -d --build assistant-runtime ocr-mcp rag-mcp schedule-api
docker compose exec assistant-runtime python -m carrefour_runtime validate specification.json
docker compose exec assistant-runtime python -m carrefour_runtime generate specification.json --output generated/agent.py
~~~

Processe uma fixture por vez; `--user` é obrigatório e identifica o paciente
localmente na API de agendamento:

~~~sh
docker compose exec assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br.png --user user-1
docker compose exec assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br_simplified.png --user user-1
~~~

As mensagens indicam os exames agendados ou já existentes, seus horários,
indisponibilidades parciais, ausência de exames ou necessidade de revisão. Não
exibem códigos de catálogo, IDs de agendamento ou conteúdo incerto do OCR. A
execução real faz chamadas externas ao Cloud Vision e ao modelo configurado; ela
não pertence à suíte padrão. O runtime remove a cópia temporária da imagem ao
encerrar cada processamento; o SQLite mantém as reservas para que uma nova
execução do mesmo usuário demonstre a reconciliação incremental.

## Referências do Google ADK

- [Runner e InMemoryRunner](https://github.com/google/adk-python/blob/main/docs/guides/runners/runner/index.md)
- [Estratégia de testes do ADK](https://github.com/google/adk-python/blob/main/contributing/adk_project_overview_and_architecture.md#testing--evaluation-strategy)
- [Integração de ferramentas MCP](https://github.com/google/adk-python/blob/main/src/google/adk/tools/mcp_tool/mcp_toolset.py)

## Transparência sobre o uso de IA

A IA apoiou a discussão de requisitos, decisões de arquitetura, implementação e documentação. O candidato direcionou as decisões de escopo e revisou as alterações. A geração do agente usa um template local determinístico; um LLM não escreve o arquivo Python gerado.

Os testes do agente usam um modelo determinístico de teste para exercitar o despacho das tools sem credenciais nem chamadas a serviços externos. Não foram feitas chamadas a Gemini real nos testes.

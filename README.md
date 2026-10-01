# Carrefour Challenge

**Estado:** Fase 1 concluída; Fase 2.0 em andamento.

O projeto constrói um agente exam scheduler a partir de uma especificação declarativa. A Fase 1 valida o JSON e gera uma factory Python para o Google ADK. A Fase 2 prepara os serviços e integrações do fluxo de atendimento.

## Fluxo da Fase 1

~~~text
specification.json -> validação Pydantic -> geração determinística de uma factory Python
~~~

A especificação escolhe tools por IDs registrados no projeto. Ela não aceita código, instruções livres, credenciais ou endereços de servidores MCP. A factory gerada recebe implementações aprovadas pelo runtime e valida que o conjunto de IDs corresponde exatamente ao declarado antes de criar o agente.

A geração produz código-fonte; não executa a factory nem inicia o agente. O código gerado define `create_agent(registered_tools)`, que instancia um `Agent` do Google ADK quando for chamado.

## Estado da Fase 2

O componente `TemporaryImageStore`, em `apps/runtime/src/carrefour_runtime/image_storage.py`, valida o conteúdo real da imagem, aceita `PNG` e `JPG` até 10 MB, grava os bytes sob um `UUID` com promoção atômica e remove imagens órfãs com mais de 30 minutos.

O Docker Compose inicia um runtime não root com um volume `tmpfs` de 64 MiB para esse armazenamento. Por enquanto, a entrada de imagens do host ainda não está ligada ao runtime. Não existe um comando público para enviar uma imagem, e o OCR MCP, o catálogo e a API de agendamento ainda não foram implementados.

## Documentação

- [PRD da Fase 1](docs/PRD.md): objetivo, escopo e critérios de conclusão.
- [Plano da Fase 1](docs/phase1-plan.md): etapas acordadas e entregas concluídas.
- [Especificação técnica da Fase 1](docs/phase1-spec.md): formato do JSON, validações, tools e geração determinística.
- [System design da Fase 1](docs/system-design.md): componentes, fluxo e fronteiras de confiança.
- [Plano da Fase 2](docs/phase2-plan.md): decisões e checklist das próximas subfases.
- [App runtime](apps/runtime/README.md): responsabilidades e limite do projeto Python executável.
- [Handoff da Fase 1](docs/HANDOFF_FASE_1.md): decisões e contexto para continuidade.
- [Exemplo de especificação](specification.json).

## Requisitos no host

- Docker Engine com Docker Compose
- Git para obter o repositório

Python, uv e as dependências do projeto são instalados dentro da imagem. Não é necessário instalar esses componentes no host.

## Construir e iniciar o container

~~~sh
docker compose up -d --build assistant-runtime
~~~

O runtime é construído independentemente a partir de `apps/runtime/`, usando o `pyproject.toml` e o `uv.lock` daquele app. O repositório é montado em `/workspace` para que a aplicação acesse o `specification.json`, as imagens de demonstração e deixe a saída gerada visível no host. O container executa como usuário não root. Se o GID do grupo do host não for 1000, configure `CARREFOUR_RUNTIME_GID` no arquivo `.env` do projeto.

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

## Testes e análise estática

A imagem inclui pytest, Ruff e Mypy para executar verificações no container. A suíte contém testes unitários da especificação, geração e armazenamento, além de um teste de execução controlada do agente com o `InMemoryRunner`. Nenhum teste inicia uma chamada a um modelo Gemini real.

~~~sh
docker compose exec -w /app assistant-runtime pytest -q
docker compose exec -w /app assistant-runtime ruff check .
docker compose exec -w /app assistant-runtime ruff format --check .
docker compose exec -w /app assistant-runtime mypy
~~~

## Referências do Google ADK

- [Runner e InMemoryRunner](https://github.com/google/adk-python/blob/main/docs/guides/runners/runner/index.md)
- [Estratégia de testes do ADK](https://github.com/google/adk-python/blob/main/contributing/adk_project_overview_and_architecture.md#testing--evaluation-strategy)
- [Integração de ferramentas MCP](https://github.com/google/adk-python/blob/main/src/google/adk/tools/mcp_tool/mcp_toolset.py)

## Transparência sobre o uso de IA

A IA apoiou a discussão de requisitos, decisões de arquitetura, implementação e documentação. O candidato direcionou as decisões de escopo e revisou as alterações. A geração do agente usa um template local determinístico; um LLM não escreve o arquivo Python gerado.

Os testes do agente usam um modelo determinístico de teste para exercitar o despacho das tools sem credenciais nem chamadas a serviços externos. Não foram feitas chamadas a Gemini real nos testes.

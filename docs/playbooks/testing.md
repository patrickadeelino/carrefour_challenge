# Playbook de testes

Este guia mantém claro o limite entre testes rápidos, testes de integração local
e validação que chama um serviço externo. A suíte padrão deve exercitar
comportamentos e caminhos de falha sem credenciais nem custo de API.

## Organização

- **Unitários:** ficam em `tests/unit/`, espelhando os módulos de
  `src/`. Cobrem regras, validações, resultados e falhas com dependências
  simuladas.
- **Integração:** ficam em `tests/integration/`. Exercitam fronteiras reais
  entre componentes locais, como ADK e MCP por SSE, usando servidor e modelo
  determinísticos. Não chamam Gemini nem Cloud Vision.
- **E2E manual:** fica em `apps/runtime/tests/e2e/`. O teste de Vision percorre
  o fluxo completo com Cloud Vision real e modelo determinístico; fica fora da
  suíte padrão e pode consumir cota/custo da API.

Mantenha cada teste perto da responsabilidade correspondente e nomeie o cenário
para indicar o comportamento observado. Prefira cobrir sucesso, validação,
falha e privacidade a adicionar casos que só elevem a porcentagem de cobertura.
Use fixtures compartilhadas quando eliminarem repetição sem esconder os dados
específicos do cenário.

## Executar as suítes nos containers

Na raiz do repositório, construa e inicie os apps:

```sh
docker compose up -d --build assistant-runtime ocr-mcp
```

Runtime e OCR têm dependências, configurações e imagens próprias. Os comandos
abaixo rodam dentro dos containers; pytest coleta os testes unitários, de
integração e os testes da biblioteca compartilhada de logging.

```sh
docker compose exec -w /workspace/apps/runtime assistant-runtime pytest -q
docker compose exec -w /workspace/apps/runtime assistant-runtime ruff check .
docker compose exec -w /workspace/apps/runtime assistant-runtime ruff format --check .
docker compose exec -w /workspace/apps/runtime assistant-runtime mypy
```

```sh
docker compose exec -w /workspace/apps/ocr_mcp ocr-mcp pytest -q
docker compose exec -w /workspace/apps/ocr_mcp ocr-mcp ruff check .
docker compose exec -w /workspace/apps/ocr_mcp ocr-mcp ruff format --check .
docker compose exec -w /workspace/apps/ocr_mcp ocr-mcp mypy
```

O E2E com Vision é optativo e manual. Siga os comandos e configure a chave
`GOOGLE_CLOUD_VISION_API_KEY` conforme a seção “E2E manual com Cloud Vision
real” do [README principal](../../README.md). Não execute esse teste como parte da
suíte padrão ou CI.

## Referências

- [Google ADK — Runner e InMemoryRunner](https://github.com/google/adk-python/blob/main/docs/guides/runners/runner/index.md)
- [Google ADK — estratégia de testes](https://github.com/google/adk-python/blob/main/contributing/adk_project_overview_and_architecture.md#testing--evaluation-strategy)
- [MCP Python SDK — testes com servidor em memória](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/get-started/testing.md)

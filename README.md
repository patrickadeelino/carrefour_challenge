# Carrefour Challenge

**Status:** fase 1 concluída no escopo definido no PRD. O teste de integração executa o agente gerado pelo `InMemoryRunner` e comprova o despacho das três tools com um modelo determinístico de teste. Chamadas a um modelo real ficam para uma etapa posterior.

Este repositório será construído por etapas. A fase 1 define uma especificação JSON para um agente do tipo exam scheduler, valida essa especificação e gera uma factory Python que instancia um agente usando Google ADK.

## Fluxo da fase 1

~~~text
specification.json -> validação Pydantic -> factory Python gerada com Google ADK
~~~

O JSON seleciona ferramentas por identificadores lógicos registrados pelo projeto. O transpilador rejeita ferramentas desconhecidas ou incompatíveis com o tipo de agente. Endereços de servidores, credenciais e instruções fixas do agente ficam fora do JSON.

A saída gerada expõe `create_agent(registered_tools)`. A factory recebe o mapa de implementações aprovadas do consumidor confiável, exige exatamente os IDs declarados e informa IDs ausentes ou extras antes de instanciar o agente ADK. O contrato da factory já está implementado; o serviço de runtime que fornecerá as tools em produção ainda fica para uma etapa posterior. A mesma especificação gera os mesmos bytes de Python. Fingerprint e cache de artefatos foram adiados.

## Documentos

- [PRD do projeto (escopo atual: fase 1)](docs/PRD.md): objetivo, escopo e critérios de conclusão.
- [Plano de implementação da fase 1](docs/phase1-plan.md): sequência acordada e entregas concluídas.
- [Especificação técnica da fase 1](docs/phase1-spec.md): formato inicial do JSON, validações, ferramentas e geração determinística.
- [System design da fase 1](docs/system-design.md): componentes, fluxo de produção e fronteiras de confiança desta etapa.
- [Exemplo de especificação](specification.json): configuração de exemplo ainda sujeita à validação pelo transpilador.

## Limite desta etapa

Esta fase trata da especificação, sua validação e da geração da factory Python do agente. O OCR, a busca de exames via MCP/SSE, a API FastAPI de agendamento, o fluxo com a imagem e a conteinerização serão detalhados em etapas posteriores. Os servidores MCP de OCR e catálogo são requisitos do desafio; o que esta fase proíbe é aceitar endpoints MCP arbitrários diretamente do JSON.

## Transparência sobre o uso de IA

A IA apoiou o refinamento dos requisitos, a discussão das decisões de arquitetura, a implementação e a documentação. As decisões de escopo — como aceitar somente IDs de tools registrados, limitar os modelos por allowlist e usar um modelo simulado para testar o despacho de tools sem chamadas externas — foram avaliadas e direcionadas pelo candidato. O código sugerido foi revisado e validado com testes, Ruff e Mypy. O gerador usa um template determinístico local e não usa um LLM para escrever o arquivo Python produzido.

Na verificação final desta fase, os 21 testes passaram; Ruff, formatação e Mypy também passaram. O teste de integração do `Runner` confirmou a execução das três tools com respostas determinísticas de um modelo de teste. O pytest exibiu avisos de depreciação do OpenTelemetry e de uso experimental de function declarations no ADK, sem falha nos testes. Não chamamos o Gemini nem validamos a qualidade das decisões do modelo.

## Referências iniciais

- [Google ADK: estrutura de projeto e definição do agente](https://google.github.io/agents-cli/guide/project-structure/)
- [Google ADK: Runner e InMemoryRunner](https://github.com/google/adk-python/blob/main/docs/guides/runners/runner/index.md)
- [Google ADK: estratégia de testes unitários, de integração e avaliação](https://github.com/google/adk-python/blob/main/contributing/adk_project_overview_and_architecture.md#testing--evaluation-strategy)
- [Google ADK: modelos e integração LiteLLM](https://github.com/google/adk-python/blob/main/src/google/adk/models/lite_llm.py)
- [Google ADK: integração MCP](https://github.com/google/adk-python/blob/main/src/google/adk/tools/mcp_tool/mcp_toolset.py)

## Executar os testes da fase 1

Requer Python 3.11 ou superior e `uv`. Sincronize o ambiente com as dependências de desenvolvimento:

~~~sh
uv sync --group dev
~~~

Execute os testes:

~~~sh
uv run pytest -q
~~~

Executar as verificações estáticas de estilo, complexidade e tipagem:

~~~sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
~~~

Validar o exemplo:

~~~sh
uv run python -m carrefour_transpiler validate specification.json
~~~

Gerar a factory Python:

~~~sh
uv run python -m carrefour_transpiler generate specification.json --output generated/agent.py
~~~

# AI Handoff - Carrefour Challenge: fase 1

- Tags: #side-project #carrefour-challenge #handoff
- Scope: carrefour-challenge
- Date: 2026-09-30

## Current Focus

- Fase 1 foi concluída no escopo do PRD: CLI valida `specification.json` e gera uma factory Python determinística para Google ADK.
- Repositório: `/home/patrick/Patrick/carrefour_challenge`, branch `main`. Último commit: `894c1b1` (`docs: document phase 1 scope and design`).
- `docs/TODO.md` e `generated/agent.py` permanecem locais e fora do Git. Este handoff foi versionado; o arquivo gerado foi preservado e não foi incluído nos commits.

## Decisions

- A especificação aceita o tipo `exam_scheduler`, modelo Gemini explícito na allowlist e somente IDs de tools registrados. Instruções são fixas no código; JSON não recebe código, endpoints, credenciais ou instruções livres.
- Pydantic valida a estrutura e as tools declaradas antes da geração. JSON inválido interrompe o CLI sem gerar `agent.py`.
- O gerador usa template determinístico. `agent.py` define `create_agent(registered_tools)`; a geração não executa a factory.
- Quando chamada, a factory compara exatamente as chaves de `registered_tools` com os IDs declarados. IDs ausentes ou extras geram `ValueError` antes de instanciar o Agent.
- Os testes instanciam um `Agent` real do ADK e exercitam o despacho das tools via `InMemoryRunner` com modelo determinístico de teste. Não há chamada a Gemini real ou serviço externo.

## Risks

- Integrações reais com Gemini, MCP/SSE e API de agendamento continuam fora da fase 1.
- Os avisos de depreciação observados no ADK/OpenTelemetry foram mantidos por decisão explícita; avaliar depois, sem confundir com falhas dos testes.
- A documentação registra que 21 testes, Ruff, formatação e Mypy passaram na validação anterior. Eles não foram executados novamente durante a criação dos commits.

## Artifacts

- Commits: `60c30ae` (validação e geração), `1fe5c31` (execução de tools com `InMemoryRunner`), `894c1b1` (documentação da fase 1).
- Documentos: `README.md`, `docs/PRD.md`, `docs/phase1-spec.md`, `docs/system-design.md`.
- Código e testes de runtime agora ficam em `apps/runtime/`; os caminhos originais da Fase 1 foram reorganizados no commit de refatoração.
- Manutenção local: `docs/TODO.md`.

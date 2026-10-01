# Plano de implementação — Fase 1

**Estado:** concluída.

## Objetivo

Criar um transpilador que valide uma especificação JSON restrita para o agente `exam_scheduler` e gere uma factory Python determinística compatível com Google ADK.

## Decisões de escopo

- Suportar somente o tipo `exam_scheduler` nesta fase.
- Manter provider/model em allowlist explícita e tools identificadas por IDs registrados.
- Manter as instruções do agente no código do projeto; não aceitar código, instruções livres, endpoints ou credenciais no JSON.
- Validar a especificação antes de gerar qualquer artefato.
- Fazer a factory receber as implementações aprovadas pelo runtime e exigir correspondência exata entre IDs declarados e recebidos.
- Gerar Python determinístico com template local, sem usar um LLM para escrever o código.
- Testar construção e despacho de tools sem chamadas a Gemini ou serviços externos.

## Entregas planejadas

### 1. Preparar o projeto e os testes

- [x] Configurar Python 3.11 ou superior e dependências com `uv`.
- [x] Criar testes para o contrato do JSON, validação do CLI e geração antes da implementação.
- [x] Configurar pytest, Ruff e Mypy.

### 2. Validar a especificação pelo CLI

- [x] Definir modelos estritos para nome, tipo, modelo e IDs de tools.
- [x] Rejeitar campos desconhecidos, valores fora da allowlist, IDs desconhecidos ou repetidos e tools obrigatórias ausentes.
- [x] Expor `validate` com mensagens de erro acionáveis; entrada inválida não deve gerar código.

### 3. Gerar o agente de forma determinística

- [x] Implementar geração Python baseada em template local.
- [x] Expor `generate` e produzir uma factory `create_agent(registered_tools)`.
- [x] Validar IDs ausentes e extras antes de instanciar o agente ADK.
- [x] Verificar sintaxe e determinismo da saída para especificações equivalentes.

### 4. Verificar integração com Google ADK

- [x] Carregar o Python gerado e instanciar um `Agent` real sem chamar um modelo externo.
- [x] Usar `InMemoryRunner` e modelo determinístico de teste para verificar despacho das tools.

### 5. Revisar e documentar

- [x] Executar testes, formatação, Ruff e Mypy.
- [x] Documentar escopo, componentes, fluxo, fronteiras de confiança e referências consultadas.
- [x] Registrar no README o uso consciente de IA, as referências e a estratégia de orquestração/testes.

## Fora do escopo

- Execução com Gemini real ou chamadas a outros modelos externos.
- Implementação do MCP de OCR, catálogo/RAG ou API de agendamento.
- Recepção, armazenamento ou processamento de imagens.
- Anonimização de PII, fluxo completo de atendimento, fingerprint ou cache.

## Evidências e sequência de commits

A validação registrada para a Fase 1 concluiu 21 testes, Ruff, formatação e Mypy. O teste ADK instancia um `Agent` real e usa `InMemoryRunner` com modelo determinístico para exercitar as tools, sem chamadas a Gemini ou serviços externos.

O histórico da Fase 1 segue esta sequência:

1. `docs: define phase 1 implementation plan` — plano inicial com as tarefas em aberto.
2. `feat: validate specs and generate ADK agents` — configuração, testes de validação e geração; checkboxes correspondentes atualizados.
3. `test: verify ADK tool dispatch with InMemoryRunner` — teste de execução controlada; checkboxes de execução atualizados.
4. `docs: document phase 1 scope and design` — documentação final e conclusão dos checkboxes.

Os documentos de apoio são [`PRD.md`](PRD.md), [`phase1-spec.md`](phase1-spec.md) e [`system-design.md`](system-design.md). Após a refatoração, o código da Fase 1 está em `apps/runtime/src/carrefour_runtime/`, e seus testes estão em `apps/runtime/tests/`.

# HOW TO VALIDATE

Roteiro reproduzível para validar o fluxo completo como avaliador: build dos
containers, testes automatizados, geração do agente, processamento das imagens
de referência e inspeção de logs e traces.

> Cada execução de `process` chama o Google Cloud Vision e o modelo Z.ai
> configurado em `specification.json`; isso pode gerar consumo faturável. Os
> testes automatizados abaixo não chamam esses serviços.

## 1. Preparar o ambiente

Requisitos no host: Docker Engine e Docker Compose. Preencha o `.env` local com
`GOOGLE_CLOUD_VISION_API_KEY` e `ZAI_API_KEY`. Configure também
`.env.observability` (pode copiar o .env.observability.example) para a conta local do OpenObserve.

As portas locais `5080` e `8001` devem estar livres. Em um checkout limpo, use
um projeto Compose isolado; na primeira execução, ele cria volumes próprios
para o banco de agendamentos e a observabilidade:

```sh
docker compose -p carrefour-validator-e2e build
docker compose -p carrefour-validator-e2e up -d
docker compose -p carrefour-validator-e2e ps
```

Confirme que `assistant-runtime`, `ocr-mcp`, `rag-mcp`, `schedule-api`,
`otel-collector` e `openobserve` estão em execução. Para verificar se as chaves
foram entregues aos containers sem exibir seus valores:

```sh
docker compose -p carrefour-validator-e2e exec assistant-runtime python -c 'import os; print("ZAI_API_KEY configurada:", bool(os.getenv("ZAI_API_KEY")))'
```
```sh
docker compose -p carrefour-validator-e2e exec ocr-mcp python -c 'import os; print("Vision API key configurada:", bool(os.getenv("GOOGLE_CLOUD_VISION_API_KEY")))'
```
Os volumes persistem entre execuções; removê-los reinicia a agenda e apaga a telemetria anterior.

## 2. Rodar os testes automatizados

As imagens `dev` incluem as ferramentas de teste. Execute as suítes por app:

Nos comandos do `assistant-runtime`, a opção `-e` aplica um filtro do Python
para ocultar os `UserWarning` experimentais emitidos pelo ADK e manter a saída
mais limpa durante esta validação. Ela não oculta os logs estruturados do
runtime nem substitui a revisão de avisos em desenvolvimento.

```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' -w /workspace/apps/runtime assistant-runtime pytest -q
```
```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' -w /workspace/apps/ocr_mcp ocr-mcp pytest -q
```
```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' -w /workspace/apps/rag_mcp rag-mcp pytest -q
```
```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' -w /workspace/apps/schedule_api schedule-api pytest -q
```

Essas suítes usam dependências locais ou simuladas e não chamam Vision, Z.ai ou
outros serviços externos. Os comandos de Ruff e Mypy estão no
[README principal](README.md#testes-e-análise-estática).

## 3. Validar e gerar o agente

Valide a especificação e gere o artefato dentro do container runtime:

```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' assistant-runtime python -m carrefour_runtime generate specification.json --output generated/agent.py
```

O `process` seguinte carrega esse agente, chama OCR, RAG e Schedule API. Use o
mesmo `user` nas imagens relacionadas para observar a reconciliação dos exames
já agendados; use outro usuário para conferir o isolamento do histórico. Os
horários são globais e exclusivos entre usuários.

## 4. Processar as imagens

Rode os comandos na ordem abaixo. Cada chamada cria uma cópia temporária da
imagem, executa o fluxo e remove a cópia ao terminar. Os arquivos originais em
`tests/fixtures/images/` permanecem intactos. O `-e` injeta no container o filtro
de `UserWarning` explicado acima; os logs e a mensagem do processamento seguem
visíveis.

### Primeira imagem para `user-1`

```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br.png --user user-1
```

Na execução observada, os cinco exames foram agendados às 09:00.

### Segunda imagem para `user-1`

```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br_simplified.png --user user-1
```

Hemograma, glicemia de jejum, hemoglobina glicada e TSH devem aparecer como já
agendados. LDL e vitamina D são novos e recebem o próximo horário global livre.
Na execução observada, esse horário foi 09:30.

### Repetir a primeira imagem para `user-1`

```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br.png --user user-1
```

Os cinco exames devem aparecer como já agendados; a repetição não cria novas
reservas.

### Primeira imagem para `user-2`

```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br.png --user user-2
```

Os cinco exames são novos para `user-2`. A agenda compartilhada escolhe outro
horário globalmente livre. Na execução observada, foi 10:00 no mesmo dia.

### Segunda imagem para `user-2`

```sh
docker compose -p carrefour-validator-e2e exec -e 'PYTHONWARNINGS=ignore:[EXPERIMENTAL] feature FeatureName.:UserWarning' assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br_simplified.png --user user-2
```

Os quatro exames em comum devem aparecer como já agendados; LDL e vitamina D
devem ser reservados em outro horário. Na execução observada, foi 10:30.

As datas e os horários dependem do calendário de disponibilidade no momento da
execução. Esta sequência observou 06/10/2026, com horários de 09:00 a 10:30.
O segundo usuário recebeu outro horário, mas não outra data porque ainda havia
slots livres naquele dia. A progressão para dias úteis seguintes está coberta
nos testes da política de disponibilidade e da seleção do próximo slot livre:
[test_availability.py](apps/schedule_api/tests/unit/carrefour_schedule_api/test_availability.py)
e [test_schedule_appointments.py](apps/schedule_api/tests/unit/carrefour_schedule_api/application/test_schedule_appointments.py).

## 5. Conferir logs e traces

Abra <http://localhost:5080> e entre com as credenciais locais definidas em
`.env.observability`. No OpenObserve:

1. Selecione `carrefour_traces` e procure pelo `trace_id` emitido pelo comando
   correspondente.
2. Abra o trace para inspecionar a execução entre runtime, OCR, RAG e Schedule
   API.
3. Selecione `carrefour_logs` e filtre pelo mesmo `trace_id` para correlacionar
   os eventos operacionais.

O runtime também imprime logs JSON em `stderr`; a mensagem funcional é escrita
em `stdout`. O ADK pode emitir avisos `[EXPERIMENTAL]` no terminal; eles não
indicam falha do processamento. Logs e traces não devem conter imagens, texto
bruto do OCR, credenciais ou dados pessoais.

## Limpar o ambiente de validação

Para parar os containers mantendo os dados da execução:

```sh
docker compose -p carrefour-validator-e2e down
```

Para apagar também o banco e a telemetria desse projeto de validação:

```sh
docker compose -p carrefour-validator-e2e down -v
```

`down -v` remove as reservas e logs/traces salvos nos volumes desse projeto.
Use-o somente depois de terminar a inspeção. Para outra execução limpa sem
apagar esses dados, escolha um nome novo com `-p` e use-o em todos os comandos.

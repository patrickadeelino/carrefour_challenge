# Schedule API

API fictícia que reconcilia exames já agendados para um usuário autenticado e
aloca um horário globalmente livre para exames novos. É um serviço independente;
nesta etapa, o runtime ainda não o chama.

## Contrato HTTP

### `POST /appointments`

Requer `Authorization: Bearer <JWT>` assinado com HS256. A identidade vem de
`sub`; o corpo não aceita `user_id`.

```json
{
  "exam_codes": ["CAT-001", "CAT-002"]
}
```

Exames repetidos são deduplicados preservando a ordem. A API mantém os horários
dos exames já agendados para aquele usuário e aloca somente os códigos novos.
Um horário é globalmente exclusivo, mesmo entre usuários diferentes.

Resposta de negócio bem-sucedida (`200`):

```json
{
  "status": "completed",
  "already_scheduled": [],
  "newly_scheduled": [
    {
      "appointment_id": "00000000-0000-0000-0000-000000000001",
      "scheduled_at": "2026-10-05T09:00:00-03:00",
      "exam_codes": ["CAT-001", "CAT-002"]
    }
  ],
  "not_scheduled": []
}
```

`status` pode ser `completed`, `partial` ou `no_availability`. A falta de
horários é resultado de negócio HTTP `200`; erro de autenticação usa `401`,
entrada inválida `422`, indisponibilidade do banco `503` e falha inesperada
sanitizada `500`. Respostas de erro seguem `{"detail":{"code":"..."}}`.

O Swagger UI fica em <http://localhost:8001/docs>; OpenAPI JSON em
<http://localhost:8001/openapi.json>. A porta é publicada somente em
`127.0.0.1` pelo Compose local. A agenda demonstrativa usa dias
úteis, 09:00–17:00, slots de 30 minutos e fuso `America/Sao_Paulo`; horários e
janela podem ser configurados por ambiente.

## Injeção de dependências e banco

O `Engine` e o `sessionmaker` são criados uma vez no lifespan da aplicação; o
engine é descartado no shutdown. `get_session` fornece uma `Session` curta por
request e a fecha em `finally` antes de enviar a resposta. Outra dependência
monta o serviço de aplicação com esse repositório. A política imutável de
disponibilidade é validada uma vez pela factory e reutilizada entre requests.
Nenhuma `Session` é compartilhada entre requests.

`appointments` guarda cada reserva e `appointment_exams` guarda os códigos
associados em linhas próprias, com chave estrangeira. A restrição `UNIQUE` no
horário impede reservas duplicadas. Cada alocação usa uma transação SQLite
`BEGIN IMMEDIATE`: a leitura dos horários ocupados, escolha do próximo slot e
gravação ficam serializadas e são confirmadas ou revertidas como uma unidade.
O volume `schedule-database` persiste os dados entre reinícios do container.
O primeiro schema é criado a partir do metadata SQLAlchemy no startup; quando a
estrutura persistida precisar evoluir, a etapa deve introduzir migrações
versionadas antes de alterar tabelas existentes.

## Autenticação local

O projeto não contém um provedor de identidade. Para testar a API localmente, o
Compose de desenvolvimento habilita o emissor `carrefour-schedule-token`, que
gera um JWT HS256 com `sub` e expiração de 30 minutos:

```sh
docker compose up -d --build schedule-api
docker compose exec schedule-api carrefour-schedule-token --user user-1
```

Copie o token para o botão **Authorize** no Swagger UI. O emissor não cria uma
rota HTTP e fica desabilitado por padrão no código. O overlay de produção também
o desabilita e exige `CARREFOUR_SCHEDULE_JWT_SECRET`; o segredo não deve ser
incluído na imagem nem versionado. O valor local de desenvolvimento no Compose
não é apropriado para deploy.

## Configuração

- `CARREFOUR_SCHEDULE_DATABASE_PATH`: caminho SQLite; padrão no container
  `/var/lib/carrefour/schedule/appointments.sqlite3`.
- `CARREFOUR_SCHEDULE_JWT_SECRET`: segredo de assinatura HS256 com pelo menos
  32 bytes.
- `CARREFOUR_SCHEDULE_TIMEZONE`: zona IANA, padrão `America/Sao_Paulo`.
- `CARREFOUR_SCHEDULE_OPENING_TIME` e `CARREFOUR_SCHEDULE_CLOSING_TIME`:
  `HH:MM`, padrões `09:00` e `17:00`.
- `CARREFOUR_SCHEDULE_SLOT_DURATION_MINUTES`: duração positiva em minutos,
  padrão `30`.
- `CARREFOUR_SCHEDULE_HORIZON_DAYS`: dias adiante incluídos, padrão `30`.
- `CARREFOUR_SCHEDULE_ENABLE_DEMO_TOKEN_ISSUER`: habilita a ferramenta local
  de emissão de token; padrão `false`.

Configuração inválida falha no startup com mensagem segura; o segredo nunca é
registrado.

## Logs

O app usa o formatador JSON compartilhado; os logs operacionais vão para
`stderr` e os access logs HTTP do Uvicorn ficam desativados. Os eventos incluem
`schedule.configuration.failed`, `schedule.database.ready`,
`schedule.database.failed` e `schedule.database.stopped`. Cada chamada
processada termina em
`schedule.appointments.completed`, `schedule.appointments.rejected`,
`schedule.appointments.failed` ou `schedule.request.failed`.

Os campos seguem o padrão do repositório: timestamp, service, event, component,
resultado (`outcome`) e duração (`duration_ms`); erros incluem `error_code` e
`error_type` estáveis. Não registramos `sub`, JWT, códigos ou nomes de exames,
corpo da requisição, SQL, mensagem bruta de exceção nem valores de configuração.

Cada requisição recebe um `request_id` aleatório gerado pela API, devolvido no
cabeçalho `X-Request-ID` e incluído nos eventos emitidos durante aquela
requisição. O identificador permite agrupar o início HTTP, a reconciliação, a
alocação e o resultado final. Um `X-Request-ID` enviado pelo cliente não é
reutilizado. Os eventos `schedule.reconciliation.completed` e
`schedule.allocation.completed` mostram as etapas de negócio concluídas sem
incluir os dados dos exames.

## Desenvolvimento e validação

O Compose principal constrói a imagem `dev`:

```sh
docker compose up -d --build schedule-api
docker compose exec -w /workspace/apps/schedule_api schedule-api pytest -q
docker compose exec -w /workspace/apps/schedule_api schedule-api pytest --cov --cov-report=term-missing
docker compose exec -w /workspace/apps/schedule_api schedule-api ruff check .
docker compose exec -w /workspace/apps/schedule_api schedule-api ruff format --check .
docker compose exec -w /workspace/apps/schedule_api schedule-api mypy
```

Os testes usam SQLite temporário e tokens sintéticos; não chamam OCR, RAG,
Gemini nem qualquer serviço externo. A suíte cobre o contrato HTTP, persistência,
reconciliação, ausência de disponibilidade, rollback, alocação concorrente,
injeção de dependência, contrato OpenAPI e privacidade dos logs.

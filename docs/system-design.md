# System Design

## Objetivo e escopo

Este documento apresenta a arquitetura atual em alto nível: containers, integrações, armazenamento compartilhado e fronteiras de confiança. O diagrama representa componentes e suas conexões; não descreve a sequência de execução dos comandos.

Os contratos e passos detalhados ficam nas especificações da [Fase 1](phase1-spec.md), da [Fase 2](phase2-spec.md) e no [plano da Fase 2](phase2-plan.md). O comando `process` orquestra o agente com os serviços independentes de OCR, RAG e agendamento.

## Requisitos

### Funcionais

- Validar `specification.json` e gerar deterministicamente a factory Python do agente.
- Receber uma imagem pelo comando `process`, acionar a extração OCR e apresentar exames ou uma resposta explícita que solicite revisão manual.
- Reconhecer os dois layouts de referência usando Cloud Vision e classificação local, sem depender de um LLM para selecionar exames.
- Resolver nomes de exames no catálogo versionado e retornar código somente em correspondências exatas e únicas; expor a busca por MCP SSE.
- Receber códigos de exames autenticados por JWT, preservar reservas já existentes e alocar exames novos em slots globais exclusivos; retornar o diff da reconciliação.

### Não funcionais

- Reduzir a exposição de dados pessoais: imagem e texto OCR integral não entram no contexto do modelo; uma barreira local analisa os valores de saída do OCR e suprime todo o resultado quando identifica PII configurada; logs não expõem conteúdo clínico ou identificadores.
- Isolar responsabilidades em containers independentes, conectados pela rede interna do Compose; montar o armazenamento temporário com escrita no runtime e somente leitura no OCR.
- Remover a cópia temporária ao fim do processamento, permitir um processamento por vez e injetar credenciais somente em runtime.
- Manter a interface do CLI previsível: mensagens funcionais humanizadas em `stdout` e logs/falhas técnicas sanitizadas em `stderr`.
- Persistir reservas em SQLite e serializar a alocação em transações; fornecer uma sessão SQLAlchemy curta por request e fechar o engine no shutdown.
- Manter a API de agendamento como serviço independente e acessível localmente para Swagger.
- Correlacionar logs e spans entre containers por trace context, exportando via OTLP sem registrar imagem, conteúdo clínico ou credenciais; falha de telemetria não deve interromper `process`.

Os critérios detalhados de validação, erros, formatos e respostas estão nas especificações das fases correspondentes.

## Containers e integrações

```mermaid
flowchart LR
    subgraph Compose["Docker Compose · rede interna"]
        direction TB

        subgraph Applications["Serviços da aplicação"]
            direction LR
            Runtime["assistant-runtime<br/>CLI · Google ADK"]
            OCR["ocr-mcp<br/>MCP · extração local"]
            RAG["rag-mcp<br/>MCP · catálogo em memória"]

            subgraph Scheduling["Agendamento"]
                direction TB
                Schedule["schedule-api<br/>FastAPI · JWT · SQLAlchemy"]
                ScheduleDB[("schedule-database<br/>SQLite · volume persistente")]
                Schedule -->|"SQLAlchemy"| ScheduleDB
            end
        end

        subgraph TemporaryStorage["Armazenamento temporário"]
            direction LR
            TempStore[("image-storage<br/>tmpfs · 64 MiB")]
        end

        subgraph Observability["Observabilidade"]
            direction LR
            Collector["otel-collector<br/>OTLP/HTTP · 4318"]
            OpenObserve["openobserve<br/>logs · traces"]
            Collector -->|"OTLP/HTTP"| OpenObserve
        end
    end

    subgraph External["Serviços externos"]
        direction TB
        Model["API do modelo configurado"]
        Vision["Google Cloud Vision<br/>DOCUMENT_TEXT_DETECTION"]
    end

    Runtime <-->|"API do modelo · tool calling"| Model
    Runtime <-->|"MCP / SSE<br/>extract_exams(image_id)"| OCR
    Runtime <-->|"MCP / SSE<br/>search_exams(exam_names)"| RAG
    Runtime -->|"HTTP · POST /appointments · JWT"| Schedule
    Runtime -->|"escrita e limpeza"| TempStore
    TempStore -->|"leitura somente"| OCR
    OCR <-->|"HTTPS · imagem e resposta OCR"| Vision

    Schedule -.->|"OTLP · logs e traces"| Collector
    RAG -.->|"OTLP · logs e traces"| Collector
    Runtime -.->|"OTLP · logs e traces"| Collector
    OCR -.->|"OTLP · logs e traces"| Collector
```

As linhas sólidas representam chamadas de negócio e acesso a dados; as tracejadas representam somente a exportação de telemetria.

## Responsabilidades

| Elemento | Responsabilidade e interface |
|---|---|
| `assistant-runtime` | Executar `validate`, `generate` e `process`; carregar a factory gerada, orquestrar o agente ADK e apresentar o resultado humanizado no CLI. |
| `ocr-mcp` | Expor `extract_exams(image_id)` por SSE, ler a imagem temporária, chamar o Cloud Vision, classificar localmente os dois layouts de referência e aplicar a barreira local de PII antes de responder. |
| `rag-mcp` | Carregar e validar o catálogo versionado, construir um índice em memória e expor `search_exams(exam_names)` por SSE; correspondências aproximadas exigem revisão e não retornam códigos. |
| `schedule-api` | Autenticar o usuário por JWT, reconciliar reservas pelo `sub` e alocar slots globais exclusivos por `POST /appointments`; receber chamadas autenticadas do runtime e expor Swagger apenas em loopback no Compose local. |
| `schedule-database` | Volume nomeado persistente para o SQLite; contém tabelas de agendamento e os exames relacionados por chave estrangeira. |
| `image-storage` | Volume `tmpfs` temporário compartilhado; o runtime grava e remove arquivos, enquanto o OCR tem acesso somente de leitura. |
| `otel-collector` | Receber OTLP/HTTP dos quatro apps, processar em lote e encaminhar logs e traces para o backend na rede interna do Compose. |
| `openobserve` | Armazenar e consultar logs e traces em volume separado; a interface local é publicada somente em `127.0.0.1:5080`. |
| API do modelo | Apoiar o agente na execução da tool aprovada; recebe o identificador interno e os metadados necessários ao agente, nunca a imagem ou o texto OCR integral. |
| Google Cloud Vision | Reconhecer texto e posições na imagem enviada pelo OCR por `DOCUMENT_TEXT_DETECTION`. |
| Docker Compose | Construir os apps separadamente, conectá-los pela rede interna e montar o volume temporário com permissões distintas. |

## Fronteiras de confiança e operação

- `process` aceita somente um nome de arquivo no diretório de entrada permitido. O agente envia um UUID canônico à tool; não escolhe caminhos, URLs, credenciais ou endpoints.
- A cópia temporária fica em `tmpfs`; o runtime tem escrita e o OCR, somente leitura. O runtime permite um processamento ativo por vez e remove a cópia ao terminar.
- A imagem é enviada ao Google Cloud Vision para OCR. O uso de `tmpfs` reduz a retenção local, mas não significa que a imagem permaneça apenas nos containers; a decisão e as garantias do fornecedor estão registradas no [plano da Fase 2](phase2-plan.md).
- A API do modelo e o Cloud Vision são serviços externos separados. As credenciais são injetadas em execução apenas no container que as utiliza e não são copiadas para as imagens Docker nem versionadas.
- O OCR analisa localmente os valores de `exams` e `ambiguous_exams` com Presidio, spaCy em português e recognizers brasileiros configurados. Ao sinalizar PII, devolve somente um status genérico de revisão; se a análise falhar, não libera o resultado. O detector reduz risco e não garante identificar toda PII.
- Logs operacionais não incluem imagem, nome ou caminho do arquivo, UUID, dados pessoais, nomes de exames, texto OCR, prompts ou credenciais.
- Logs e spans exportados via Collector mantêm a mesma política de privacidade e usam o contexto distribuído para correlacionar a execução entre runtime, OCR, RAG e agendamento. Se o backend estiver indisponível, o fluxo funcional continua e os logs locais permanecem em `stderr`.
- O servidor OCR não publica uma porta no host; o runtime o acessa pela rede do Compose. O CLI apresenta mensagens funcionais em português no `stdout`; logs JSON e falhas técnicas sanitizadas usam `stderr`.
- Os servidores OCR e RAG não publicam portas no host; o runtime os acessa pela rede do Compose via MCP/SSE.
- A API de agendamento publica somente em `127.0.0.1:8001` no Compose local para permitir a validação pelo Swagger; o runtime a acessa pela rede interna.
- O emissor local de JWT é habilitado pelo Compose apenas para a demonstração; não substitui um provedor de identidade. O segredo é configuração de runtime e não deve ser versionado.
- Cada request obtém sua própria `Session`; o `Engine` e a fábrica de sessões vivem no lifespan da API. `BEGIN IMMEDIATE` e a restrição única do slot protegem a alocação concorrente.

## Limites atuais

A extração cobre os dois layouts de referência validados: lista numerada sem caixas e formulário com marcações X. Isso não representa suporte geral a documentos médicos ou manuscritos. Novos componentes e fluxos serão incluídos quando suas subfases forem especificadas.

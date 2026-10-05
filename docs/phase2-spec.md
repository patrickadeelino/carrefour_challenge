# Especificação técnica — Fase 2

**Estado:** a aprovação formal do escopo geral da Fase 2 continua aberta. As decisões desta fatia foram acordadas antes da implementação; o OCR da subfase 2.1 já está implementado e validado conforme esta especificação.

## 1. Objetivo e escopo

A Fase 2 conecta o agente `exam_scheduler` da Fase 1 aos serviços necessários para atender uma solicitação de exames: receber a imagem do pedido, identificar os exames, consultar o catálogo e solicitar um agendamento. O PRD descreve os requisitos do desafio; este documento detalha a arquitetura progressivamente, antes da implementação de cada subfase.

O primeiro entregável é a fatia vertical de OCR: executar `process --path <nome-do-arquivo>` dentro do container, enviar a imagem ao OCR por meio do agente e apresentar os exames no CLI. Essa fatia foi implementada e validada. A pesquisa no catálogo e o agendamento continuam no escopo geral da Fase 2, mas seus contratos ainda não são especificados aqui.

Esta especificação é deliberadamente incremental. Requisitos futuros aparecem como contexto e permanecem em aberto até a subfase correspondente; não são autorização para implementá-los junto com a fatia OCR.

## 2. Requisitos e rastreabilidade

| ID | Requisito da Fase 2 | Componente principal | Critério de aceite |
|---|---|---|---|
| F2-01 | Receber uma imagem pelo comando de atendimento do runtime. | CLI de runtime | `process --path <nome>` encontra a imagem na pasta de entrada permitida dentro do container. |
| F2-02 | Validar formato e tamanho antes de armazenar. | CLI e `TemporaryImageStore` | PNG/JPG válidos de até 10 MB são aceitos; arquivo vazio, corrompido, não suportado ou acima do limite é recusado sem arquivo parcial. |
| F2-03 | Passar ao agente apenas uma referência interna à imagem. | Runtime e armazenamento temporário | A imagem é armazenada em `tmpfs` sob UUID; a tool recebe o UUID, nunca um caminho ou URL escolhido pelo modelo. |
| F2-04 | Permitir que o agente acione OCR por uma tool aprovada. | Agente ADK e servidor MCP de OCR | O agente chama a tool de OCR com o UUID; o servidor resolve o arquivo dentro do diretório permitido. |
| F2-05 | Extrair exames sem enviar a imagem a um LLM. | Servidor MCP e Google Cloud Vision | Vision recebe os bytes para OCR; Gemini ou outro modelo de linguagem não recebe a imagem original. A identificação de marcações é local, conforme a POC dos dois layouts de referência. |
| F2-06 | Apresentar uma resposta estável no CLI. | CLI | Saída de sucesso em JSON no formato `{"exams": ["Hemograma completo"]}`; lista vazia é uma resposta válida. Todas as chaves JSON são em inglês. |
| F2-07 | Apagar a cópia temporária ao fim do atendimento. | Runtime e `TemporaryImageStore` | Imagem removida no caminho de sucesso e no de erro; rotina de limpeza remove arquivos UUID órfãos com mais de 30 minutos. |
| F2-08 | Proteger dados pessoais do paciente. | Servidor MCP de OCR e runtime | Resposta da tool e logs não incluem nome, documento ou contato do paciente; o original no diretório de entrada não é alterado nem apagado. |
| F2-09 | Executar o fluxo localmente em containers. | Docker Compose | O comando é executado dentro do container; a imagem de entrada está visível pelo mount de workspace e o armazenamento temporário é compartilhado com o OCR em modo somente leitura. |

Os requisitos mais amplos do desafio — catálogo/RAG, API de agendamento, MCPs correspondentes e fluxo completo — são registrados no [PRD](PRD.md) e no [plano da Fase 2](phase2-plan.md). Os contratos dessas partes serão detalhados antes de suas implementações.

## 3. Contratos do primeiro fluxo

### 3.1 Entrada do CLI

Comando previsto, executado no serviço `assistant-runtime`:

```text
docker compose exec assistant-runtime python -m carrefour_runtime process --path exam_request_pt_br.png
```

- `--path` recebe apenas o nome do arquivo, sem caminho absoluto ou componentes `..`.
- Na configuração inicial, o nome é resolvido dentro de `/workspace/tests/fixtures/images`, que já está visível pelo mount do workspace.
- O resolvedor rejeita links simbólicos e qualquer resolução que saia da pasta permitida.
- A imagem original fica intacta. A validação olha o conteúdo real, não apenas o sufixo do nome.
- Formatos aceitos: PNG e JPG/JPEG. Limite: 10 MB (`10_000_000` bytes), conforme o componente atual.
- Na execução normal, o agente usa o modelo definido pela especificação validada. Os testes podem substituir esse modelo por um modelo determinístico, sem alterar a especificação do agente.

A pasta de fixtures é o diretório de entrada desta demonstração. Um diretório ou mecanismo de upload para uso fora das fixtures será decidido antes de ampliar essa interface.

### 3.2 Resposta funcional

Sucesso é serializado como JSON no `stdout`, preservando a ordem reconhecida dos exames:

```json
{"exams": ["Hemograma completo", "Glicemia de jejum"]}
```

Se nenhum exame for identificado com segurança, a resposta sem ambiguidade é:

```json
{"exams": []}
```

O CLI não completa nomes, não inventa exames e não consulta ou normaliza contra o catálogo nesta subfase. Nomes de chaves JSON são sempre em inglês; valores dos nomes de exames permanecem como reconhecidos no documento. Quando houver marcação ambígua, o CLI imprime uma resposta JSON com status `review_required` e chaves `exams` e `ambiguous_exams`, e termina com código distinto de zero. Falhas técnicas sanitizadas vão para `stderr`.

Exemplo de resposta que solicita revisão manual:

```json
{"status": "review_required", "exams": ["Hemograma completo"], "ambiguous_exams": ["TSH"]}
```

### 3.3 Regras para os dois layouts de referência

- Lista sem caixas de seleção, que instrui realizar os exames exibidos: retornar todos os exames legíveis da lista.
- Formulário com caixas: retornar apenas os exames cuja caixa esteja marcada com X.
- A leitura do X usa análise local da imagem em conjunto com as posições/textos reconhecidos pelo OCR; não é feita por um LLM.
- O layout é escolhido por marcadores de texto conhecidos na resposta OCR: a frase `MARQUE COM X OS EXAMES SOLICITADOS` identifica o formulário; `EXAMES SOLICITADOS` junto de `REALIZAR OS EXAMES ABAIXO` identifica a lista numerada. No formulário, essa escolha encaminha para a análise visual local das caixas; não determina, por si só, quais estão marcadas.
- Se uma marcação não puder ser classificada com segurança, não inferir que está marcada ou desmarcada. Sinalizar necessidade de revisão manual, sem apresentar uma seleção potencialmente incorreta como resultado normal.
- A POC validou estes comportamentos nas duas imagens de referência documentadas no plano. Isso não demonstra suporte a formulários arbitrários, manuscritos ou marcas diferentes de X; tais formatos precisam de avaliação própria.

**Decisão de provedor e custo:** nesta entrega, manter Cloud Vision `DOCUMENT_TEXT_DETECTION` e a identificação dos dois layouts por marcadores no texto OCR. O Document AI Form Parser é uma alternativa futura: ele oferece detecção de checkboxes preenchidos/vazios e associação ao texto próximo, mas é um processador separado e tem cobrança própria. Como este é um desafio de portfólio e não queremos incorrer em gasto adicional para avaliá-lo, não faremos chamadas ao Form Parser. A taxa pública consultada em 2026-10-04 era US$ 30 por 1.000 páginas para Form Parser; o Cloud Vision informa as primeiras 1.000 unidades mensais gratuitas e US$ 1,50 por 1.000 unidades na faixa seguinte. Preços podem mudar e variar conforme moeda/região. Reconsiderar o Form Parser se o escopo passar a exigir formulários variados ou se a abordagem local falhar na validação. [Documentação do Form Parser](https://docs.cloud.google.com/document-ai/docs/form-parser) · [Preços do Document AI](https://cloud.google.com/products/document-ai/pricing) · [Preços do Cloud Vision](https://cloud.google.com/vision/pricing).

### 3.4 Erros e fronteira MCP

| Situação | Comportamento previsto |
|---|---|
| Arquivo inexistente, sem permissão ou fora da pasta permitida | CLI informa a falha de entrada em `stderr`; não inicia o OCR. |
| Conteúdo inválido, vazio, formato não suportado ou acima de 10 MB | Falha de validação; nenhum arquivo parcial permanece em `tmpfs`. |
| Erro operacional do processamento da tool | Servidor MCP retorna resultado de tool com `isError: true`; runtime apresenta mensagem sanitizada. |
| Argumento inválido ou falha de protocolo MCP/JSON-RPC | Erro de protocolo é tratado como falha da chamada; não é convertido em lista vazia. |
| MCP indisponível, conexão encerrada ou timeout | Falha de transporte apresentada pelo CLI, sem dados clínicos no erro. |
| OCR conclui sem detectar exames | Sucesso funcional com `{"exams": []}`. |
| Marcação ambígua | Não adivinhar; retornar status `review_required` com listas `exams` e `ambiguous_exams`, e encerrar com código distinto de zero. |

As categorias seguem a distinção do MCP entre erro de execução de tool, erro JSON-RPC e falha de transporte. A política de produto permite um processamento ativo por vez e é imposta pelo lock do runtime, coberto por teste unitário. No Compose local, `GOOGLE_CLOUD_VISION_API_KEY` é injetada apenas no OCR e `GOOGLE_API_KEY` apenas no runtime, em tempo de execução; as chaves ficam no `.env` ignorado pelo Git e não são copiadas para as imagens. O timeout do Vision é de 60 segundos, sem retries automáticos. As execuções reais estão registradas na seção de validação abaixo; como mediram o fluxo completo, não isolam a latência do Vision. Marcações ambíguas usam `status: "review_required"` e permanecem distintas do resultado válido `{"exams": []}`.

## 4. Componentes e responsabilidades

As responsabilidades abaixo cobrem somente a fatia de OCR. A busca no catálogo e o agendamento não participam deste fluxo inicial.

| Componente | Responsabilidade nesta fatia |
|---|---|
| CLI `process` | Resolver a entrada, coordenar o fluxo, exibir JSON e garantir limpeza em `finally`. |
| `TemporaryImageStore` | Validar bytes, criar UUID, gravar atomicamente, resolver/remover por UUID e limpar órfãos. |
| Factory gerada em `agent.py` | Criar o agente a partir do mapa de tools aprovado, mantendo o contrato exato da Fase 1. |
| Runtime de `process` | Fornecer as três tools exigidas pelo contrato da Fase 1: a tool MCP de OCR e stubs controlados para catálogo e agendamento. Os stubs informam que a capacidade não está implementada nesta fatia e não realizam chamadas externas. Na execução normal, usa o modelo definido pela especificação validada. |
| Agente Google ADK | Nesta fatia, seguir instruções limitadas ao processamento OCR e orquestrar a tool aprovada via MCP sobre SSE. Não recebe os bytes nem um caminho arbitrário. Nos testes, seu modelo pode ser substituído por um modelo determinístico. |
| Servidor MCP de OCR | Expor a tool por SSE, aceitar o UUID, ler o volume em modo somente leitura, invocar o Vision e devolver somente os exames após tratamento local. |
| Google Cloud Vision | Executar `DOCUMENT_TEXT_DETECTION` nos bytes da imagem. |
| Docker Compose | Executar runtime e servidor OCR em containers e compartilhar o volume `tmpfs` com permissões distintas. |

O `TemporaryImageStore`, o comando `process`, o servidor MCP e a conexão entre o ADK e o OCR estão implementados nesta fatia. Os testes automatizados simulam o Vision e o modelo; o harness E2E também foi executado manualmente com Vision real e modelo determinístico, conforme o registro desta especificação.

O runtime é um app Python independente em `apps/runtime/`, com seu próprio `pyproject.toml`, `uv.lock`, Dockerfile, pacote instalado e testes. O OCR MCP é outro app independente em `apps/ocr_mcp/`, também com build e dependências próprios. O Compose constrói cada app com seu diretório como contexto, mantém o OCR sem porta publicada no host e compartilha o volume `tmpfs` com montagem somente leitura no container OCR. O runtime chama o serviço OCR pela tool MCP via SSE; o fluxo foi validado com testes locais e com as duas fixtures no E2E manual.

## 5. Privacidade e segurança

- A cópia temporária fica no volume `tmpfs` compartilhado; o runtime escreve e o MCP de OCR lê. O volume do OCR é montado como somente leitura.
- A imagem original é enviada ao Google Cloud Vision para reconhecimento de texto. Essa decisão usa as garantias documentadas do fornecedor registradas no [plano da Fase 2](phase2-plan.md); `tmpfs` reduz a retenção local, mas não significa que a imagem permaneça apenas nos containers.
- A imagem original não é adicionada ao contexto do Gemini/LLM. O agente envia apenas o UUID à tool; o OCR retorna nomes de exames, nunca o texto integral do documento.
- O MCP de OCR mascara nome, documentos e contatos antes de devolver a resposta. Logs e exceções não devem conter bytes, texto OCR integral, PII ou o UUID interno.
- O modelo não escolhe caminho, URL, nome de arquivo, volume ou credencial. O servidor resolve somente um UUID canônico dentro do diretório configurado.
- Não usar `map.json`; o UUID é o nome do arquivo e permite resolução direta sem varrer o diretório.
- O arquivo é removido em `finally` tanto em sucesso como em falha. Uma limpeza adicional remove órfãos acima de 30 minutos.
- A política acordada para a primeira versão é um atendimento por vez. O runtime impõe o limite com um lock entre processos, coberto por teste unitário.
- Segredos e credenciais não entram na especificação JSON, na imagem Docker ou no Git. No Compose local, são injetados em tempo de execução a partir do `.env` ignorado pelo Git.

## 6. Testes e critérios de aceite

### Testes automatizados

- Testes unitários cobrem resolução segura do nome, validação de formato/tamanho, geração/resolução/exclusão do UUID, gravação atômica, erros e limpeza.
- Testes do servidor MCP simulam o Cloud Vision e validam argumentos, resposta `{"exams": [...]}`, mascaramento e erros sem rede externa.
- Testes do fluxo verificam que a tool recebe apenas o UUID, que a imagem é apagada em sucesso e erro, e que nenhuma PII aparece em logs/mensagens.
- Testes de seleção cobrem a fixture sem checkboxes e a fixture com X, incluindo marcação ambígua.

### Teste ponta a ponta com Vision real

O entregável da subfase inclui um teste de integração ponta a ponta, optativo e executado dentro do ambiente Docker:

- Percorrer `process`, armazenamento temporário, factory gerada, agente ADK, chamada MCP via SSE, servidor OCR, Cloud Vision e JSON final do CLI.
- Substituir o modelo definido na especificação por um modelo determinístico de teste para provocar a chamada da tool. O teste não chama Gemini; a chamada ao Cloud Vision é real.
- Executar o entry point do runtime pelo harness de teste, com injeção interna do executor determinístico; o `process` de produção não ganha uma opção pública de modo de teste.
- Executar nas duas fixtures sintéticas: a lista sem checkboxes deve retornar os cinco exames esperados; o formulário deve retornar apenas os seis itens marcados (EX-101, EX-102, EX-104, EX-106, EX-109 e EX-110), conforme a POC visualmente conferida.
- Verificar também que o arquivo de origem permanece intacto, a cópia em `tmpfs` é removida ao final e a resposta não contém PII.
- Exigir credenciais do Vision configuradas fora do repositório. O teste não é executado automaticamente no CI; a execução usa Cloud Vision real e deve ser explícita.

O harness está em `apps/runtime/tests/e2e/test_live_vision.py`. Ele só roda com
`RUN_LIVE_VISION_E2E=1` e seleciona uma das duas fixtures por
`E2E_IMAGE_NAME`; os comandos reproduzíveis estão no README principal. A
validação real foi executada em 2026-10-04. `exam_request_pt_br.png` retornou
cinco exames em 4,47 s e `exam_request_pt_br_simplified.png` retornou os seis
exames marcados em 4,57 s. O usuário confirmou visualmente que as seleções
correspondem às imagens. O harness confirmou o resultado JSON esperado, uma
chamada à tool pelo modelo determinístico, o uso apenas do UUID no prompt, a
remoção da cópia temporária, a integridade do arquivo original e a ausência dos
marcadores sintéticos de PII na saída e nos erros. O Cloud Vision foi chamado
realmente; Gemini não foi chamado. A inspeção dos logs do container OCR mostrou
somente metadados de transporte e status HTTP, sem conteúdo da imagem ou dos
exames. As durações são do fluxo completo e não representam uma medição isolada
da latência do Vision.

Na primeira tentativa, o container ainda continha uma versão anterior do teste:
as chamadas ao Vision ocorreram, mas o teste falhou em uma asserção obsoleta.
Após reconstruir a imagem do runtime, os dois casos passaram. As quatro
tentativas desta sequência fizeram quatro chamadas reais ao Vision; esse número
se refere a estes comandos, não ao histórico completo do container.

A página oficial de preços informa que os primeiros 1.000 usos mensais de `Document Text Detection` são gratuitos e que cada recurso aplicado a uma imagem conta como uma unidade faturável. Executar as duas fixtures uma vez consome duas unidades; as quatro chamadas reais feitas nesta validação consumiram quatro unidades no total. [Preços do Cloud Vision](https://cloud.google.com/vision/pricing).

Os testes automatizados locais continuam simulando o Vision para validar falhas e limpeza sem chamadas externas. O teste ponta a ponta real complementa essa cobertura e verifica a integração com o provedor.

### Critério de aceite da subfase 2.1

Executar via Docker Compose `process --path <nome>` para as duas imagens de referência, obter a seleção de exames esperada no JSON do CLI usando Cloud Vision real e um modelo determinístico, não enviar a imagem a um LLM, e remover a cópia temporária em sucesso e em falha. Erros não devem expor PII nem deixar arquivos após a finalização.

## 7. Fases posteriores — somente visão geral

Estas etapas pertencem à Fase 2, mas permanecem fora da implementação corrente:

1. **Catálogo e busca/RAG:** confirmar fonte, formato, critérios de busca e avaliação para o catálogo exigido.
2. **API de agendamento:** especificar endpoints, modelos, disponibilidade e conflitos conforme o desafio.
3. **Privacidade transversal:** verificar que API, busca, agente e logs preservam a fronteira definida no OCR.
4. **Integração do agente:** ligar OCR, catálogo e agendamento e testar o fluxo com ferramentas locais e modelo determinístico.
5. **Ambiente completo:** compor todos os serviços no Docker Compose e avaliar separadamente qualquer execução opcional com Gemini real.

Cada etapa deve ter contratos e critérios detalhados antes de sua implementação. O [plano da Fase 2](phase2-plan.md) acompanha a ordem e o checklist.

## 8. Referências

- [Google ADK — documentação](https://google.github.io/adk-docs/)
- [Google ADK — `McpToolset`](https://github.com/google/adk-python/blob/main/src/google/adk/tools/mcp_tool/mcp_toolset.py)
- [Google ADK — Runner e InMemoryRunner](https://github.com/google/adk-python/blob/main/docs/guides/runners/runner/index.md)
- [MCP — especificação de ferramentas](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-06-18/schema.mdx)
- [MCP Python SDK — tratamento de erros](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/handling-errors.md)
- [Cloud Vision — requisições REST](https://docs.cloud.google.com/vision/docs/request)
- [Google Cloud — boas práticas para chaves de API](https://docs.cloud.google.com/docs/authentication/api-keys-best-practices)
- [Cloud Vision — OCR](https://docs.cloud.google.com/vision/docs/ocr)
- [Cloud Vision — idiomas](https://docs.cloud.google.com/vision/docs/languages)
- [Cloud Vision — uso de dados](https://docs.cloud.google.com/vision/docs/data-usage)
- [Docker — mounts `tmpfs`](https://docs.docker.com/engine/storage/tmpfs/)
- [Docker Compose — volumes](https://docs.docker.com/reference/compose-file/volumes/)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)

## 9. Decisões operacionais da subfase 2.1

1. **Timeout e retries:** manter o timeout de 60 segundos no Vision e não fazer retries automáticos. As duas execuções E2E passaram; seus tempos totais foram 4,47 s e 4,57 s, insuficientes para estimar a distribuição da latência do provedor ou revisar o timeout.
2. **Credenciais no ambiente Docker local:** Compose injeta `GOOGLE_CLOUD_VISION_API_KEY` somente no OCR e `GOOGLE_API_KEY` somente no runtime em tempo de execução. O `.env` é ignorado pelo Git; as chaves não entram no build das imagens.
3. **Resposta de revisão manual:** o contrato é `status: "review_required"`, com `exams` e `ambiguous_exams`, distinto de `{"exams": []}`. As duas imagens reais não produziram marcações ambíguas; o comportamento para marcas incertas permanece coberto nos testes locais.
4. **Concorrência:** permitir somente um processamento ativo por vez. O runtime impõe a regra com lock entre processos, e o teste unitário verifica a rejeição de um segundo processamento enquanto o primeiro está ativo.

Essas decisões operacionais foram implementadas e validadas na subfase 2.1. A aprovação do escopo geral da Fase 2 continua registrada separadamente no plano.

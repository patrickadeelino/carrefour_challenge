# Especificação técnica — Fase 2

**Estado:** rascunho para revisão. As decisões abaixo refletem o que foi combinado; a implementação do OCR começa após a revisão e aprovação desta especificação.

## 1. Objetivo e escopo

A Fase 2 conecta o agente `exam_scheduler` da Fase 1 aos serviços necessários para atender uma solicitação de exames: receber a imagem do pedido, identificar os exames, consultar o catálogo e solicitar um agendamento. O PRD descreve os requisitos do desafio; este documento detalha a arquitetura progressivamente, antes da implementação de cada subfase.

O primeiro entregável implementável é a fatia vertical de OCR: executar `process --path <nome-do-arquivo>` dentro do container, enviar a imagem ao OCR por meio do agente e apresentar os exames no CLI. A pesquisa no catálogo e o agendamento continuam no escopo geral da Fase 2, mas seus contratos ainda não são especificados aqui.

Esta especificação é deliberadamente incremental. Requisitos futuros aparecem como contexto e permanecem em aberto até a subfase correspondente; não são autorização para implementá-los junto com a fatia OCR.

## 2. Requisitos e rastreabilidade

| ID | Requisito da Fase 2 | Componente principal | Critério de aceite |
|---|---|---|---|
| F2-01 | Receber uma imagem pelo comando de atendimento do runtime. | CLI de runtime | `process --path <nome>` encontra a imagem na pasta de entrada permitida dentro do container. |
| F2-02 | Validar formato e tamanho antes de armazenar. | CLI e `TemporaryImageStore` | PNG/JPG válidos de até 10 MB são aceitos; arquivo vazio, corrompido, não suportado ou acima do limite é recusado sem arquivo parcial. |
| F2-03 | Passar ao agente apenas uma referência interna à imagem. | Runtime e armazenamento temporário | A imagem é armazenada em `tmpfs` sob UUID; a tool recebe o UUID, nunca um caminho ou URL escolhido pelo modelo. |
| F2-04 | Permitir que o agente acione OCR por uma tool aprovada. | Agente ADK e servidor MCP de OCR | O agente chama a tool de OCR com o UUID; o servidor resolve o arquivo dentro do diretório permitido. |
| F2-05 | Extrair exames sem enviar a imagem a um LLM. | Servidor MCP e Google Cloud Vision | Vision recebe os bytes para OCR; Gemini ou outro modelo de linguagem não recebe a imagem original. A identificação de marcações é local, conforme a POC dos dois layouts de referência. |
| F2-06 | Apresentar uma resposta estável no CLI. | CLI | Saída de sucesso em JSON no formato `{"exames": ["Hemograma completo"]}`; lista vazia é uma resposta válida. |
| F2-07 | Apagar a cópia temporária ao fim do atendimento. | Runtime e `TemporaryImageStore` | Imagem removida no caminho de sucesso e no de erro; rotina de limpeza remove arquivos UUID órfãos com mais de 30 minutos. |
| F2-08 | Proteger dados pessoais do paciente. | Servidor MCP de OCR e runtime | Resposta da tool e logs não incluem nome, documento ou contato do paciente; o original no diretório de entrada não é alterado nem apagado. |
| F2-09 | Executar o fluxo localmente em containers. | Docker Compose | O comando é executado dentro do container; a imagem de entrada está visível pelo mount de workspace e o armazenamento temporário é compartilhado com o OCR em modo somente leitura. |

Os requisitos mais amplos do desafio — catálogo/RAG, API de agendamento, MCPs correspondentes e fluxo completo — são registrados no [PRD](PRD.md) e no [plano da Fase 2](phase2-plan.md). Os contratos dessas partes serão detalhados antes de suas implementações.

## 3. Contratos do primeiro fluxo

### 3.1 Entrada do CLI

Comando previsto, executado no serviço `assistant-runtime`:

```text
docker compose exec assistant-runtime python -m carrefour_transpiler process --path exam_request_pt_br.png
```

- `--path` recebe apenas o nome do arquivo, sem caminho absoluto ou componentes `..`.
- Na configuração inicial, o nome é resolvido dentro de `/workspace/tests/fixtures/images`, que já está visível pelo mount do workspace.
- O resolvedor rejeita links simbólicos e qualquer resolução que saia da pasta permitida.
- A imagem original fica intacta. A validação olha o conteúdo real, não apenas o sufixo do nome.
- Formatos aceitos: PNG e JPG/JPEG. Limite: 10 MB (`10_000_000` bytes), conforme o componente atual.

A pasta de fixtures é o diretório de entrada desta demonstração. Um diretório ou mecanismo de upload para uso fora das fixtures será decidido antes de ampliar essa interface.

### 3.2 Resposta funcional

Sucesso é serializado como JSON no `stdout`, preservando a ordem reconhecida dos exames:

```json
{"exames": ["Hemograma completo", "Glicemia de jejum"]}
```

Se nenhum exame for identificado com segurança, a resposta sem ambiguidade é:

```json
{"exames": []}
```

O CLI não completa nomes, não inventa exames e não consulta ou normaliza contra o catálogo nesta subfase. Erros e mensagens para revisão manual vão para `stderr`; o processo termina com status diferente de zero. O formato detalhado de um aviso de revisão permanece sujeito à decisão aberta na seção 9.

### 3.3 Regras para os dois layouts de referência

- Lista sem caixas de seleção, que instrui realizar os exames exibidos: retornar todos os exames legíveis da lista.
- Formulário com caixas: retornar apenas os exames cuja caixa esteja marcada com X.
- A leitura do X usa análise local da imagem em conjunto com as posições/textos reconhecidos pelo OCR; não é feita por um LLM.
- Se uma marcação não puder ser classificada com segurança, não inferir que está marcada ou desmarcada. Sinalizar necessidade de revisão manual, sem apresentar uma seleção potencialmente incorreta como resultado normal.
- A POC validou estes comportamentos nas duas imagens de referência documentadas no plano. Isso não demonstra suporte a formulários arbitrários, manuscritos ou marcas diferentes de X; tais formatos precisam de avaliação própria.

### 3.4 Erros e fronteira MCP

| Situação | Comportamento previsto |
|---|---|
| Arquivo inexistente, sem permissão ou fora da pasta permitida | CLI informa a falha de entrada em `stderr`; não inicia o OCR. |
| Conteúdo inválido, vazio, formato não suportado ou acima de 10 MB | Falha de validação; nenhum arquivo parcial permanece em `tmpfs`. |
| Erro operacional do processamento da tool | Servidor MCP retorna resultado de tool com `isError: true`; runtime apresenta mensagem sanitizada. |
| Argumento inválido ou falha de protocolo MCP/JSON-RPC | Erro de protocolo é tratado como falha da chamada; não é convertido em lista vazia. |
| MCP indisponível, conexão encerrada ou timeout | Falha de transporte apresentada pelo CLI, sem dados clínicos no erro. |
| OCR conclui sem detectar exames | Sucesso funcional com `{"exames": []}`. |
| Marcação ambígua | Não adivinhar; solicitar revisão manual e não apresentar a resposta como seleção confiável. |

As categorias seguem a distinção do MCP entre erro de execução de tool, erro JSON-RPC e falha de transporte. A forma exata da mensagem no CLI e o limite de timeout ainda precisam ser fechados antes da implementação.

## 4. Componentes e responsabilidades

As responsabilidades abaixo cobrem somente a fatia de OCR. A busca no catálogo e o agendamento não participam deste fluxo inicial.

| Componente | Responsabilidade nesta fatia |
|---|---|
| CLI `process` | Resolver a entrada, coordenar o fluxo, exibir JSON e garantir limpeza em `finally`. |
| `TemporaryImageStore` | Validar bytes, criar UUID, gravar atomicamente, resolver/remover por UUID e limpar órfãos. |
| Factory gerada em `agent.py` | Criar o agente a partir do mapa de tools aprovado, mantendo o contrato exato da Fase 1. |
| Runtime de `process` | Fornecer as três tools exigidas pelo contrato da Fase 1: a tool MCP de OCR e stubs controlados para catálogo e agendamento. Os stubs informam que a capacidade não está implementada nesta fatia e não realizam chamadas externas. |
| Agente Google ADK | Nesta fatia, seguir instruções limitadas ao processamento OCR e orquestrar a tool aprovada via MCP sobre SSE. Não recebe os bytes nem um caminho arbitrário. |
| Servidor MCP de OCR | Expor a tool por SSE, aceitar o UUID, ler o volume em modo somente leitura, invocar o Vision e devolver somente os exames após tratamento local. |
| Google Cloud Vision | Executar `DOCUMENT_TEXT_DETECTION` nos bytes da imagem. |
| Docker Compose | Executar runtime e servidor OCR em containers e compartilhar o volume `tmpfs` com permissões distintas. |

O `TemporaryImageStore` já está implementado. O comando `process`, o servidor MCP e a conexão entre o ADK e o OCR ainda não estão implementados.

## 5. Privacidade e segurança

- A cópia temporária fica no volume `tmpfs` compartilhado; o runtime escreve e o MCP de OCR lê. O volume do OCR será montado como somente leitura.
- A imagem original é enviada ao Google Cloud Vision para reconhecimento de texto. Essa decisão usa as garantias documentadas do fornecedor registradas no [plano da Fase 2](phase2-plan.md); `tmpfs` reduz a retenção local, mas não significa que a imagem permaneça apenas nos containers.
- A imagem original não é adicionada ao contexto do Gemini/LLM. O agente envia apenas o UUID à tool; o OCR retorna nomes de exames, nunca o texto integral do documento.
- O MCP de OCR mascara nome, documentos e contatos antes de devolver a resposta. Logs e exceções não devem conter bytes, texto OCR integral, PII ou o UUID interno.
- O modelo não escolhe caminho, URL, nome de arquivo, volume ou credencial. O servidor resolve somente um UUID canônico dentro do diretório configurado.
- Não usar `map.json`; o UUID é o nome do arquivo e permite resolução direta sem varrer o diretório.
- O arquivo é removido em `finally` tanto em sucesso como em falha. Uma limpeza adicional remove órfãos acima de 30 minutos.
- A primeira versão assume um atendimento por vez. O mecanismo para impor concorrência única será definido antes da integração completa.
- Segredos e credenciais não entram na especificação JSON, na imagem Docker ou no Git; serão injetados na configuração de execução.

## 6. Testes e critérios de aceite

### Testes automatizados

- Testes unitários cobrem resolução segura do nome, validação de formato/tamanho, geração/resolução/exclusão do UUID, gravação atômica, erros e limpeza.
- Testes do servidor MCP simulam o Cloud Vision e validam argumentos, resposta `{"exames": [...]}`, mascaramento e erros sem rede externa.
- Testes do fluxo verificam que a tool recebe apenas o UUID, que a imagem é apagada em sucesso e erro, e que nenhuma PII aparece em logs/mensagens.
- Testes de seleção cobrem a fixture sem checkboxes e a fixture com X, incluindo marcação ambígua.

### Teste ponta a ponta com Vision real

O entregável da subfase inclui um teste de integração ponta a ponta, optativo e executado dentro do ambiente Docker:

- Percorrer `process`, armazenamento temporário, factory gerada, agente ADK, chamada MCP via SSE, servidor OCR, Cloud Vision e JSON final do CLI.
- Usar um modelo determinístico de teste para provocar a chamada da tool; o teste não chama Gemini. A chamada ao Cloud Vision é real.
- Executar nas duas fixtures sintéticas: a lista sem checkboxes deve retornar os cinco exames esperados; o formulário deve retornar apenas os seis itens marcados (EX-101, EX-102, EX-104, EX-106, EX-109 e EX-110), conforme a POC visualmente conferida.
- Verificar também que o arquivo de origem permanece intacto, a cópia em `tmpfs` é removida ao final e a resposta não contém PII.
- Exigir credenciais do Vision configuradas fora do repositório. O teste não é executado automaticamente no CI; a execução usa Cloud Vision real e deve ser explícita.

A página oficial de preços informa que os primeiros 1.000 usos mensais de `Document Text Detection` são gratuitos e que cada recurso aplicado a uma imagem conta como uma unidade faturável. Com um recurso por fixture, uma execução normal deste teste consome duas unidades do limite mensal. [Preços do Cloud Vision](https://cloud.google.com/vision/pricing).

Os testes automatizados locais continuam simulando o Vision para validar falhas e limpeza sem chamadas externas. O teste ponta a ponta real complementa essa cobertura e verifica a integração com o provedor.

### Critério de aceite da subfase 2.1

Executar via Docker Compose `process --path <nome>` para as duas imagens de referência, obter a seleção de exames esperada no JSON do CLI usando Cloud Vision real e um modelo determinístico, não enviar a imagem a um LLM, e remover a cópia temporária em sucesso e em falha. Erros não devem expor PII nem deixar arquivos após a finalização.

## 7. Fases posteriores — somente visão geral

Estas etapas pertencem à Fase 2, mas permanecem fora da implementação corrente:

1. **API de agendamento:** especificar endpoints, modelos, disponibilidade e conflitos conforme o desafio.
2. **Catálogo e busca/RAG:** confirmar fonte, formato, critérios de busca e avaliação para o catálogo exigido.
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
- [Cloud Vision — OCR](https://docs.cloud.google.com/vision/docs/ocr)
- [Cloud Vision — idiomas](https://docs.cloud.google.com/vision/docs/languages)
- [Cloud Vision — uso de dados](https://docs.cloud.google.com/vision/docs/data-usage)
- [Docker — mounts `tmpfs`](https://docs.docker.com/engine/storage/tmpfs/)
- [Docker Compose — volumes](https://docs.docker.com/reference/compose-file/volumes/)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)

## 9. Decisões técnicas pendentes antes do código

1. **Timeout e retries:** definir limites de conexão e processamento e se haverá retry da chamada ao Vision/MCP.
2. **Credenciais no ambiente Docker local:** definir como disponibilizar credenciais do Vision sem gravá-las na imagem, no Compose versionado ou no Git.
3. **Resposta de revisão manual:** definir a representação no contrato/CLI quando a marcação estiver ambígua, sem confundi-la com `{"exames": []}`.
4. **Concorrência:** definir como impor o limite de um atendimento ativo se runtime e OCR receberem chamadas simultâneas.

Essas pendências não impedem a revisão do desenho. Devem ser resolvidas antes de implementar os componentes que dependem delas.

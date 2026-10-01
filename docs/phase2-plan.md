# Plano da Fase 2

**Estado:** rascunho inicial de `phase2-spec.md` preparado para revisão. O armazenamento temporário e o runtime independente estão implementados. A implementação do fluxo OCR começa depois de revisar e aprovar a especificação.

**Regra de trabalho:** fechar e revisar a especificação da Fase 2 antes de continuar a implementação. Depois, avançar uma subfase por vez, validando o entregável e documentando as decisões.

## Objetivo provisório

Preparar os serviços e as integrações que permitirão ao agente `exam_scheduler`, definido na Fase 1, realizar o fluxo de atendimento: interpretar uma solicitação com imagem, identificar exames, consultar disponibilidade e solicitar um agendamento, respeitando os requisitos de privacidade do desafio.

## Subfases propostas

### 2.0 — Especificação da Fase 2

**Objetivo:** consolidar requisitos, fluxo, contratos, limites de privacidade e critérios de aceite antes de ampliar a implementação.

- [x] Criar o rascunho `docs/phase2-spec.md` como especificação de referência da Fase 2.
- [x] Mapear os requisitos da primeira fatia a componentes e critérios de aceite, a partir do PRD e das decisões registradas.
- [x] Especificar o primeiro fluxo: comando `process --path <nome-do-arquivo>` recebe uma imagem e apresenta os exames extraídos no CLI.
- [x] Definir a resolução inicial do nome na pasta montada no container: `/workspace/tests/fixtures/images`; aceitar somente o nome e restringir a resolução a essa pasta.
- [x] Descrever a sequência entre CLI de runtime, armazenamento temporário, agente ADK, tool/MCP de OCR e resultado apresentado no CLI.
- [ ] Fechar o contrato para timeout, retries e resposta de revisão manual; categorias de erros e resposta de sucesso estão documentadas no rascunho.
- [x] Registrar as regras de validação de PNG/JPG, limite de 10 MB, uso do UUID interno e limpeza em sucesso ou falha.
- [x] Registrar o limite de privacidade: o agente recebe o `image_id`, o servidor OCR mascara PII e a imagem bruta não entra no contexto do LLM.
- [x] Definir a composição do agente gerado nesta fatia: tools controladas de stub para catálogo e agendamento, sem chamadas externas; instruções limitadas ao OCR.
- [x] Implementar o componente reutilizável `TemporaryImageStore`, com validação, gravação atômica, resolução por UUID, exclusão e limpeza de órfãos; os testes unitários do componente estão presentes.
- [x] Configurar a base de desenvolvimento em Docker: dependências `dev`, workspace montado em `/workspace`, runtime não root e volume `tmpfs`; `docker compose config` foi validado.
- [x] Organizar o runtime atual como app Python independente, com build, dependências, testes e documentação próprios; manter os materiais da POC na raiz.
- [x] Atualizar o system design e manter rastreabilidade entre requisitos, componentes e testes.
- [ ] Revisar e aprovar a especificação e fechar as pendências técnicas antes de iniciar a próxima implementação.

**Entregável:** `docs/phase2-spec.md` revisada e aprovada, com o escopo e os critérios da primeira fatia de implementação.

### 2.1 — OCR: imagem recebida até exames no CLI

**Objetivo:** entregar o primeiro fluxo utilizável de ponta a ponta: receber uma imagem pelo comando de runtime, executar o caminho OCR previsto e apresentar a lista de exames no CLI.

- [ ] Implementar o comando de runtime `process --path <nome-do-arquivo>`, resolvendo o nome na pasta de entrada montada.
- [ ] Validar o arquivo e armazená-lo no `TemporaryImageStore`, mantendo o UUID interno ao fluxo.
- [ ] Implementar o servidor MCP de OCR via SSE, com acesso somente leitura ao volume compartilhado.
- [ ] Fazer o OCR resolver a imagem pelo UUID e chamar o Google Cloud Vision `DOCUMENT_TEXT_DETECTION`.
- [ ] Mascarar nomes, documentos e contatos no servidor OCR antes de retornar a lista de exames.
- [ ] Ligar o fluxo ao agente ADK para que o agente acione a tool de OCR com o `image_id`; fornecer stubs controlados para catálogo e agendamento, conforme decidido na especificação.
- [ ] Apresentar no CLI os exames no contrato acordado, inclusive o caso válido `{"exames": []}`.
- [ ] Remover a imagem temporária em `finally`, tanto em sucesso quanto em erro.
- [ ] Cobrir leitura e resolução do caminho, validação, contrato MCP, erros e limpeza com testes sem chamadas externas.
- [ ] Criar e executar, de forma explícita e fora do CI, um teste ponta a ponta de integração com Cloud Vision real e modelo determinístico nas duas fixtures sintéticas; verificar resultado, integridade do original e limpeza do temporário.

**Critério de aceite:** `process --path <nome>` executado via Docker Compose processa uma imagem da pasta montada, apresenta os exames extraídos no CLI e remove a imagem temporária ao concluir. Erros não exibem PII nem deixam a imagem armazenada após a finalização.

### POC concluída: extração de exames nos dois layouts sintéticos

**Objetivo da validação:** conferir se um fluxo com Cloud Vision OCR e análise local consegue retornar os exames corretos em duas imagens de demonstração: uma lista numerada sem caixas de seleção e um formulário com checkboxes.

**Resultado:** a validação funcionou para as duas amostras.

- `exam_request_pt_br.png`: a lista numerada não tem checkboxes e instrui a realizar os exames listados. O fluxo retornou os cinco itens: Hemograma completo, Glicemia de jejum, Hemoglobina glicada (HbA1c), Colesterol total e frações, e TSH (hormônio tireoestimulante).
- `exam_request_pt_br_simplified.png`: o formulário tem dez checkboxes. O OCR localizou códigos e textos; a análise local de pixels identificou seis marcações: EX-101, EX-102, EX-104, EX-106, EX-109 e EX-110.
- Os resultados foram conferidos visualmente contra as imagens. Não foi chamado Gemini, GLM ou outro LLM: Cloud Vision foi usado para OCR; a classificação dos X foi feita localmente.

**Limite da evidência:** são duas amostras sintéticas, com layouts conhecidos. A POC demonstra viabilidade para esses formatos; não valida formulários arbitrários, manuscritos ou outros tipos de marca. Na lista sem caixas, retornar todos depende da instrução contextual de que os exames listados devem ser realizados.

**Artefatos da POC:** os scripts de exploração ficam em `scripts/vision_ocr.py`, `scripts/vision_exam_marks.py` e `scripts/validate_exam_selection.py`. O relatório executado está em `generated/vision-validation/report.json`.

**Ordem de implementação acordada:** a recepção e o armazenamento temporário local precedem o servidor/tool de OCR. O componente interno já foi implementado; o caminho de entrada pelo comando de atendimento será conectado quando o OCR estiver disponível. A imagem é armazenada em `tmpfs` sob UUID e o OCR receberá somente esse ID. Veja a seção “Recepção e armazenamento temporário de imagem”.

### 2.2 — API de agendamento

- [ ] Definir endpoints e modelos de dados conforme o enunciado.
- [ ] Implementar regras de disponibilidade e conflito de horários.
- [ ] Cobrir casos válidos, inválidos e de erro.
- [ ] Documentar a API e sua configuração local.

**Entrega candidata:** API FastAPI testável sem o agente.

### 2.3 — Catálogo de exames e busca

- [ ] Confirmar fonte, formato e volume do catálogo exigido.
- [ ] Preparar e validar os dados do catálogo.
- [ ] Implementar busca e critérios de avaliação dos resultados.
- [ ] Expor a capacidade pela interface definida na subfase 2.0.
- [ ] Testar sem depender de um modelo externo.

**Entrega candidata:** busca de exames disponível ao agente por uma interface documentada.


### 2.4 — Verificação transversal de privacidade

> A anonimização dos dados extraídos acontece dentro do MCP de OCR, na subfase 2.1. Esta etapa verifica que os outros componentes respeitam esse limite e não reintroduzem exposição ou persistência de PII.

- [ ] Revisar logs e mensagens de erro dos serviços para evitar exposição de dados pessoais.
- [ ] Confirmar que armazenamento, API e agente não persistem nem propagam PII desnecessária.
- [ ] Testar os limites de privacidade definidos para o sistema.

**Entrega candidata:** evidências de que os componentes respeitam o limite de privacidade definido.

### 2.5 — Integração do fluxo completo no agente

- [ ] Ligar os IDs de catálogo e agendamento da Fase 1 às implementações aprovadas.
- [ ] Montar o agente com os serviços locais e a tool de OCR já entregue na subfase 2.1.
- [ ] Exercitar os fluxos com `InMemoryRunner` e modelo determinístico.
- [ ] Verificar sucesso, falha de tool e resposta a erros sem chamar Gemini.

**Entrega candidata:** agente usando OCR, catálogo e agendamento em cenários controlados.

### 2.6 — Ambiente local e validação ponta a ponta

- [x] Configurar a base do runtime no Docker Compose, montar o workspace e declarar o volume `tmpfs`.
- [ ] Adicionar e configurar os serviços necessários para o fluxo completo, incluindo o mount somente leitura do volume no OCR.
- [ ] Manter configuração de ambiente fora da especificação JSON do agente.
- [ ] Executar o fluxo ponta a ponta com serviços locais.
- [ ] Documentar como iniciar e verificar o ambiente.
- [ ] Avaliar teste opcional com Gemini real, credenciais configuradas e chamadas externas.

**Entrega candidata:** demonstração local reproduzível; integração com modelo real claramente identificada como opcional ou obrigatória conforme o desafio.

## Nota da discussão: referência da imagem para a tool de OCR

**Validação técnica:** a analogia com armazenamento de objetos (como S3 ou Cloud Storage) é válida, mas gerar um ID sozinho não faz upload nem concede acesso ao arquivo. Um componente de entrada precisa receber a imagem, registrá-la sob uma referência opaca e permitir que o serviço de OCR a recupere com autorização. O ID é uma referência, não uma credencial de autorização.

**Decisão aprovada para este desafio:** manter o modelo todo local e conteinerizado, sem GCS/S3, usando um volume compartilhado em `tmpfs`. O runtime/CLI registra a imagem no volume com um nome UUID vinculado à solicitação ativa. O agente chama a tool MCP de OCR via SSE com esse ID. O OCR valida o UUID e abre diretamente o arquivo correspondente no diretório permitido; não varre o diretório nem aceita caminhos ou URLs arbitrários fornecidos pelo modelo. O OCR mascara PII e retorna `{"exames": ["..."]}`.

**Decisão aprovada sobre o mapeamento:** não haverá `map.json` nesta etapa. O UUID é o nome do arquivo e permite resolução direta. O runtime/CLI remove a imagem ao final do fluxo, inclusive em caso de erro (`finally`); arquivos órfãos poderão ser removidos por uma rotina de limpeza baseada na idade do arquivo.

**Controles de acesso propostos:** runtime/CLI com escrita no volume; servidor OCR com leitura. A política exata para limpeza de solicitações abandonadas será fechada na implementação.

**Motivo da decisão:** a imagem do pedido pode conter PII. Mantê-la no armazenamento temporário e passar ao agente apenas um `image_id` evita que os bytes da imagem entrem no contexto do modelo. O agente ainda chama a tool OCR; o OCR acessa a imagem, mascara os dados pessoais e devolve somente a lista de exames. Essa fronteira reduz a exposição de PII ao modelo sem retirar do agente a orquestração da tool.

O desenho também evita introduzir GCS e credenciais cloud num desafio que exige a solução conteinerizada com Docker Compose. Se futuramente o runtime estiver no GCP, o mesmo contrato pode apontar para um objeto privado no Cloud Storage; o serviço de entrada controla o upload e o OCR acessa o objeto por identidade de serviço ou autorização temporária. Uma URL assinada não deve ser tratada como um ID comum: quem a possui pode usá-la enquanto válida.

**Estado:** tmpfs compartilhado, UUID como nome do arquivo e resolução direta sem `map.json` estão aprovados. A política concreta para limpeza de arquivos órfãos será definida na implementação.

### Decisão aprovada: Google ADK e Cloud Vision para OCR

**Decisão:** usar o Google ADK para construir e executar o agente e o Google Cloud Vision `DOCUMENT_TEXT_DETECTION` como backend de OCR, chamado pelo servidor MCP de OCR. O ADK é a camada do agente; o Vision é o serviço de reconhecimento de texto. A interface do MCP continua recebendo o `image_id` e retornando somente `{"exames": [...]}`.

**Motivos:**

- Alinhamento com a stack Google Cloud usada pela empresa e com o Google ADK solicitado no desafio.
- O Google Cloud Vision documenta português (`pt`) como idioma suportado, incluindo a variante brasileira.
- Para chamadas síncronas de OCR, o Google documenta que a imagem é processada em memória e não persistida em disco. Também declara que o conteúdo é usado para prestar o serviço, não para treinar ou melhorar o Vision.
- Essas garantias documentadas oferecem uma base clara para a decisão de arquitetura deste desafio.

**Limite de confiança e tratamento de dados:** a imagem continua sendo enviada ao Google Cloud Vision para processamento; portanto, `tmpfs` reduz a retenção local, mas não significa que os bytes permaneçam apenas nos containers. O fluxo escolhido usará a operação síncrona de anotação de imagem. A documentação informa que certos metadados da solicitação, como horário e tamanho, podem ser registrados temporariamente. A saída para o agente seguirá limitada aos exames extraídos, após o mascaramento de PII no MCP de OCR.

**Entrada de imagem aprovada:** PNG e JPG, com tamanho máximo inicial de 10 MB. O CLI valida o tamanho e o formato real do arquivo antes de armazená-lo; o OCR verifica se consegue abrir e processar a imagem. Arquivos PDF e outros formatos ficam fora deste escopo inicial.

**Alternativa não selecionada:** GLM-OCR fica como possível alternativa futura. A documentação consultada não lista português explicitamente, e os termos de uso e o tratamento de dados para este fluxo relacionado à saúde precisam de confirmação antes de considerar seu uso. A avaliação poderá ser reaberta se esses pontos forem esclarecidos e um teste com pedidos em português mostrar benefício frente ao Vision.

### Referências consultadas

- [Docker — tmpfs mounts](https://docs.docker.com/engine/storage/tmpfs/): armazenamento temporário em memória e observação de que o swap pode afetar a persistência.
- [Docker Compose — volumes](https://docs.docker.com/reference/compose-file/volumes/): compartilhamento de volumes entre serviços e opções de montagem.
- [Model Context Protocol — especificação de ferramentas](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-06-18/schema.mdx): diferencia resultado de execução da tool com `isError` de erros do protocolo JSON-RPC.
- [MCP Python SDK — tratamento de erros](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/handling-errors.md): exemplos de como erros lançados pelo handler são expostos como erro de tool ou de protocolo no cliente.
- [Google Cloud Storage — Signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signed-urls): permissões temporárias para um objeto específico; quem possui a URL pode usá-la enquanto válida.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): nomes gerados pela aplicação, armazenamento segregado e controle de leitura.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): um ID complexo não substitui a autorização por objeto.
- [Google AI for Developers — ADK](https://google.github.io/adk-docs/): documentação oficial do Google Agent Development Kit.
- [Cloud Vision — OCR](https://docs.cloud.google.com/vision/docs/ocr): diferença entre detecção geral de texto e detecção de texto denso em documentos.
- [Cloud Vision — idiomas OCR](https://docs.cloud.google.com/vision/docs/languages): idiomas suportados, incluindo português brasileiro.
- [Cloud Vision — uso de dados](https://docs.cloud.google.com/vision/docs/data-usage): tratamento de conteúdo em chamadas síncronas, treinamento e metadados temporários.
- [Cloud Vision — preços](https://cloud.google.com/vision/pricing): preço por imagem para os recursos de OCR.
- [Z.AI — GLM-OCR](https://docs.z.ai/guides/vlm/glm-ocr): formatos, limite de tamanho, idiomas declarados e benchmark publicado pelo fornecedor.
- [Z.AI — termos de uso](https://chat.z.ai/legal-agreement/terms-of-service): termos aplicáveis a API e restrições de uso a confirmar para este cenário.
- [GLM-OCR Technical Report](https://arxiv.org/abs/2603.10910): relatório técnico e benchmarks reportados pelos autores do GLM-OCR.

## Recepção e armazenamento temporário — componente implementado

O componente interno `TemporaryImageStore` valida o conteúdo real da imagem, aceita PNG/JPG até 10 MB, grava os bytes sob um UUID sem extensão e resolve e remove arquivos somente por UUID canônico. A gravação usa arquivo temporário e promoção atômica; falhas não deixam artefatos parciais. Ele ainda não está conectado ao comando de atendimento e não expõe um comando público para armazenar imagens isoladamente. Os testes unitários do componente cobrem formatos, conteúdo inválido, limite configurável, UUID, resolução, exclusão, limpeza e falha durante promoção atômica.

O `compose.yaml` mantém o serviço `assistant-runtime` em execução e monta o volume `image-storage` em `tmpfs` (64 MiB), gravável pelo runtime. O container segue como usuário não root (UID 10001). Quando o OCR for implementado, ele deverá montar o volume temporário somente para leitura. A integração futura enviará os bytes da imagem ao runtime e usará o `image_id` internamente; o fluxo de atendimento será responsável por remover a imagem em `finally`. Uma gravação remove arquivos UUID com mais de 30 minutos. A primeira versão assume um atendimento por vez.

## Próximos passos acordados

1. [ ] Revisar `docs/phase2-spec.md` e fechar as decisões pendentes antes de aprová-la.
2. [ ] Após aprovar a especificação, implementar a fatia OCR de ponta a ponta: imagem pelo `process --path`, armazenamento temporário, OCR e exames apresentados no CLI.

## Princípios herdados da Fase 1

- Manter a especificação do agente restrita a valores e tools permitidos; não aceitar código, endpoints ou credenciais arbitrárias no JSON.
- Preservar a geração determinística e os testes locais reproduzíveis.
- Usar modelo determinístico e `InMemoryRunner` nos testes sem chamadas externas; documentar separadamente qualquer teste que use Gemini real.
- Validar cada entregável e sua documentação antes de avançar para a subfase seguinte.

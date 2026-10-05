# Plano da Fase 2

**Estado:** a aprovação formal do escopo geral em `phase2-spec.md` continua em revisão. A subfase 2.1 está implementada e validada: as duas execuções ponta a ponta com Cloud Vision real e modelo determinístico passaram, assim como as suítes automatizadas, análise estática, cobertura, locks e configuração do Compose. A revisão local do diff não encontrou pendências de aderência à especificação.

**Regra de trabalho:** revisar a especificação e os contratos antes de implementar cada componente; avançar uma etapa por vez, validar o entregável e documentar as decisões antes de prosseguir.

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
- [x] Definir a política de concorrência: somente um processamento pode estar ativo por vez; a subfase 2.1 implementou e testou o lock entre processos.
- [x] Definir que credenciais ficam fora da imagem Docker e do Git; a subfase 2.1 configurou a injeção em tempo de execução a partir do `.env` ignorado pelo Git.
- [x] Registrar as regras de validação de PNG/JPG, limite de 10 MB, uso do UUID interno e limpeza em sucesso ou falha.
- [x] Registrar o limite de privacidade: o agente recebe o `image_id`, o servidor OCR verifica os valores de saída com uma barreira local de PII e a imagem bruta não entra no contexto do LLM. O detector reduz risco, sem garantir cobertura universal.
- [x] Definir a composição do agente gerado nesta fatia: tools controladas de stub para catálogo e agendamento, sem chamadas externas; instruções limitadas ao OCR.
- [x] Implementar o componente reutilizável `TemporaryImageStore`, com validação, gravação atômica sob UUID, exclusão e limpeza de órfãos; o OCR resolve o UUID diretamente como nome do arquivo no volume compartilhado.
- [x] Configurar a base de desenvolvimento em Docker: dependências `dev`, workspace montado em `/workspace`, runtime não root e volume `tmpfs`; `docker compose config` foi validado.
- [x] Organizar o runtime atual como app Python independente, com build, dependências, testes e documentação próprios; manter os materiais da POC na raiz.
- [x] Atualizar o system design e manter rastreabilidade entre requisitos, componentes e testes.
- [ ] Revisar e aprovar a especificação de escopo; as decisões operacionais ficam planejadas para a subfase 2.1.

**Entregável:** `docs/phase2-spec.md` revisada e aprovada, com o escopo e os critérios da primeira fatia de implementação.

### 2.1 — OCR: imagem recebida até exames no CLI

**Objetivo:** entregar o primeiro fluxo utilizável de ponta a ponta: receber uma imagem pelo comando de runtime, executar o caminho OCR previsto e apresentar a lista de exames no CLI.

#### Etapa 1 — Estrutura e contrato do servidor

- [x] Criar `apps/ocr_mcp` como app Python independente, com pacote `carrefour_ocr_mcp`, dependência MCP 2.x, lockfile e testes próprios.
- [x] Expor a tool `extract_exams(image_id)`: validar UUID canônico, resolver a imagem somente no diretório configurado e passar seus bytes a um extrator injetado.
- [x] Manter o resultado estruturado no contrato `{"exams": [...]}` e testar descoberta e chamada pela interface `Client` do SDK MCP em memória, sem rede.
- [x] Testar UUID inválido e imagem ausente; nesses casos o extrator não é chamado e a resposta de erro não repete o valor recebido.
- [x] Executar testes, análise estática e build isolado do pacote.

#### Etapa 2 — Cliente Google Cloud Vision

- [x] Implementar cliente REST assíncrono para `DOCUMENT_TEXT_DETECTION`, recebendo `GOOGLE_CLOUD_VISION_API_KEY` do ambiente de execução e enviando-a no header `X-Goog-Api-Key`.
- [x] Usar timeout inicial de 60 segundos e não repetir chamadas automaticamente; medir chamadas reais antes de rever esses parâmetros.
- [x] Testar payload, autenticação, timeout, resposta inválida e erros HTTP com cliente HTTP simulado, sem chamadas à nuvem.

#### Nota para revisão futura — erros e política de retry

A documentação consultada fornece sinais úteis para classificar falhas, mas não estabelece uma matriz de retry específica para o Cloud Vision. A resposta de status tem código e detalhes estruturados; a orientação geral do Google Cloud é tomar decisões pelo código/detalhes, sem depender do texto da mensagem, que pode mudar.

| Sinal observado | Tratamento a avaliar depois das chamadas reais |
|---|---|
| Requisição inválida (`400`) ou credenciais/permissões incorretas (`401`/`403`) | Não repetir automaticamente; corrigir a requisição ou a configuração. |
| Timeout, desconexão de rede ou serviço temporariamente indisponível (`503`) | Candidato a uma tentativa adicional limitada, com espera e prazo total definidos. Confirmar primeiro o comportamento observado e o impacto no fluxo. |
| Limite de chamadas (`429` / `RESOURCE_EXHAUSTED`) | Não repetir imediatamente. Verificar os detalhes estruturados para distinguir limite temporário por janela de quota esgotada; só o primeiro pode se beneficiar de espera e nova tentativa. |
| Campo `error` dentro da resposta de uma imagem | Não assumir que a resposta está totalmente vazia: o Vision documenta que pode haver anotações preenchidas junto com `error`. Definir se o OCR rejeita resultado parcial ou se há um tratamento específico antes de considerar retry. |

Uma repetição é uma nova chamada de anotação; a decisão futura deve considerar latência, quota e possível custo duplicado. **Decisão vigente:** manter timeout de 60 segundos e nenhuma repetição automática. Rever esta nota após a validação ponta a ponta com Vision real, sem tratar a lista acima como política já implementada.

Referências para a revisão: [modelo de status do Cloud Vision](https://docs.cloud.google.com/vision/docs/reference/rest/v1/Status), [erros por imagem na resposta do Vision](https://docs.cloud.google.com/vision/docs/reference/rest/v1/AnnotateImageResponse), [orientação geral para erros de APIs Google Cloud](https://docs.cloud.google.com/apis/docs/troubleshooting) e [quotas do Cloud Vision](https://docs.cloud.google.com/vision/quotas).

#### Etapa 3 — Extração e classificação local

- [x] Organizar texto e coordenadas devolvidos pelo Vision e reconhecer somente os dois layouts sintéticos de referência.
- [x] Usar Pillow para classificar cada checkbox como selecionado, não selecionado ou ambíguo; não inferir uma marca incerta.
- [x] Confirmar os cinco exames da lista numerada e os seis marcados no formulário, incluindo testes de marca parcial e layout não reconhecido.
- [x] Limitar a resposta aos nomes dos exames e não persistir nem registrar o texto OCR integral.

#### Etapa 4 — Transporte SSE e Docker Compose

- [x] Expor a tool pelo transporte HTTP+SSE exigido no desafio e manter o serviço na rede interna do Compose, sem publicar a porta no host.
- [x] Montar o volume tmpfs compartilhado como somente leitura no container OCR e verificar leitura/escrita entre os containers.
- [x] Testar descoberta e chamada com Vision simulado tanto em memória como pelo transporte SSE real.

#### Etapa 5 — Integração com runtime e agente

- [x] Implementar `process --path <nome-do-arquivo>` no runtime; aceitar somente o nome dentro de `/workspace/tests/fixtures/images` e rejeitar caminhos e links simbólicos.
- [x] Validar e gravar a imagem no `TemporaryImageStore`, chamar o agente via ADK/MCP SSE e apagar a cópia em `finally`.
- [x] Usar o modelo da especificação em execução normal e injetar um modelo determinístico nos testes, sem criar um modo de teste público no CLI.
- [x] Capturar e serializar `structuredContent` da resposta de `extract_exams`, sem depender do texto final do modelo ou fazer uma segunda chamada Gemini.
- [x] Fornecer stubs controlados para catálogo e agendamento, expor somente `extract_exams` do servidor OCR e impor um processamento por vez com lock entre processos.
- [x] Validar resultados, mensagens sanitizadas, limpeza em sucesso e erro, imagem inválida, resposta ausente/malformada e falha do MCP em testes sem serviços externos.
- [x] Injetar `GOOGLE_API_KEY` no runtime e `GOOGLE_CLOUD_VISION_API_KEY` no OCR somente em execução, fora das imagens Docker e do Git.
- [x] Definir timeout inicial de 5 segundos para conectar ao MCP, 75 segundos para aguardar respostas SSE e 90 segundos para o fluxo no ADK; não repetir chamadas automaticamente.
- [x] Retornar revisão manual com status distinto e exames ambíguos; usar código de saída 2 para revisão manual, 0 para sucesso e 1 para falhas técnicas.

**Resultado:** o fluxo local usa `InMemoryRunner` do ADK com a conexão SSE e captura a resposta estruturada da tool. A bateria automatizada usa um servidor MCP local e modelo determinístico; não chama Gemini nem Cloud Vision. O Compose desativa a descoberta de certificados mTLS Google porque esta conexão MCP usa HTTP interno sem autenticação.

**Timeouts observados:** o cliente REST do Vision mantém seu limite de 60 segundos. O runtime permite 5 segundos para descoberta/conexão MCP, 75 segundos de leitura SSE e 90 segundos para o turno ADK. Não há retries automáticos. As duas execuções reais terminaram em menos de cinco segundos no fluxo completo; como esse tempo não isola a latência do Vision e representa apenas duas amostras, mantemos os limites e a política sem retries.

#### Etapa 6 — Validação ponta a ponta com Vision real

- [x] Criar harness E2E manual e optativo no runtime, com modelo determinístico e servidor OCR/Vision reais.
- [x] Executar explicitamente, fora do CI, o fluxo Compose nas duas imagens usando Cloud Vision real e modelo determinístico; não chamar Gemini.
- [x] Conferir os exames e o JSON do CLI; a revisão visual confirmou a seleção esperada. O harness verificou os marcadores sintéticos de PII na saída e nos erros, a integridade do original e a remoção da cópia temporária. A inspeção manual dos logs do OCR no Compose encontrou apenas metadados de transporte/status, sem conteúdo da imagem ou dos exames.
- [x] Verificar a rejeição de um segundo processamento simultâneo no teste unitário de `ProcessingLock`, sem fazer uma segunda chamada real ao Vision.
- [x] Registrar a duração ponta a ponta e manter os timeouts e a política sem retries; as medições não isolam o tempo de resposta do Vision.
- [x] Rever o tratamento de marcações ambíguas: as duas imagens não produziram casos ambíguos; permanece a resposta `review_required` para classificações incertas, coberta pelos testes locais.

**Critério de aceite:** `process --path <nome>` executado via Docker Compose processa uma imagem da pasta montada, apresenta os exames extraídos no CLI e remove a imagem temporária ao concluir. Erros não exibem PII nem deixam a imagem armazenada após a finalização.

**Registro E2E (2026-10-04):** `exam_request_pt_br.png` retornou cinco exames em 4,47 s; `exam_request_pt_br_simplified.png` retornou os seis exames marcados em 4,57 s. O usuário confirmou visualmente que a seleção corresponde às imagens. O E2E verificou que o modelo determinístico provocou uma única chamada à tool, que o prompt contém apenas o UUID, que a cópia temporária foi removida, que o arquivo original permaneceu intacto e que os marcadores sintéticos de PII não apareceram na saída ou nos erros. O Cloud Vision foi real; Gemini não foi chamado.

**Nota de custo da validação:** a primeira tentativa em cada fixture usou uma imagem Docker desatualizada e chegou a chamar o Vision antes de falhar em uma asserção obsoleta do teste. Após reconstruir o runtime, as duas execuções passaram. As quatro tentativas desta sequência fizeram quatro chamadas ao Vision; esse número se refere a estes comandos, não ao histórico completo do container. Não repetir essas execuções sem necessidade.

### 2.1.1 — Barreira local de PII no OCR

**Objetivo:** reduzir a chance de nomes, documentos ou contatos identificados como exames serem devolvidos pela tool e chegarem ao agente ou ao RAG.

- [x] Inicializar Presidio dentro do container OCR com spaCy local em português; a falha de inicialização encerra o serviço com evento e mensagem sanitizados.
- [x] Analisar todos os valores que poderiam sair em `exams` e `ambiguous_exams`, sem enviar o texto OCR a um serviço de detecção externo.
- [x] Configurar recognizers locais para nomes, e-mail, telefone brasileiro, CPF, CNPJ numérico e alfanumérico, RG e CNS.
- [x] Ao detectar PII, suprimir todo o resultado e retornar somente `{"status":"review_required","reason":"sensitive_data_detected"}`; não expor exames não sinalizados nem mascarar trechos.
- [x] Se a análise falhar, interromper a tool com erro técnico sanitizado; não liberar o resultado original.
- [x] Cobrir categorias com dados sintéticos, regressões das duas fixtures e a fronteira MCP/runtime; nenhuma suíte chama Vision, Gemini ou Sensitive Data Protection.
- [x] Atualizar especificação, system design e notas para o vídeo para descrever a implementação e seus limites.

**Limite da evidência:** os testes cobrem as categorias e exemplos sintéticos listados. Presidio, spaCy e recognizers próprios reduzem o risco, mas não garantem detecção completa de PII em texto OCR imperfeito ou formatos não previstos. Sensitive Data Protection continua sendo alternativa futura; não é chamado nesta etapa.

**Regra conservadora para documentos:** CPF e CNPJ são detectados pelo formato, mesmo quando o checksum não confere. Um erro de leitura OCR pode alterar um dígito válido; exigir checksum permitiria que um identificador real passasse sem bloqueio. O custo possível é revisão extra para strings numéricas que apenas se parecem com documentos.

**Resultado:** o detector local foi inicializado e os testes unitários cobriram os identificadores brasileiros configurados, e-mail, telefone e nomes em português. Os dois layouts de referência passam sem falso positivo. A resposta MCP e o CLI preservam somente o estado genérico de revisão quando um valor é sinalizado.

### POC concluída: extração de exames nos dois layouts sintéticos

**Objetivo da validação:** conferir se um fluxo com Cloud Vision OCR e análise local consegue retornar os exames corretos em duas imagens de demonstração: uma lista numerada sem caixas de seleção e um formulário com checkboxes.

**Resultado:** a validação funcionou para as duas amostras.

- `exam_request_pt_br.png`: a lista numerada não tem checkboxes e instrui a realizar os exames listados. O fluxo retornou os cinco itens: Hemograma completo, Glicemia de jejum, Hemoglobina glicada (HbA1c), Colesterol total e frações, e TSH (hormônio tireoestimulante).
- `exam_request_pt_br_simplified.png`: o formulário tem dez checkboxes. O OCR localizou códigos e textos; a análise local de pixels identificou seis marcações: EX-101, EX-102, EX-104, EX-106, EX-109 e EX-110.
- Os resultados foram conferidos visualmente contra as imagens. Não foi chamado Gemini, GLM ou outro LLM: Cloud Vision foi usado para OCR; a classificação dos X foi feita localmente.

**Limite da evidência:** são duas amostras sintéticas, com layouts conhecidos. A POC demonstra viabilidade para esses formatos; não valida formulários arbitrários, manuscritos ou outros tipos de marca. Na lista sem caixas, retornar todos depende da instrução contextual de que os exames listados devem ser realizados.

**Artefatos da POC:** os scripts de exploração e o relatório são mantidos localmente como referência e não fazem parte do repositório. Os resultados e limites foram resumidos acima; a subfase 2.1 reproduziu os dois casos nos testes locais e no E2E manual com Cloud Vision real.

**Ordem de implementação acordada:** a recepção e o armazenamento temporário local precederam o servidor/tool de OCR. Essa ordem foi seguida: `TemporaryImageStore` recebe a cópia em `tmpfs` sob UUID e `process` envia somente esse ID ao servidor OCR. O fluxo está implementado e foi validado na subfase 2.1; veja a seção “Recepção e armazenamento temporário de imagem”.

### 2.2 — Catálogo de exames e busca (RAG via MCP)

**Objetivo:** receber em lote os nomes de exames retornados pelo OCR, resolver cada nome no catálogo fictício e devolver códigos somente quando a correspondência for confiável. A capacidade será exposta ao agente por um servidor MCP usando SSE; esta subfase não depende da API de agendamento.

#### Etapa 1 — Especificar catálogo e contrato da tool

- [x] Definir o JSON como fonte versionada do catálogo, empacotado em `apps/rag_mcp`, com 122 registros de exames e códigos fictícios únicos, nomes canônicos e aliases aprovados. O Git versiona o arquivo; o contrato não adiciona `schema_version`.
- [x] Implementar a validação estrita do catálogo: estrutura e campos obrigatórios, mínimo de 100 exames, formato e unicidade de códigos, nomes canônicos únicos e aliases não vazios nem repetidos dentro do mesmo exame. Aliases compartilhados entre exames distintos são permitidos para que a busca possa sinalizar ambiguidade.
- [x] Definir o contrato da tool em lote `search_exams(exam_names)`, com limite de 50 nomes e 160 caracteres por nome. A resposta tem um item por nome normalizado distinto e estados `resolved`, `ambiguous`, `review_required` ou `not_found`.
- [x] Definir a deduplicação após normalização e a ordem da primeira ocorrência. `input_indices` relaciona cada resultado a todas as posições originais da consulta correspondente.
- [x] Definir que somente respostas `resolved` incluem código. Respostas ambíguas ou aproximadas incluem nomes candidatos sem códigos; `not_found` não inventa código. A API de agendamento recebe apenas exames resolvidos/confirmados.

#### Etapa 2 — Construir índice e recuperação

- [x] Normalizar nome canônico, aliases e consultas com regras idênticas para caixa, acentos, pontuação e espaços, preservando qualificadores clínicos.
- [x] Construir na inicialização um índice em memória no qual cada termo normalizado aponta para um ou mais exames.
- [x] Implementar busca exata primeiro, cobrindo nomes canônicos e aliases; se o termo exato apontar para múltiplos exames, retornar `ambiguous`.
- [x] Quando não houver correspondência exata, usar RapidFuzz `fuzz.ratio` para comparar a consulta com os termos do índice e ordenar até três candidatos por similaridade, com desempate por código.
- [x] Manter a busca aproximada como geração de candidatos: o corte calibrado em 80 pontos produz `review_required`, abaixo dele retorna `not_found`, e nenhum resultado aproximado recebe código.
- [x] Retornar o método de correspondência e os candidatos necessários para explicar a decisão, sem registrar nomes de exames em logs operacionais.

**Cobertura automatizada desta etapa:** teste de resolução individual dos 122 nomes canônicos e 105 aliases; 11 nomes vindos dos dois layouts OCR (7 códigos distintos); 40 casos rotulados em `apps/rag_mcp/tests/fixtures/retrieval_cases.json`; colisão de alias, deduplicação, ordenação determinística e preservação de qualificadores. Nos casos sintéticos, o menor score dos typos foi 83,7 e o maior dos nomes fora do catálogo foi 75,0; o corte 80 deixa margens de 3,7 e 5 pontos para esses casos rotulados. Scores são semelhança textual, não probabilidades, e este conjunto pequeno não representa pedidos clínicos gerais.

#### Etapa 3 — Avaliar a recuperação

- [x] Montar casos de referência a partir dos exames identificados nas duas imagens de teste e associar cada consulta ao código esperado.
- [x] Avaliar a recuperação separadamente do OCR para distinguir erros de extração de erros de catálogo.
- [x] Cobrir correspondência exata, alias, erro ortográfico, alias compartilhado/ambiguidade e exame ausente; incluir variações sintéticas de grafia para medir o comportamento aproximado.
- [x] Medir os casos rotulados e calibrar o corte sem presumir que uma pontuação de similaridade seja uma probabilidade: 227/227 etiquetas exatas, 11/11 ocorrências OCR corretas, 12/12 typos com o alvo no top 3, 8/8 OOV como `not_found` e 8/8 variações de qualificadores sem resolução automática.
- [x] Executar testes sem depender de LLM, Cloud Vision ou API de agendamento.

**Limite da avaliação:** os resultados são regressões de um catálogo e 40 casos sintéticos pequenos; não representam pedidos clínicos arbitrários nem demonstram cobertura geral de OCR. O corte 80 deve ser revisto se o catálogo ou a distribuição das consultas mudar.

#### Etapa 4 — Expor e documentar o MCP RAG

- [x] Preparar a fronteira MCP em memória com a tool `search_exams`, dependência de logging compartilhada e eventos JSON seguros para inicialização do catálogo e conclusão, rejeição ou falha da busca.
- [x] Testar eventos via cliente MCP em memória, incluindo resultados ambíguos, aproximados e não encontrados; confirmar duração, severidade, códigos técnicos e ausência de consultas, exames e mensagens brutas nos logs.
- [x] Implementar o servidor MCP como app independente e expor a busca pelo transporte SSE exigido pelo desafio.
- [x] Testar descoberta e chamada da tool pelo transporte SSE, incluindo resultados resolvidos, aproximados, falhas de entrada e rejeição de Host não permitido.
- [x] Adicionar o serviço ao Docker Compose sem publicar sua porta no host; limitar a proteção DNS rebinding ao host `rag-mcp:8000`.
- [x] Documentar o formato do catálogo, contrato de entrada e saída, estratégia de recuperação, avaliação, transporte, logs e comandos para iniciar e verificar o servidor.

**Resultado:** o RAG inicia como app independente, carrega o catálogo uma vez e expõe `search_exams` em `http://rag-mcp:8000/sse` na rede interna do Compose. O teste SSE usa um servidor local com cliente MCP real e valida descoberta, resposta estruturada, rejeição de entrada e host não permitido. Access logs HTTP ficam desativados; os logs JSON da aplicação permanecem em `stderr` e não contêm consultas nem dados de exames. O runtime ainda não chama o RAG.

**Entrega candidata:** catálogo fictício validado e busca em lote disponível por MCP SSE, com correspondência exata e aproximada avaliadas e resultados que não escolhem códigos de forma ambígua.

### 2.3 — API de agendamento

**Objetivo:** disponibilizar uma API fictícia de agendamento, persistente e testável sem o agente. A primeira versão recebe os exames resolvidos, reconcilia-os com a agenda do usuário autenticado e escolhe horários livres automaticamente.

#### Decisões de escopo para a primeira versão

- [x] Usar SQLite para persistir agendamentos entre chamadas e reinícios do container, guardando o arquivo em volume persistente do Compose.
- [x] Organizar a API em camadas `api`, `application`, `domain` e `infrastructure` quando cada camada tiver responsabilidade própria; evitar abstrações sem necessidade concreta.
- [x] Começar com um único `POST /appointments`; a API aloca os horários e devolve a confirmação na mesma chamada. Não expor endpoint de disponibilidade nesta entrega.
- [x] Tratar `appointment_booking` como a capacidade lógica configurada na especificação do agente. A tool do runtime chama o endpoint da API; a especificação não precisa espelhar cada rota HTTP.
- [x] Obter a identidade do usuário do claim `sub` de um JWT validado pela API; não aceitar `user_id` como identidade confiável no corpo da requisição.
- [x] Fazer reconciliação incremental por usuário: preservar exames já agendados e horários existentes; agendar somente os exames novos e evitar duplicatas em chamadas repetidas.
- [x] Considerar os horários globalmente exclusivos: um horário já reservado não pode ser atribuído a outro usuário; selecionar outro horário livre.
- [x] Usar transações e restrições no SQLite para garantir que chamadas simultâneas não confirmem duas reservas para o mesmo horário.

#### Contrato, implementação e validação

- [x] Definir o contrato de `POST /appointments`: `Authorization: Bearer <JWT>` e corpo `{"exam_codes": [...]}` sem `user_id`; códigos repetidos são deduplicados preservando a ordem.
- [x] Definir a resposta agrupada por agendamento: `status` (`completed`, `partial` ou `no_availability`), `already_scheduled`, `newly_scheduled` e `not_scheduled`. Cada agendamento inclui `appointment_id`, `scheduled_at` em ISO 8601 com offset e `exam_codes`; cada exame não agendado inclui o motivo `no_availability`.
- [x] Tratar falta de horário como resultado de negócio HTTP `200`; usar `401` para credencial ausente/inválida/expirada, `422` para entrada inválida e `503` para indisponibilidade técnica.
- [x] Fornecer emissor local de JWT HS256 com expiração curta, desabilitado por padrão e habilitado somente no Compose de desenvolvimento; documentar que não substitui um provedor de identidade.
- [x] Definir os horários fictícios e determinísticos: dias úteis, 09:00–17:00, slots de 30 minutos, fuso `America/Sao_Paulo` e janela configurável de 30 dias.
- [x] Implementar entidades/regras de agendamento, caso de uso de reconciliação, repositório SQLAlchemy/SQLite, transação de alocação e rota FastAPI.
- [x] Gerenciar `Engine` e `sessionmaker` no lifespan FastAPI e injetar uma `Session` por request com `Depends`; fechar a sessão antes da resposta.
- [x] Preservar a alocação atômica com `BEGIN IMMEDIATE`, `UNIQUE` no slot global e chave estrangeira entre agendamentos e exames.
- [x] Testar sucesso autenticado, token ausente/malformado/expirado e rejeição de campos extras; a identidade usada vem do `sub` verificado.
- [x] Cobrir chamadas repetidas, exames previamente agendados, exames novos agrupados em um horário, usuários diferentes e exclusividade global dos horários.
- [x] Cobrir falta de horário, resultado parcial, persistência após reinício, concorrência, falha de escrita e rollback da transação.
- [x] Validar resposta HTTP sanitizada e logs sem subject, JWT, códigos de exame ou mensagens brutas do SQLite.
- [x] Documentar e testar os esquemas de autenticação, erros e respostas no Swagger `/docs` e em `/openapi.json`.
- [x] Adicionar o serviço Compose independente com volumes persistentes e targets de desenvolvimento e runtime.
- [x] Documentar contrato, configuração, DI, SQLite, emissor local de token, logs, Swagger e comandos nos READMEs da raiz e do app.

#### Reavaliação após a primeira entrega

- [ ] Validar se a experiência precisa oferecer opções de horário para escolha explícita do usuário. Se houver benefício, especificar endpoints separados para propor e confirmar uma agenda antes de implementá-los.
- [ ] Se a proposta tiver de garantir que os horários continuem disponíveis enquanto o usuário escolhe, avaliar reservas temporárias com expiração (*holds*) e a liberação dos horários não escolhidos. Não manter transações ou locks do SQLite abertos durante a espera do usuário.

**Estado da implementação:** o serviço independente está implementado com DI por request, persistência SQLAlchemy/SQLite, JWT de demonstração restrito ao ambiente local, Swagger e logs JSON sanitizados. A suíte contém 42 testes e mede 96,0% de cobertura combinada no último relatório `pytest-cov` (Python 3.11). A revisão do usuário ainda precede os testes de integração com runtime, RAG e OCR.

**Entrega candidata:** API FastAPI com `POST /appointments`, SQLite persistente, identidade JWT, reconciliação idempotente por usuário e alocação globalmente exclusiva, testável sem o agente.

### 2.4 — Verificação transversal de privacidade

> A barreira local do OCR, entregue na subfase 2.1.1, suprime o resultado quando reconhece uma das categorias configuradas. Esta etapa verifica que os outros componentes respeitam esse limite e não reintroduzem exposição ou persistência desnecessária de PII; ela não presume que o detector reconheça toda PII.

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
- [ ] Compor no Docker Compose os serviços já implementados nas subfases anteriores para a demonstração completa; o serviço OCR e seu mount somente leitura são entregues na subfase 2.1.
- [ ] Executar o fluxo completo com serviços locais após a entrega de OCR, catálogo e agendamento.
- [ ] Documentar como iniciar e verificar o ambiente completo.
- [ ] Avaliar teste opcional com Gemini real, credenciais configuradas e chamadas externas.

**Entrega candidata:** demonstração local reproduzível; integração com modelo real claramente identificada como opcional ou obrigatória conforme o desafio.

### 2.7 — Observabilidade do fluxo

**Objetivo:** tornar uma execução rastreável entre o CLI/runtime, o transporte MCP por SSE, o serviço OCR e a chamada ao Cloud Vision, sem registrar imagem, dados pessoais ou conteúdo clínico.

**Decisão aprovada para o ambiente local:** usar OpenTelemetry como padrão de instrumentação e um OpenTelemetry Collector como ponto de recepção/exportação OTLP. Para visualizar e armazenar localmente os sinais, usar OpenObserve OSS em modo single-node. O Compose terá esses componentes como serviços opcionais do ambiente de desenvolvimento; a interface web ficará acessível somente pelo host local. A persistência de telemetria usará volume próprio, separado do `tmpfs` de imagens. Esta decisão descreve a stack local do projeto, não um dimensionamento de produção. Registrar e revisar a licença AGPL-3.0 do OpenObserve antes de qualquer distribuição do stack.

**Princípios de instrumentação:**

- Manter o JSON de resultado como única saída de sucesso em `stdout`; logs operacionais estruturados seguem para `stderr` e para o pipeline de telemetria.
- Fazer a execução continuar se o Collector ou o OpenObserve estiver indisponível; telemetria não pode impedir nem alterar o processamento.
- Correlacionar logs e spans pelo `trace_id`, sem usar imagem, nome de arquivo ou dado do paciente como identificador.
- Aplicar os 5 Ws como perguntas para cada evento: quando (`timestamp`), quem (`service`), o quê (`event`), onde (`component`) e resultado/motivo (`outcome`, `error_code`, `error_type`). O `level` indica severidade.
- Instrumentar fronteiras importantes do fluxo; não adicionar eventos a cada função ou iteração. Cada limite registra apenas o contexto operacional que sua camada conhece.
- Aplicar allowlist de atributos. Não registrar bytes ou caminho da imagem, `image_id`, nome/resultado de exame, texto OCR, prompt, chave ou cabeçalho de autenticação, payload da Vision, nem resposta bruta de erro que possa conter esses dados.
- Registrar apenas metadados operacionais necessários, como componente, etapa, resultado, duração, classe/código técnico de erro e contagem agregada de exames quando essa contagem não permitir reconstruir conteúdo clínico.
- Sanitizar mensagens de erro na fronteira do CLI; detalhes internos devem ser classificados e filtrados antes de serem exportados.

#### Etapas propostas

- [x] Definir o catálogo inicial de eventos de log, níveis, códigos de erro e allowlist de atributos.
- [x] Padronizar logs JSON nos dois apps. Os registros operacionais são emitidos em `stderr`, preservando `stdout` exclusivamente para o JSON de resultado do CLI. `docker compose exec` encaminha ambos os canais ao terminal; a retenção por `docker compose logs` vale para o processo principal do container, não deve ser presumida para comandos `exec`.
- [x] Revisar os eventos com os 5 Ws, incluir `component`, classificar falhas com códigos estáveis, medir duração das etapas principais e testar que conteúdo livre e dados sensíveis não entram nos logs.
- [ ] Instrumentar o runtime com um span raiz de `process` e spans para validação/leitura da imagem, armazenamento, execução ADK, chamada MCP e limpeza. Registrar resultado e duração sem anexar dados clínicos.
- [ ] Instrumentar o OCR com spans para entrada da tool, resolução por UUID, chamada HTTPX ao Vision, decodificação e extração local. Instrumentar as requisições Starlette e HTTPX onde isso não duplicar spans; verificar a propagação do contexto pelo transporte SSE do SDK MCP.
- [ ] Se o SDK ou o transporte SSE não propagar contexto de trace entre cliente e servidor, escolher e documentar uma correlação segura entre serviços antes de implementar um identificador alternativo; não reutilizar o `image_id` para isso.
- [ ] Adicionar OpenTelemetry Collector e OpenObserve OSS ao Compose local, com configuração OTLP, persistência separada das imagens e publicação da UI apenas em loopback. Segredos e credenciais de acesso à UI ficam em ambiente local, fora da imagem e do Git.
- [ ] Testar instrumentação com exporters em memória e sem depender do backend. Cobrir sucesso, falhas de Vision/MCP, limpeza e indisponibilidade do Collector; confirmar spans pai/filho ou a correlação alternativa aprovada.
- [ ] Fazer uma execução manual via Compose e conferir no backend os logs e spans de ponta a ponta. Incluir marcadores sintéticos de PII e verificar que nenhum aparece em logs, atributos, eventos ou exceções exportadas.
- [ ] Documentar como subir, acessar, desligar e limpar a stack local, incluindo retenção e remoção do volume de telemetria.

#### Catálogo local de eventos

| Evento | Emissor / componente | Nível | Campos específicos |
|---|---|---|---|
| `process.started` | Runtime / `process_service` | INFO | — |
| `process.lock.rejected` | Runtime / `processing_lock` | WARNING | `error_code`, `error_type` |
| `process.image.stored` | Runtime / `temporary_image_store` | INFO | `duration_ms` |
| `process.ocr.started` | Runtime / `ocr_executor` | INFO | — |
| `process.ocr.completed` | Runtime / `ocr_executor` | INFO ou WARNING | `duration_ms`, `outcome` |
| `process.image_cleanup.completed` | Runtime / `temporary_image_store` | INFO | `outcome` |
| `process.image_cleanup.failed` | Runtime / `temporary_image_store` | ERROR | `error_code`, `error_type` |
| `process.completed` | Runtime / `process_service` | INFO ou WARNING | `duration_ms`, `outcome` |
| `process.failed` | Runtime / componente da falha | WARNING ou ERROR | `duration_ms`, `error_code`, `error_type` |
| `process.configuration_failed` | Runtime / `cli` | ERROR | `error_code` |
| `ocr.configuration.failed` | OCR MCP / componente de configuração | ERROR | `error_code`, `error_type` |
| `ocr.tool.started` | OCR MCP / `mcp_tool` | INFO | — |
| `ocr.image.resolved` | OCR MCP / `image_access` | INFO | `duration_ms` |
| `ocr.extraction.started` | OCR MCP / `exam_extractor` | INFO | — |
| `ocr.extraction.completed` | OCR MCP / `exam_extractor` | INFO ou WARNING | `duration_ms`, `outcome` |
| `ocr.tool.completed` | OCR MCP / `exam_extractor` | INFO ou WARNING | `duration_ms`, `outcome` |
| `ocr.tool.rejected` | OCR MCP / `image_access` | WARNING | `duration_ms`, `error_code`, `error_type` |
| `ocr.tool.failed` | OCR MCP / componente da falha | ERROR | `duration_ms`, `error_code`, `error_type` |
| `vision.request.started` | OCR MCP / `vision_client` | INFO | — |
| `vision.request.completed` | OCR MCP / `vision_client` | INFO | `duration_ms`, `outcome` |
| `vision.request.failed` | OCR MCP / `vision_client` | ERROR | `duration_ms`, `error_code`, `error_type` |
| `schedule.database.ready` | Schedule API / `persistence` | INFO | `duration_ms`, `outcome` |
| `schedule.database.failed` | Schedule API / `persistence` | ERROR | `outcome`, `error_code`, `error_type` |
| `schedule.database.stopped` | Schedule API / `persistence` | INFO | `outcome` |
| `schedule.configuration.failed` | Schedule API / `configuration` | ERROR | `outcome`, `error_code`, `error_type` |
| `schedule.request.started` | Schedule API / `http` | INFO | `outcome`, `request_id` |
| `schedule.reconciliation.completed` | Schedule API / `application` | INFO | `outcome`, `request_id` |
| `schedule.allocation.completed` | Schedule API / `application` | INFO | `outcome`, `request_id` |
| `schedule.appointments.completed` | Schedule API / `appointments` | INFO | `duration_ms`, `outcome` |
| `schedule.appointments.rejected` | Schedule API / `appointments` | WARNING | `duration_ms`, `outcome`, `error_code`, `error_type` |
| `schedule.appointments.failed` | Schedule API / `persistence` | ERROR | `duration_ms`, `outcome`, `error_code`, `error_type` |
| `schedule.request.rejected` | Schedule API / `http` | WARNING | `duration_ms`, `outcome`, `error_code`, `error_type` |
| `schedule.request.failed` | Schedule API / `http` | ERROR | `duration_ms`, `outcome`, `error_code`, `error_type` |

Todos os eventos incluem `timestamp`, `level`, `service`, `event` e `component`. A allowlist permite somente `request_id`, `duration_ms`, `outcome`, `error_code` e `error_type` como atributos variáveis. A mensagem livre do logger, valores de imagem e resultado clínico não são serializados. Códigos como `input_image_unavailable`, `process_already_running`, `vision_timeout`, `vision_api_rejected`, `exam_layout_unrecognized` e `image_not_found` permitem localizar a classe da falha sem armazenar a mensagem original.

**Correlação:** a Schedule API gera um `request_id` por requisição, devolve-o em `X-Request-ID` e inclui-o nos eventos HTTP e de aplicação daquela chamada. Ele não é aceito do cliente. Isso correlaciona eventos dentro da Schedule API, mas não substitui um `trace_id` distribuído entre runtime, OCR MCP, RAG e Schedule API. A propagação distribuída fica para a instrumentação OpenTelemetry futura, incluindo validação pelo SSE. O formatador mantém uma allowlist e descarta a mensagem livre do `LogRecord`, evitando que conteúdo arbitrário seja serializado.

**Critérios de aceite:** uma execução pode ser acompanhada do runtime até o Vision; falhas mostram a etapa e uma classificação técnica sem conteúdo sensível; a saída JSON do CLI não muda; a indisponibilidade do backend não falha o atendimento; e a busca nos dados coletados não encontra os marcadores sintéticos de PII, imagem ou credenciais.

**Fora da primeira entrega:** dashboards operacionais elaborados, alertas, métricas de negócio e implantação em produção. Primeiro estabilizar nomes, cardinalidade, propagação e política de privacidade; depois decidir quais métricas e painéis são úteis. Para métricas, preferir instrumentos e exportação estáveis do OpenTelemetry. A API de Logs do OpenTelemetry para Python está marcada como *Development* na documentação atual; encapsular a integração de logs para permitir revisão sem acoplar os apps a detalhes experimentais do SDK.

**Referências oficiais:** [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/) (status dos sinais), [instrumentação Python](https://opentelemetry.io/docs/languages/python/instrumentation/), [instrumentação HTTPX](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html), [instrumentação Starlette](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/starlette/starlette.html), [arquitetura single-node do OpenObserve](https://openobserve.ai/docs/architecture/), [ingestão OTLP de logs no OpenObserve](https://openobserve.ai/docs/reference/api/ingestion/logs/otlp/), [ingestão de traces no OpenObserve](https://openobserve.ai/docs/ingestion/traces/) e [repositório/licença do OpenObserve](https://github.com/openobserve/openobserve).

## Nota da discussão: referência da imagem para a tool de OCR

**Validação técnica:** a analogia com armazenamento de objetos (como S3 ou Cloud Storage) é válida, mas gerar um ID sozinho não faz upload nem concede acesso ao arquivo. Um componente de entrada precisa receber a imagem, registrá-la sob uma referência opaca e permitir que o serviço de OCR a recupere com autorização. O ID é uma referência, não uma credencial de autorização.

**Decisão aprovada para este desafio:** manter o modelo todo local e conteinerizado, sem GCS/S3, usando um volume compartilhado em `tmpfs`. O runtime/CLI registra a imagem no volume com um nome UUID vinculado à solicitação ativa. O agente chama a tool MCP de OCR via SSE com esse ID. O OCR valida o UUID e abre diretamente o arquivo correspondente no diretório permitido; não varre o diretório nem aceita caminhos ou URLs arbitrários fornecidos pelo modelo. Uma barreira local verifica os nomes de exames que sairiam da tool; quando reconhece PII, suprime toda a lista e retorna apenas um status genérico de revisão. Essa detecção não é uma garantia de anonimização completa.

**Decisão aprovada sobre o mapeamento:** não haverá `map.json` nesta etapa. O UUID é o nome do arquivo e permite resolução direta. O runtime/CLI remove a imagem ao final do fluxo, inclusive em caso de erro (`finally`); uma gravação também remove arquivos órfãos com mais de 30 minutos.

**Controles de acesso implementados:** runtime/CLI com escrita no volume e servidor OCR com montagem somente leitura. Um lock entre processos impede atendimentos simultâneos; uma nova gravação remove arquivos órfãos com mais de 30 minutos.

**Motivo da decisão:** a imagem do pedido pode conter PII. Mantê-la no armazenamento temporário e passar ao agente apenas um `image_id` evita que os bytes da imagem entrem no contexto do modelo. O agente ainda chama a tool OCR; o OCR acessa a imagem, verifica localmente os valores extraídos e devolve a lista somente quando não reconhece PII nas categorias configuradas. Se reconhecer, suprime a lista inteira. Essa fronteira reduz a exposição, sem prometer detecção completa.

O desenho também evita introduzir GCS e credenciais cloud num desafio que exige a solução conteinerizada com Docker Compose. Se futuramente o runtime estiver no GCP, o mesmo contrato pode apontar para um objeto privado no Cloud Storage; o serviço de entrada controla o upload e o OCR acessa o objeto por identidade de serviço ou autorização temporária. Uma URL assinada não deve ser tratada como um ID comum: quem a possui pode usá-la enquanto válida.

**Estado:** tmpfs compartilhado, UUID como nome do arquivo e resolução direta sem `map.json` estão implementados. Arquivos órfãos com mais de 30 minutos são removidos durante uma gravação.

### Decisão aprovada: Google ADK e Cloud Vision para OCR

**Decisão:** usar o Google ADK para construir e executar o agente e o Google Cloud Vision `DOCUMENT_TEXT_DETECTION` como backend de OCR, chamado pelo servidor MCP de OCR. O ADK é a camada do agente; o Vision é o serviço de reconhecimento de texto. A interface do MCP continua recebendo o `image_id` e retornando somente `{"exams": [...]}`.

**Motivos:**

- Alinhamento com a stack Google Cloud usada pela empresa e com o Google ADK solicitado no desafio.
- O Google Cloud Vision documenta português (`pt`) como idioma suportado, incluindo a variante brasileira.
- Para chamadas síncronas de OCR, o Google documenta que a imagem é processada em memória e não persistida em disco. Também declara que o conteúdo é usado para prestar o serviço, não para treinar ou melhorar o Vision.
- Essas garantias documentadas oferecem uma base clara para a decisão de arquitetura deste desafio.

**Limite de confiança e tratamento de dados:** a imagem continua sendo enviada ao Google Cloud Vision para processamento; portanto, `tmpfs` reduz a retenção local, mas não significa que os bytes permaneçam apenas nos containers. O fluxo escolhido usará a operação síncrona de anotação de imagem. A documentação informa que certos metadados da solicitação, como horário e tamanho, podem ser registrados temporariamente. Antes de enviar valores ao agente, o MCP de OCR verifica as categorias de PII configuradas e suprime o resultado completo quando detecta uma delas. A detecção não garante cobertura universal.

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

O componente `TemporaryImageStore` valida o conteúdo real da imagem, aceita PNG/JPG até 10 MB e grava os bytes sob um UUID sem extensão. Ele remove arquivos pelo UUID canônico e resolve órfãos expirados durante cada nova gravação. A gravação usa arquivo temporário e promoção atômica; falhas não deixam artefatos parciais. O comando `process --path <nome>` conecta esse armazenamento ao fluxo ADK/MCP: o runtime lê somente arquivos regulares da pasta permitida, envia o UUID ao agente e remove a cópia temporária em `finally`; o servidor OCR resolve o UUID diretamente no volume compartilhado. O arquivo original permanece intacto. Não há um comando público que apenas armazena imagens.

O `compose.yaml` mantém o serviço `assistant-runtime` em execução e monta o volume `image-storage` em `tmpfs` (64 MiB), gravável pelo runtime e somente para leitura pelo OCR. Os containers seguem como usuários não root (UID 10001). Cada nova gravação remove arquivos UUID com mais de 30 minutos; não há limpeza periódica. Um lock estável em `/tmp` impede atendimentos simultâneos no runtime. Os testes unitários cobrem formatos, conteúdo inválido, limite, UUID, escrita, exclusão, limpeza e falha na promoção atômica.

## Próximos passos acordados

1. [ ] Revisar e aprovar `docs/phase2-spec.md`; as decisões operacionais da primeira fatia já foram fechadas durante a implementação.
2. [x] Criar `apps/ocr_mcp`, contrato `extract_exams(image_id)` e testes MCP em memória.
3. [x] Implementar o cliente REST do Vision com chave de execução e testes HTTP simulados.
4. [x] Reconhecer os dois layouts de referência e classificar as marcações localmente, incluindo respostas de revisão manual.
5. [x] Expor o servidor OCR por SSE no Compose, com o volume temporário somente para leitura.
6. [x] Integrar `process` ao agente ADK e ao MCP OCR; cobrir com modelo determinístico e servidor SSE local, sem chamadas a serviços Google.
7. [ ] Executar a validação ponta a ponta das duas imagens com Cloud Vision real e modelo determinístico; rever latência, privacidade e limpeza.

### Refatoração transversal — responsabilidades, contratos e testes

- [x] Agrupar os casos de uso do runtime em `services/generate/`, `services/process/` e `services/image_storage/`; manter o CLI como adaptador de entrada.
- [x] Separar o registro de tools ADK da leitura de eventos MCP/SSE para manter a execução focada na coordenação do agente.
- [x] Manter o `finally` focado na chamada a `delete_image(image_id)` e preservar erro composto e sanitizado quando processamento e limpeza falharem.
- [x] Introduzir `ImageId` e `ExamResult` no runtime; usar `ImageId`, `BoundingBox`, `ExamCode`, `ExamMark` e `OcrDocument` no OCR.
- [x] Separar a decodificação da imagem e a classificação visual do checkbox em módulos dedicados.
- [x] Espelhar a estrutura dos testes unitários com os serviços do runtime e compartilhar o fake e as fixtures Vision nos testes de transporte do OCR.
- [x] Executar as suítes dos dois apps com cobertura, Ruff e format check, Mypy, `uv lock --check`, `docker compose config` e `git diff --check`; essa execução histórica da Fase 4 passou. Runtime: 102 testes; OCR MCP: 107 testes. O E2E manual não integra a cobertura padrão. Para os números e cobertura atuais, consultar a validação mais recente abaixo.

**Validação mais recente do hardening (2026-10-05):** runtime — 109 testes, 91,4% de cobertura; OCR MCP — 107 testes, 96,1%. Ruff, formatação, Mypy, `uv lock --check`, `docker compose config --quiet`, build das duas imagens e `git diff --check` passaram. A suíte padrão não chama Vision nem Gemini; o E2E manual com Vision real está registrado acima e não integra a cobertura padrão.

## Princípios herdados da Fase 1

- Manter a especificação do agente restrita a valores e tools permitidos; não aceitar código, endpoints ou credenciais arbitrárias no JSON.
- Preservar a geração determinística e os testes locais reproduzíveis.
- Usar modelo determinístico e `InMemoryRunner` nos testes sem chamadas externas; documentar separadamente qualquer teste que use Gemini real.
- Validar cada entregável e sua documentação antes de avançar para a subfase seguinte.

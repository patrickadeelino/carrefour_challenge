# Carrefour RAG MCP

App independente para buscar nomes de exames em um catálogo fictício e
devolvê-los associados a códigos controlados. O catálogo, a validação, o
contrato em lote e o serviço local de recuperação estão implementados. A tool
MCP `search_exams` é exposta por SSE e pode ser descoberta na rede interna do
Docker Compose. A integração do agente/runtime com este serviço fica para uma
etapa posterior.

## Catálogo

`src/carrefour_rag_mcp/data/exams.json` é a fonte versionada do catálogo. Ele
contém 122 registros com códigos `CAT-*` fictícios, nomes canônicos e aliases
revisados. O JSON é empacotado junto ao app; o serviço o carrega e constrói um
índice em memória na inicialização. Uma alteração no catálogo será entregue
por uma nova imagem do app. O versionamento do arquivo no Git é suficiente;
não há campo `schema_version` neste contrato.

O carregador do catálogo empacotado exige pelo menos 100 registros e rejeita
JSON inválido, campos desconhecidos, registros incompletos, códigos repetidos,
nomes canônicos repetidos e aliases duplicados dentro do mesmo exame. A
validação estrutural aceita catálogos menores para testes controlados. Aliases
iguais em exames diferentes são permitidos de propósito para que a busca
retorne uma ambiguidade, sem escolher um código.

## Contrato de busca em lote

O serviço local recebe um `SearchExamsRequest`; a tool MCP é
`search_exams(exam_names)`. O pedido aceita de 1 a 50 nomes, com até 160
caracteres por nome. A resposta não repete o texto consultado. Cada resultado
aponta para as posições de todas as entradas equivalentes com `input_indices`.

- `resolved`: nome canônico ou alias exato único; inclui código e nome
  canônico.
- `ambiguous`: mais de um exame corresponde exatamente; inclui candidatos e
  não inclui códigos.
- `review_required`: a busca aproximada encontrou candidatos; não escolhe
  nem inclui código para agendamento.
- `not_found`: não há correspondência; nenhum código é inventado.

Os nomes canônicos, aliases e consultas usam a mesma normalização: caixa e
acentos são ignorados, pontuação vira separador e espaços são compactados.
Qualificadores como `T3`/`T4`, `IgG`/`IgM`, `HDL`/`LDL`, `livre`/`total` e
`jejum` são preservados. Uma busca exata única retorna `resolved`; uma colisão
exata entre exames retorna `ambiguous`.

Sem busca exata, RapidFuzz compara o nome normalizado com os termos do índice.
São devolvidos até três candidatos ordenados por similaridade e, em caso de
empate, por código. O corte atual é 80 pontos: os casos acima dele retornam
`review_required`; abaixo dele, `not_found`. Busca aproximada nunca resolve
automaticamente nem devolve códigos. O corte foi calibrado em 40 exemplos
sintéticos rotulados: o menor score nos 12 typos foi 83,7 e o maior nos 8 nomes
fora do catálogo foi 75,0. A pontuação mede semelhança textual, não probabilidade
de acerto, e o conjunto pequeno não representa todos os pedidos possíveis.

Na amostra de teste: 227/227 etiquetas do catálogo resolvem para o código
esperado; 11/11 ocorrências das fixtures OCR resolvem (7 códigos distintos);
12/12 erros de grafia incluem o exame rotulado entre as sugestões; 8/8 termos
fora do catálogo são recusados; e 8/8 variações de qualificadores não são
resolvidas automaticamente. Um alias compartilhado retorna `ambiguous`. Esses
resultados descrevem somente os casos sintéticos versionados na suíte.

Consultas equivalentes são deduplicadas pela forma normalizada e retornam um
resultado por nome distinto, ordenado pela primeira ocorrência. `input_indices`
relaciona o resultado a todas as posições originais. Nomes consultados e
resultados clínicos não aparecem em logs operacionais.

## Desenvolvimento

O serviço atende em `http://rag-mcp:8000/sse` na rede Compose. Ele valida o
header `Host` com a variável `CARREFOUR_RAG_ALLOWED_HOSTS`; em Compose, o valor
é `rag-mcp:8000`. A porta 8000 não é publicada no host. O catálogo é carregado
uma vez no startup, e uma falha impede o servidor de iniciar.

Para construir e iniciar o serviço a partir da raiz do repositório:

```sh
docker compose up -d --build rag-mcp
```

Os testes e verificações são executados dentro do container:

```sh
docker compose exec -w /workspace/apps/rag_mcp rag-mcp pytest -q
docker compose exec -w /workspace/apps/rag_mcp rag-mcp ruff check .
docker compose exec -w /workspace/apps/rag_mcp rag-mcp ruff format --check .
docker compose exec -w /workspace/apps/rag_mcp rag-mcp mypy
```

A suíte cobre o cliente MCP em memória e o transporte SSE real por loopback.
Não usa Vision, Gemini, API de agendamento nem outros serviços externos.

## Logs operacionais

O app usa `carrefour-observability` para emitir eventos JSON em `stderr`. A
inicialização registra `rag.catalog.ready` ou `rag.catalog.failed`; chamadas da
tool registram exatamente um evento terminal: `rag.search.completed`,
`rag.search.rejected` ou `rag.search.failed`. Os eventos incluem duração e,
quando aplicável, um código e tipo de erro estáveis. `completed` significa que
a tool produziu uma resposta válida, mesmo que os resultados exijam revisão ou
não encontrem correspondência.

Os logs não incluem consultas, nomes ou códigos de exames, candidatos,
similaridades, payloads nem mensagens brutas de exceção. Falhas do catálogo
impedem a criação do servidor. O Uvicorn mantém os access logs HTTP desativados
para não duplicar registros nem expor metadados da requisição. Rejeições de
esquema feitas pelo SDK antes de chamar o handler não produzem evento da
aplicação.

## Referência

- [Documentação do RapidFuzz: `process.extract` e ranking de candidatos](https://rapidfuzz.github.io/RapidFuzz/Usage/process.html)

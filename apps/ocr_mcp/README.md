# Carrefour OCR MCP

App Python independente que abriga o servidor MCP responsável por identificar
exames em uma imagem temporária.

## Contrato inicial

A tool `extract_exams(image_id)` recebe somente o UUID do arquivo temporário. O
servidor valida o formato do UUID, resolve o arquivo dentro do diretório
configurado e entrega os bytes a um extrator injetado. O resultado público é
estruturado como `{"exams": ["Hemograma completo"]}`. Os nomes dos exames
permanecem no idioma reconhecido; os nomes das chaves JSON são em inglês.

A fronteira da tool aceita somente formas exatas: sucesso `{"exams": [...]}`;
revisão manual com `status: "review_required"`, `exams` e `ambiguous_exams`; ou
bloqueio de privacidade com `status: "review_required"` e
`reason: "sensitive_data_detected"`. Campos extras, listas malformadas e estados
desconhecidos falham de forma segura. A barreira reconstrói a saída usando apenas
as chaves permitidas e analisa todos os nomes antes de devolvê-los. Falhas
técnicas retornam um erro genérico de tool; logs contêm somente classificação
operacional estável, sem conteúdo da exceção ou valores do documento.

O servidor recebe o extrator por injeção; os testes do contrato MCP usam um
extrator falso e validam descoberta/chamada tanto com cliente em memória quanto
por HTTP+SSE local real. Em execução, o app inicia o transporte HTTP+SSE na
porta 8000 e aceita somente os `Host` configurados em
`CARREFOUR_OCR_ALLOWED_HOSTS`. A aplicação registra eventos operacionais JSON
da tool e da chamada ao Vision, sem incluir imagem, UUID, nomes de exames,
texto OCR bruto ou credenciais. Para acompanhá-los localmente, use
`docker compose logs -f ocr-mcp`.

## Cliente Google Cloud Vision

`GoogleCloudVisionClient` envia os bytes da imagem para
`DOCUMENT_TEXT_DETECTION` pelo endpoint REST de anotação. Ele obtém a chave de
`GOOGLE_CLOUD_VISION_API_KEY` com `from_environment`, envia-a pelo header
`X-Goog-Api-Key` e usa timeout de 60 segundos. O cliente não repete chamadas
automaticamente e converte falhas de transporte, HTTP e resposta em exceções
sanitizadas. A resposta bruta do Vision fica em memória para a etapa de
extração; não é registrada nem enviada ao agente.

Mantemos o Cloud Vision nesta entrega e identificamos os dois layouts pelos
marcadores de texto que ele reconhece. O Document AI Form Parser é uma
alternativa futura para detectar checkboxes, mas tem cobrança própria; não o
avaliamos para evitar custo neste desafio. A decisão e os preços consultados
estão registrados na [especificação da Fase 2](../../docs/phase2-spec.md#33-regras-para-os-dois-layouts-de-referência).

Os testes usam `httpx.MockTransport`: verificam a requisição e os caminhos de
erro sem contactar a API ou consumir cota.

## Extração e classificação local

`ExamProcessingService`, em
`src/carrefour_ocr_mcp/services/exam_processing/`, coordena a leitura pelo UUID,
a extração e a barreira de PII. `server.py` mantém a adaptação ao MCP: recebe o
argumento da tool, chama o serviço e converte falhas seguras em erros do
protocolo.

Os serviços de extração ficam em `src/carrefour_ocr_mcp/services/exam_extractor/`.
`VisionExamExtractor` chama o Vision e delega à `ExamExtractorFactory`, que
seleciona um dos dois serviços especializados com base nos marcadores do OCR:

- `NumberedListExamExtractor` extrai os itens numerados entre os marcadores da
  seção e exige numeração sequencial antes de retornar os nomes.
- `CheckboxExamExtractor` associa as coordenadas OCR dos códigos `EX-101` a
  `EX-110` às regiões das caixas. Pillow verifica o contorno e conta tinta nas
  duas diagonais: duas marcas classificam como selecionada, nenhuma como vazia
  e apenas uma como ambígua.

Os tipos de domínio usados entre etapas ficam em
`src/carrefour_ocr_mcp/value_objects/`: `ImageId` valida a referência interna,
`OcrDocument` organiza palavras e coordenadas, e `ExamCode`/`BoundingBox`
representam os dados posicionais usados na classificação local.

O extrator reconhece somente os dois layouts sintéticos de referência:

- Uma marca ambígua resulta em `{"status": "review_required", "exams": [...],
  "ambiguous_exams": [...]}`. Layout ou resposta OCR não reconhecidos geram
  falha sanitizada; o extrator não transforma incerteza em uma lista vazia.

Os offsets, dimensões das regiões e limites de pixels estão calibrados para o
formulário de demonstração de 2325 × 3288 pixels. Isso não é um classificador
genérico de formulários. O texto OCR integral e a imagem ficam somente em
memória durante a chamada; o extrator não persiste nem registra esses dados e
retorna apenas nomes de exames.

Os testes dessa etapa usam cópias das duas imagens sintéticas e respostas OCR
estruturadas sanitizadas. Também verificam uma marca parcial criada a partir da
ficha de demonstração. Nenhum teste chama o Vision real.

## Transporte HTTP+SSE e container

O container executa `python -m carrefour_ocr_mcp` como usuário não root. O
Compose não publica a porta 8000 no host; os outros serviços do mesmo projeto
acessam o servidor pelo endereço interno `http://ocr-mcp:8000/sse`. A imagem
compartilhada é montada somente para leitura no OCR. O runtime permanece como o
único serviço autorizado a gravar no volume `tmpfs`.

`GOOGLE_CLOUD_VISION_API_KEY` é lida do ambiente quando o container inicia. Ela
não é argumento de build, não é copiada para a imagem e não deve ser adicionada
ao Git. No Compose local, configure-a no `.env` ignorado pelo Git.

## Testes

Na raiz do app:

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
uv run mypy
```

O app tem seu próprio `pyproject.toml` e `uv.lock`; suas dependências são
independentes do runtime.

Os testes unitários espelham o código em `tests/unit/carrefour_ocr_mcp/`, com
casos separados para cada extrator e para a Factory. O contrato do servidor MCP
com o cliente em memória e a conexão HTTP+SSE real ficam em
`tests/integration/carrefour_ocr_mcp/`. Ambos usam um processador falso, sem
chamadas externas.

## Referências

- [MCP Python SDK — testes com servidor em memória](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/get-started/testing.md)
- [MCP Python SDK — transporte SSE do servidor](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md)
- [MCP Python SDK — transporte SSE do cliente](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md)
- [MCP Python SDK — mudanças da versão 2](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md)
- [Cloud Vision — requisições REST](https://docs.cloud.google.com/vision/docs/request)
- [Cloud Vision — OCR](https://docs.cloud.google.com/vision/docs/ocr)
- [Pillow — documentação](https://pillow.readthedocs.io/en/stable/)
- [Google Cloud — boas práticas para chaves de API](https://docs.cloud.google.com/docs/authentication/api-keys-best-practices)

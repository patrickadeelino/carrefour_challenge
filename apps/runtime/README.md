# Runtime do Carrefour Challenge

Este app contém o CLI de validação, geração e processamento de pedidos, além do armazenamento temporário de imagens. Ele tem dependências, build Docker e testes próprios. O servidor MCP de OCR fica em `apps/ocr_mcp/` e é conectado pelo agente usando SSE.

O projeto usa Python 3.11 ou superior e `uv`. O `Dockerfile` instala o pacote e as dependências de desenvolvimento; os comandos de execução e verificação são documentados no [README principal](../../README.md) e devem ser chamados pelo Docker Compose.

O ponto de entrada Python é `python -m carrefour_runtime`. Execute `generate` antes de `process`; o comando de processamento carrega `generated/agent.py`, valida e guarda a imagem em `tmpfs`, chama `extract_exams` pelo MCP SSE e remove a cópia temporária ao concluir.

O `process` emite eventos operacionais JSON para `stderr`; `stdout` fica reservado
à resposta JSON. Como ele roda com `docker compose exec`, esses logs aparecem no
terminal que executou o comando e não devem ser presumidos em
`docker compose logs assistant-runtime`.

## Estrutura do app

- `services/generate/` valida a especificação e produz a factory ADK determinística.
- `services/process/` coordena o pedido, executa o agente, monta o registro fechado de tools e captura o resultado estruturado dos eventos ADK.
- `services/image_storage/` valida e guarda a cópia temporária da imagem.
- `value_objects/` representa o UUID interno da imagem e o resultado validado do OCR.
- `tests/unit/carrefour_runtime/` espelha os serviços e objetos; `tests/integration/carrefour_runtime/` cobre a conexão SSE local com o ADK; `tests/e2e/` contém a validação manual optativa com Cloud Vision real.

Runtime e OCR mantêm seus próprios `ImageId`, pois são apps com builds
independentes. Entre containers, o contrato compartilhado continua sendo
somente o UUID canônico em texto.

O Compose injeta `GOOGLE_API_KEY` no runtime para a chamada do modelo definido na especificação. A variável `GOOGLE_CLOUD_VISION_API_KEY` é injetada separadamente no container OCR. Nenhuma das chaves entra nas imagens Docker ou nos arquivos do Git. O Compose também desativa a descoberta de certificados mTLS Google no runtime: o MCP usa apenas HTTP na rede interna e não tem autenticação nesta etapa.

Os testes unitários ficam em `tests/unit/carrefour_runtime/`, seguindo os módulos do pacote. Os testes de integração ficam em `tests/integration/carrefour_runtime/`.

O E2E de Vision fica em `tests/e2e/` e não é coletado pela execução padrão. Ele exige containers Compose em execução e `GOOGLE_CLOUD_VISION_API_KEY` configurada no serviço OCR. Consulte o README principal para os comandos; o modelo ADK é determinístico e o teste não chama Gemini.

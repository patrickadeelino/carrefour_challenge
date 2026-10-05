# Runtime do Carrefour Challenge

Este app contém o CLI de validação, geração e processamento de pedidos, além do armazenamento temporário de imagens. Ele tem dependências, build Docker e testes próprios. O servidor MCP de OCR fica em `apps/ocr_mcp/` e é conectado pelo agente usando SSE.

O projeto usa Python 3.11 ou superior e `uv`. O `Dockerfile` instala o pacote e as dependências de desenvolvimento; os comandos de execução e verificação são documentados no [README principal](../../README.md) e devem ser chamados pelo Docker Compose.

O ponto de entrada Python é `python -m carrefour_runtime`. Execute `generate` antes de `process`; o comando de processamento carrega `generated/agent.py`, valida e guarda a imagem em `tmpfs`, executa o agente ADK com OCR MCP, RAG MCP e Schedule API e remove a cópia temporária ao concluir.

O `process` apresenta mensagens humanizadas em português no `stdout`, com nomes
canônicos e horários, sem códigos de catálogo ou IDs de agendamento. Eventos
operacionais JSON continuam em `stderr`. Como o comando roda com
`docker compose exec`, os logs aparecem no terminal que o executou e não devem
ser presumidos em `docker compose logs assistant-runtime`.

## Estrutura do app

- `services/generate/` valida a especificação e produz a factory ADK determinística.
- `services/process/` coordena o pedido, compõe o caso de uso em `composition.py`, executa o fluxo completo do agente, monta o registro fechado de tools, protege a ordem com estado confiável e captura os resultados estruturados dos eventos ADK.
- `services/image_storage/` valida e guarda a cópia temporária da imagem.
- `value_objects/` representa o UUID interno da imagem, a identidade local do usuário e o resultado final validado do atendimento.
- `tests/unit/carrefour_runtime/` espelha os serviços e objetos; `tests/integration/carrefour_runtime/` cobre o fluxo completo com MCP/SSE locais e modelo determinístico. A validação manual real é feita pelo comando `process`, sem harness pytest; consulte o README principal.

Runtime e OCR mantêm seus próprios `ImageId`, pois são apps com builds
independentes. Entre containers, o contrato compartilhado continua sendo
somente o UUID canônico em texto.

O Compose injeta `GOOGLE_API_KEY` e `ZAI_API_KEY` no runtime; a factory gerada usa a credencial correspondente ao par de provedor e modelo permitido em `specification.json`. A variável `GOOGLE_CLOUD_VISION_API_KEY` é injetada separadamente no container OCR. Nenhuma das chaves entra nas imagens Docker ou nos arquivos do Git. O Compose também desativa a descoberta de certificados mTLS Google no runtime: o MCP usa apenas HTTP na rede interna e não tem autenticação nesta etapa.

Os testes unitários ficam em `tests/unit/carrefour_runtime/`, seguindo os módulos do pacote. Os testes de integração ficam em `tests/integration/carrefour_runtime/`.

O fluxo normal usa o provedor/modelo de `specification.json`, Cloud Vision via OCR MCP, RAG MCP e Schedule API. O E2E manual executa esse mesmo comando pelo Compose com credenciais de execução; ele pode gerar cobrança no Vision e no provedor de modelo. Consulte o README principal para os passos e comandos.

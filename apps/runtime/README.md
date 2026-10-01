# Runtime do Carrefour Challenge

Este app contém o CLI de validação e geração do agente, além do armazenamento temporário de imagens usado pelo fluxo da Fase 2. Ele tem dependências, build Docker e testes próprios. O servidor MCP de OCR será outro app e não faz parte deste diretório ainda.

O projeto usa Python 3.11 ou superior e `uv`. O `Dockerfile` instala o pacote e as dependências de desenvolvimento; os comandos de execução e verificação são documentados no [README principal](../../README.md) e devem ser chamados pelo Docker Compose.

O ponto de entrada Python é `python -m carrefour_runtime`. O pacote contém as capacidades de transpiler da Fase 1 e os componentes de runtime que já foram implementados.

# PRD — Carrefour Challenge

**Escopo atual:** fase 1 — especificação JSON e geração do agente.

**Estado:** fase 1 concluída no escopo definido abaixo. A execução pelo `InMemoryRunner` com modelo determinístico de teste comprova o despacho das tools; chamadas a um modelo real ficam para uma etapa posterior.

## 1. Objetivo

Construir a primeira parte do desafio: um transpilador que recebe a especificação JSON de um agente exam scheduler, valida a configuração e gera uma factory Python que instancia esse agente com Google ADK ao receber implementações confiáveis das tools.

## 2. Problema a resolver

A especificação deve representar um agente sem permitir que o seu autor injete código ou conexões arbitrárias. O resultado precisa ser compreensível, reproduzível e fácil de revisar.

O transpilador converte uma descrição declarativa em uma definição de agente. Ele não usa um LLM para escrever o próprio código gerado.

## 3. Usuário principal

Uma pessoa desenvolvedora ou avaliadora que fornece uma configuração JSON e precisa:

- saber se ela é válida;
- receber erros que identifiquem o campo e o motivo;
- obter uma definição Python do agente compatível com o escopo suportado.

## 4. Escopo funcional

1. Aceitar um documento JSON que declare nome, tipo, modelo e ferramentas do agente.
2. Na versão inicial, aceitar somente o tipo exam_scheduler.
3. Validar o modelo contra uma allowlist explícita e as ferramentas contra IDs registrados e permitidos pelo projeto. Para `exam_scheduler`, as três tools atuais são obrigatórias.
4. Associar o tipo exam_scheduler a instruções fixas mantidas pelo projeto, não a uma instrução livre fornecida no JSON.
5. Gerar uma factory Python determinística que recebe as implementações aprovadas das tools e instancia o agente usando Google ADK.
6. Produzir uma explicação acionável quando a entrada for inválida.
7. Gerar os mesmos bytes de Python para a mesma especificação válida; fingerprint e reuso por cache ficam fora do escopo atual.

## 5. Requisitos de segurança

- O JSON não pode conter código Python, comandos, credenciais ou URLs de servidor MCP.
- As tools são declaradas por identificadores lógicos. O runtime confiável fornecerá implementações aprovadas; endpoints não são parte da especificação JSON.
- Cada tool precisa existir e estar permitida para o tipo de agente.
- Toda especificação é validada antes da geração.
- A geração determinística garante reprodutibilidade sem persistir ou reutilizar artefatos por hash nesta fase.

## 6. Restrições do desafio relacionadas

O desafio exige geração de agentes com Google ADK. Também exige, nas fases posteriores, MCP via SSE para OCR e catálogo/RAG, uma API FastAPI de agendamento, proteção de PII e execução em Docker Compose.

Esta fase não implementa esses serviços. Ela estabelece como um agente futuro poderá referenciar somente capacidades aprovadas. Os endpoints dos MCPs não serão fornecidos pelo JSON.

O registro atual mantém os IDs aceitos, sua ordem canônica de geração e o conjunto obrigatório para `exam_scheduler`. Os adaptadores e endpoints das implementações serão definidos no runtime de uma etapa posterior.

A fase termina na validação da especificação, geração da factory, instanciação do objeto `Agent` do ADK e comprovação de que o `InMemoryRunner` despacha chamadas às tools registradas. O teste usa respostas determinísticas de um modelo falso, sem credenciais ou chamadas externas; validar o comportamento do Gemini real fica para uma etapa posterior.

## 7. Fora do escopo

- Processar imagens ou executar OCR.
- Implementar MCP de OCR ou MCP de catálogo.
- Implementar recuperação de exames ou a base de 100+ itens.
- Implementar ou executar chamadas à API de agendamento.
- Implementar a anonimização de PII.
- Criar execução de agentes genéricos ou aceitar ferramentas arbitrárias.
- Suportar provedores de modelos diferentes de Gemini na versão inicial.

## 8. Critérios de conclusão da fase

- Uma especificação válida gera sempre os mesmos bytes de Python.
- Uma especificação desconhecida ou inválida falha com um erro claro e não gera código.
- A saída é Python sintaticamente válido e contém uma factory que instancia o agente por meio do Google ADK com as tools fornecidas pelo runtime confiável.
- Um teste de integração usa o `InMemoryRunner` do ADK e um modelo determinístico para comprovar que cada tool registrada pode ser chamada e executada.
- Alterar espaços, ordem das chaves ou ordem das tools não altera o código gerado.
- Alterar o nome do agente altera o código gerado; tipo, modelo e tools aceitos permanecem limitados às opções atualmente suportadas.
- Um JSON que referencia uma tool inexistente, proibida ou incompatível com exam_scheduler é rejeitado.
- Um JSON não consegue escolher URLs MCP ou fornecer instruções livres.

## 9. Recurso adiado: fingerprint e cache

Fingerprint SHA-256 e reuso de artefatos ficam adiados. A geração atual é determinística e usa um template local, então calcular e manter um cache não traz benefício suficiente para esta fase. Se a geração se tornar custosa ou passar a produzir artefatos persistidos, o recurso poderá ser reconsiderado; a validação deverá continuar ocorrendo antes de qualquer reuso.

## 10. Registro de uso de IA

O README registra como a IA apoiou o refinamento e a implementação, quais decisões de escopo foram feitas pelo candidato e quais verificações foram executadas. O código gerado vem de um template determinístico do projeto; um LLM não escreve nem altera esse código durante a geração.

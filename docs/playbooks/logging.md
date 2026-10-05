# Playbook de logging

Este guia define como criar e revisar logs nos apps do projeto. O objetivo é
explicar etapas e falhas sem registrar imagens, dados pessoais ou conteúdo
clínico.

## Checklist dos 5 Ws

A OWASP recomenda que os eventos permitam responder quando, onde, quem e o quê;
também sugere registrar ação, resultado e motivo quando forem úteis. Usamos esse
princípio como checklist adaptado ao projeto, sem tratar os campos abaixo como
uma exigência universal da OWASP.

| Pergunta | Campo do projeto | Uso |
| --- | --- | --- |
| Quando? | `timestamp` | Horário UTC do evento. |
| Quem? | `service` | Serviço que emitiu o evento, como `assistant-runtime` ou `ocr-mcp`; não é a identidade do paciente. |
| O quê? | `event` | Nome estável da transição, como `process.started` ou `vision.request.failed`. |
| Onde? | `component` | Componente que conhece a etapa, como `process_service` ou `vision_client`. |
| Qual resultado ou motivo? | `outcome`, `error_code`, `error_type` | Descreve sucesso, revisão ou classe técnica da falha sem incluir texto bruto. |

`level` representa a severidade: use `INFO` para transições e sucessos,
`WARNING` para revisão manual ou condições recuperáveis e `ERROR` para falhas
técnicas. Inclua duração quando ela ajudar a localizar lentidão.

## Como adicionar um evento

- Registre transições úteis nas fronteiras entre etapas; evite log por função ou
  por item de uma lista.
- Prefira nomes de evento e códigos de erro estáveis, definidos no componente
  responsável.
- Passe somente atributos operacionais aprovados pelo formatador compartilhado
  em `packages/carrefour_observability/`.
- Mantenha a saída funcional do CLI em `stdout` e os logs operacionais em
  `stderr`.
- Adicione ou ajuste testes para validar os campos, a severidade e a ausência de
  dados sensíveis.

## Dados que não entram nos logs

Não registre imagem ou bytes, caminho/nome do arquivo, `image_id`, dados
pessoais, nomes ou resultados de exames, texto OCR, prompts, credenciais,
cabeçalhos de autenticação, payloads ou respostas brutas de serviços externos.
Não use mensagens livres de exceção como atributos; classifique a falha com um
`error_code` estável e uma classe técnica segura.

## Referência

- [OWASP Logging Cheat Sheet — Event attributes e Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

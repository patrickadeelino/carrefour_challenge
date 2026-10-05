# Workflow de desenvolvimento

Este playbook orienta pessoas e assistentes que alteram o projeto. O README
resume o produto; os planos e especificações das fases registram decisões e
progresso. Use estes guias junto com os playbooks de [testes](testing.md) e
[logging](logging.md).

## Antes de alterar

- Leia o README, o plano da fase ativa e a especificação relacionada à mudança.
- Confira o estado do Git e preserve alterações locais que não pertencem à tarefa.
- Se a mudança afetar contratos, segurança, comportamento ou escopo, esclareça
  as decisões e os critérios de aceite antes de implementar.

## Ciclo de mudança

1. Divida o trabalho em uma entrega pequena, com comportamento esperado e
   validações definidos.
2. Implemente e cubra o comportamento e os caminhos de falha com testes no nível
   adequado, seguindo o [playbook de testes](testing.md).
3. Revise o diff contra os requisitos: responsabilidades, tratamento de erros,
   privacidade nos logs e alterações de documentação.
4. Rode as suítes e verificações do app dentro do Docker Compose. Se a mudança
   tocar Compose ou build, valide também a configuração e a construção afetadas.
5. Atualize o plano da fase e seus checkboxes somente quando houver evidência de
   que os critérios foram atendidos. Registre limitações ou decisões adiadas.

## Uso consciente de IA

A IA pode apoiar análise, implementação e documentação, mas suas sugestões são
propostas para revisão. Entenda o código alterado, confira referências externas,
revise o diff e valide o comportamento com testes. Não aceite código gerado sem
critério nem registre resultados que não foram observados. Mantenha a seção
[Transparência sobre o uso de IA](../../README.md#transparência-sobre-o-uso-de-ia)
fiel ao processo realmente seguido.

## Entrega e commits

Ao concluir uma fatia, resuma o que mudou, quais verificações passaram e o que
permanece pendente para revisão. Organize commits por entregável coerente e
documentação correspondente; faça commits depois da revisão e validação do
usuário.

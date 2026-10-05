# Especificação técnica — fase 1

**Estado:** implementada para o escopo da fase 1; o despacho das tools foi exercitado pelo `InMemoryRunner` com um modelo determinístico de teste. Chamadas a um modelo real estão adiadas para uma etapa posterior.

## 1. Contrato de entrada

A especificação é uma configuração confiável de desenvolvimento fornecida ao transpilador. Não é a imagem nem a entrada clínica de uma execução futura.

Formato aceito:

~~~json
{
  "agent": {
    "name": "exam_scheduler_demo",
    "type": "exam_scheduler",
    "model": {
      "provider": "gemini",
      "name": "gemini-3.1-flash-lite"
    },
    "tools": [
      "medical_order_ocr",
      "exam_catalog_search",
      "appointment_booking"
    ]
  }
}
~~~

A allowlist aceita os pares `gemini`/`gemini-3.1-flash-lite` e `zai`/`glm-5.3`. O primeiro foi selecionado para continuar a validação manual após responder `OK` em uma chamada REST exploratória; o segundo foi adicionado para testar a integração alternativa via LiteLLM.

## 2. Contrato dos campos

| Campo | Regra implementada |
|---|---|
| agent.name | String obrigatória com até 63 caracteres, começando por letra minúscula e contendo apenas letras minúsculas, números ou `_`. |
| agent.type | Valor obrigatório e fixo: `exam_scheduler`. |
| agent.model.provider | Provedor explícito: `gemini` ou `zai`, aceito somente com o modelo pareado na allowlist. |
| agent.model.name | Nome explícito do modelo: `gemini-3.1-flash-lite` ou `glm-5.3`, pareado respectivamente com `gemini` ou `zai`. |
| agent.tools | Lista sem duplicatas contendo exatamente `medical_order_ocr`, `exam_catalog_search` e `appointment_booking`. A ordem no JSON não afeta a ordem canônica do código gerado. |

Todos os campos são obrigatórios. Campos desconhecidos e valores fora dos tipos ou listas aceitos são rejeitados.

## 3. Registro de tools

A especificação declara IDs, e o transpilador consulta um registro interno mantido pelo projeto. Nesta fase, o registro define os IDs aceitos, sua ordem canônica e o conjunto obrigatório para `exam_scheduler`; ainda não contém adaptadores de runtime.

| ID lógico | Papel na solução | Integração prevista para etapa posterior |
|---|---|---|
| medical_order_ocr | Extrair exames do pedido | MCP via SSE |
| exam_catalog_search | Encontrar nomes e códigos no catálogo | MCP via SSE |
| appointment_booking | Solicitar agendamento | Adaptador aprovado para a API FastAPI |

Para exam_scheduler, as três capacidades são necessárias ao fluxo completo esperado no desafio. Os endereços SSE e a URL da API serão fornecidos por configuração de execução confiável, nunca pelo JSON.

O transpilador rejeita IDs ausentes do registro, duplicados ou ausentes do conjunto obrigatório. Um servidor MCP adicional só se torna selecionável após ser registrado e aprovado pelo projeto.

## 4. Instruções do agente

Não haverá campo instruction no JSON. O campo type seleciona um conjunto fixo de instruções mantido no código do projeto. A validação garante que o tipo suportado tenha uma definição de agente e um conjunto de tools coerente.

## 5. Provedor de modelo

A allowlist aceita somente estes pares explícitos de provedor e modelo: `gemini` com `gemini-3.1-flash-lite` e `zai` com `glm-5.3`. A autenticação é configuração de ambiente, não conteúdo do JSON. A integração Z.ai usa o adaptador LiteLLM do ADK e a variável `ZAI_API_KEY`; isso não habilita modelos ou provedores arbitrários.

Outros modelos podem ser acrescentados futuramente com um provedor e adaptador explicitamente implementados. O ADK documenta integração com LiteLLM para modelos externos; isso requer dependências e credenciais específicas e, portanto, não significa que qualquer string de modelo seja executável automaticamente.

## 6. Validação

### Sintaxe e forma

- JSON bem formado.
- Todos os campos obrigatórios presentes.
- Tipos JSON corretos para cada campo.
- Nenhum campo desconhecido.

### Semântica

- type existente e habilitado.
- par `provider`/`name` presente na allowlist.
- tools sem IDs repetidos, todos registrados e permitidos pelo tipo.
- Todas as tools requeridas por exam_scheduler presentes.
- Nome de agente dentro do padrão definido.

### Proteções de configuração

- Rejeitar campos para código, comando de shell, URL, caminho executável ou segredo.
- Não interpolar valores arbitrários do JSON em sintaxe Python.
- Resolver somente IDs de tools por meio do registro interno.
- Validar toda especificação antes de gerar o código. Reuso por cache está fora do escopo atual.

Os erros do CLI incluem o caminho do campo e uma mensagem acionável. Exemplo: `agent.tools` contém um ID desconhecido ou uma tool obrigatória está ausente.

## 7. Geração e determinismo

A geração usa templates/código determinístico mantido pelo projeto; não chama um LLM para redigir Python. Para a mesma especificação válida, diferenças de espaços, ordem das chaves e ordem de tools produzem os mesmos bytes de Python.

Fingerprint de build e reuso de artefatos por cache estão fora do escopo atual. Se forem considerados futuramente, a validação deverá ocorrer antes de qualquer consulta ou reutilização do artefato.

## 8. Saída

A saída da fase 1 é um arquivo Python que:

- expõe `create_agent(registered_tools)`, uma factory que instancia o agente por meio da API Google ADK;
- recebe as implementações aprovadas de tools do runtime confiável, e não do JSON, exigindo correspondência exata entre os IDs registrados e os IDs declarados;
- informa IDs ausentes ou extras com `ValueError` antes de instanciar o agente;
- seleciona instruções fixas pelo tipo;
- não contém endpoints nem segredos vindos da especificação;
- é Python sintaticamente válido e produz os mesmos bytes para a mesma especificação válida.

O CLI usa `generate specification.json --output caminho/agent.py`. A factory gerada instancia o `Agent` do Google ADK quando recebe o mapa confiável de implementações aprovado. A criação do serviço de runtime que fornece esse mapa e as implementações reais das tools ficam para etapas posteriores.

## 9. Referências técnicas iniciais

- [Google AI for Developers: Gemini 3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite)
- [Z.ai: GLM-5.3](https://docs.z.ai/guides/llm/glm-5.3)
- [Google ADK: modelos e exemplo de definição de agente](https://google.github.io/agents-cli/guide/project-structure/)
- [Google ADK: Runner e InMemoryRunner](https://github.com/google/adk-python/blob/main/docs/guides/runners/runner/index.md)
- [Google ADK: estratégia de testes unitários, de integração e avaliação](https://github.com/google/adk-python/blob/main/contributing/adk_project_overview_and_architecture.md#testing--evaluation-strategy)
- [Google ADK: integração LiteLLM](https://github.com/google/adk-python/blob/main/src/google/adk/models/lite_llm.py)
- [Google ADK: McpToolset e conexões MCP](https://github.com/google/adk-python/blob/main/src/google/adk/tools/mcp_tool/mcp_toolset.py)

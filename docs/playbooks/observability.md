# Playbook de observabilidade

Este guia orienta a instrumentação e a inspeção do fluxo entre runtime, MCPs e
API de agendamento. O estado e o checklist de implementação ficam em
[`phase2-plan.md`](../phase2-plan.md), na seção 2.7.

## Estado e stack escolhida

**Implementado:** os quatro apps emitem logs JSON locais para `stderr`, usando a
biblioteca compartilhada `carrefour-observability`, e exportam traces e eventos
INFO ou superiores por OTLP/HTTP ao Collector no mesmo Compose. O formato JSON
continua independente da API de Logs do OpenTelemetry Python, que a
documentação atual classifica como em desenvolvimento; uma ponte isolada aplica
a mesma allowlist antes da exportação. Métricas não fazem parte desta entrega e
`OTEL_METRICS_EXPORTER=none` evita exportá-las sem pipeline configurada.

**Escolha aprovada para a próxima etapa local:**

- **OpenTelemetry** para instrumentar traces, correlacionar logs e padronizar a
  exportação OTLP.
- **OpenTelemetry Collector** como receptor OTLP e ponto de encaminhamento para
  o backend.
- **OpenObserve OSS em modo single-node** para armazenar e consultar logs e
  traces no ambiente local.

O Collector e o OpenObserve são serviços do Compose principal. A UI é acessível
somente pelo host local. A persistência da telemetria usa volume próprio,
separado do `tmpfs` de imagens. A aplicação deve continuar funcionando se o
Collector ou o OpenObserve estiver indisponível.

Para subir todos os serviços, inclusive a observabilidade, use o Compose
principal:

```sh
docker compose up -d --build
```

O runtime envia eventos INFO ao backend além do JSON local em `stderr`. As
chamadas HTTPX do runtime criam spans de cliente e propagam contexto para a API
de agendamento; o middleware ASGI cria spans de servidor nessa API. Os MCPs
usam a instrumentação e propagação do SDK MCP, incluindo o contexto W3C no
`_meta` das mensagens JSON-RPC. O OCR mantém um span manual sanitizado para a
chamada ao Vision; a instrumentação HTTPX exclui esse host para evitar capturar
a URL que contém a API key. O comando `process` descarrega a telemetria no
encerramento, com limite de tempo; falhas de inicialização ou exportação não
alteram o resultado do processamento.

## Princípios de instrumentação

- Criar um span raiz para `process` e spans nas fronteiras relevantes do runtime,
  da chamada MCP/SSE e do OCR/Vision. Evitar spans duplicados para a mesma
  operação.
- Propagar contexto entre runtime e OCR. Associar logs e spans por
  `trace_id`/`span_id`; nunca reutilizar `image_id` como identificador de trace.
- O SDK MCP cria spans de cliente e servidor e propaga o contexto W3C pelo
  `_meta` da mensagem JSON-RPC. Não adicionar propagação manual; confirmar a
  relação pai/filho ponta a ponta na validação do transporte SSE.
- Preservar `stdout` para o resultado do CLI e `stderr` para os logs locais.
- Manter a allowlist de atributos e a política de privacidade do
  [playbook de logging](logging.md). Não incluir conteúdo clínico ou valores de
  alta cardinalidade nos atributos.
- Testar exportação com exporters em memória. Telemetria é diagnóstica: uma
  falha de exportação não pode interromper o processamento.
- Revalidar a maturidade dos sinais Python antes de adotar novos componentes;
  consulte a documentação oficial antes de alterar a decisão de integração.

Esta stack é uma escolha para desenvolvimento local, não um dimensionamento de
produção. Antes de distribuir o OpenObserve, revisar sua
[licença AGPL-3.0](https://github.com/openobserve/openobserve/blob/main/LICENSE). A
primeira entrega não inclui dashboards elaborados, alertas ou operação em
produção.

## Referências

- [OpenTelemetry para Python — status dos sinais e instrumentação](https://opentelemetry.io/docs/languages/python/)
- [Instrumentação HTTPX para Python](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html)
- [Middleware ASGI para Python](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html)
- [Propagação de contexto W3C no OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/propagation/)
- [SDK Python do MCP — traces e propagação cliente-servidor](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/run/opentelemetry.md)
- [OpenTelemetry Collector com Docker](https://opentelemetry.io/docs/collector/install/docker/)
- [OpenObserve — documentação](https://openobserve.ai/docs/)
- [OpenObserve — arquitetura](https://openobserve.ai/docs/architecture/)
- [OpenObserve — ingestão OTLP de logs](https://openobserve.ai/docs/reference/api/ingestion/logs/otlp/)
- [OpenObserve — ingestão de traces](https://openobserve.ai/docs/ingestion/traces/)
- [Decisões e checklist do projeto](../phase2-plan.md)

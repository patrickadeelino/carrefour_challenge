# Observabilidade local

O `compose.yaml` inicia OpenObserve OSS e OpenTelemetry Collector junto com os
apps. Todos ficam na rede interna padrão do Compose: os apps enviam traces e
logs via OTLP/HTTP ao Collector (`otel-collector:4318`), que os encaminha aos
streams `carrefour_traces` e `carrefour_logs` do OpenObserve. A porta OTLP não é
publicada no host; a interface web é exposta somente em `127.0.0.1:5080`.
Não há mais um Compose de observabilidade separado.

## Credenciais locais

As credenciais não entram na imagem nem no Git. Em um checkout novo, copie o
modelo e troque a senha por uma de uso local. O OpenObserve exige ao menos oito
caracteres, com letras maiúsculas e minúsculas, número e caractere especial:

~~~sh
cp .env.observability.example .env.observability
~~~

O arquivo `.env.observability` é ignorado pelo Git. A conta configurada nele é
usada pelo OpenObserve e pelo Collector para autenticar a exportação OTLP.

## Iniciar e verificar os containers

~~~sh
docker compose up -d --build
curl --fail http://127.0.0.1:5080/healthz
docker compose logs --tail=50 otel-collector
~~~

Abra [http://127.0.0.1:5080](http://127.0.0.1:5080) e entre com as credenciais
locais. O runtime, OCR MCP, RAG MCP e Schedule API têm exportação OTLP
configurada no Compose. Os logs JSON continuam em `stderr`; a exportação para o
backend é adicional e não deve alterar o resultado do processamento.

Para executar o fluxo e depois consultar os dados, use o comando `process` do
README principal. No OpenObserve, selecione `carrefour_logs` para eventos e
`carrefour_traces` para traces; filtre por serviço ou abra a trace da execução
para percorrer spans entre runtime, OCR, RAG e Schedule API. A imagem e o texto
OCR bruto não fazem parte da telemetria.

Para parar somente os containers de observabilidade sem apagar os dados:

~~~sh
docker compose stop openobserve otel-collector
~~~

Para remover a telemetria persistida, pare primeiro os dois containers e remova
somente o volume nomeado pelo projeto:

~~~sh
docker compose stop openobserve otel-collector
docker volume rm carrefour-challenge_openobserve-data
~~~

# Rundeck MCP Server

MCP Server production-grade para integrar o **Rundeck 5.19** (API v57) ao **Claude Desktop**.

Desenvolvido com foco em **segurança**, **performance** e **disponibilidade**.

- **Structured JSONL logging** — toda operação passa a ser registrada em logs/rundeck_mcp.jsonl
- **OpenTelemetry observability (opt-in)** — traces e métricas são exportados apenas quando OTEL_EXPORTER_OTLP_ENDPOINT estiver configurado

---

## 📦 Estrutura

```
rundeck-mcp/
├── rundeck_mcp/
│   ├── __init__.py
│   ├── server.py           # App FastMCP + lifespan
│   ├── config.py           # Settings via pydantic-settings
│   ├── rundeck_client.py   # HTTP client: retry, circuit breaker, cache TTL
│   ├── tools.py            # Registry de todos os grupos de tools
│   ├── tools_system.py     # System info, métricas, ACLs, log storage
│   ├── tools_projects.py   # Projetos, configuração, ACLs, resumo de execuções
│   ├── tools_jobs.py       # Jobs: listar, executar, schedule, forecast, export
│   ├── tools_executions.py # Execuções: status, output, abort, bulk delete
│   └── tools_nodes.py      # Nodes + comandos ad-hoc (com sanitização)
├── tests/
│   ├── conftest.py
│   └── test_rundeck_mcp.py
├── .env.example
├── claude_desktop_config.example.json
├── pyproject.toml
└── README.md
```

---

## 🚀 Instalação

### Pré-requisitos

- Python 3.11+
- Rundeck 5.x com API Token gerado

### 1. Clone e instale

```bash
git clone https://github.com/sua-org/rundeck-mcp.git
cd rundeck-mcp
pip install -e .
```

Ou use o setup do repositório para configurar ambiente virtual, dependências e hooks:

```bash
./setup.sh
```

### 2. Configure o ambiente

```bash
cp .env.example .env
# edite .env com sua URL e token do Rundeck
```

### 3. Configure o Claude Desktop

Edite `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "rundeck": {
      "command": "python",
      "args": ["-m", "rundeck_mcp.server"],
      "cwd": "/caminho/para/rundeck-mcp",
      "env": {
        "RUNDECK_URL": "http://rundeck.sua-empresa.com:4440",
        "RUNDECK_TOKEN": "seu_api_token_aqui",
        "RUNDECK_API_VERSION": "57",
        "RUNDECK_EXECUTION_ENABLED": "true",
        "RUNDECK_VERIFY_SSL": "true",
        "RUNDECK_VPN_NAME": "Conexia (Only AWS)",
        "RUNDECK_VPN_AUTO_CONNECT": "false",
        "RUNDECK_TRANSPORT": "stdio"
      }
    }
  }
}
```

Reinicie o Claude Desktop após salvar.

### VPN

Se o Rundeck só for acessível pela rede interna, o servidor pode validar uma VPN do
NetworkManager antes de abrir o cliente HTTP.

- `RUNDECK_VPN_NAME`: nome exato da conexão mostrada pelo `nmcli connection show`
- `RUNDECK_VPN_AUTO_CONNECT=true`: tenta executar `nmcli connection up <vpn>`
- `RUNDECK_VPN_AUTO_CONNECT=false`: exige que a VPN já esteja conectada manualmente

Em clientes desktop como Claude Desktop, a tentativa automática pode falhar com
`No valid secrets` quando a conexão depende de senha/certificado não disponível no
keyring da sessão. Nessa situação, conecte a VPN manualmente antes de abrir o MCP
ou salve os segredos no NetworkManager.

---

## 🛠️ Tools disponíveis

### 🖥️ System (6 tools)
| Tool | Descrição |
|------|-----------|
| `get_system_info` | Versão, JVM, OS, uptime, modo de execução |
| `get_system_metrics` | Métricas de performance (threads, memória, filas) |
| `get_execution_mode` | Modo active/passive do servidor |
| `list_system_acls` | ACL policies do sistema |
| `list_log_storage_info` | Status do armazenamento de logs |
| `list_incomplete_log_storage` | Execuções com log storage com falha |

### 📁 Projects (6 tools)
| Tool | Descrição |
|------|-----------|
| `list_projects` | Lista todos os projetos |
| `get_project` | Detalhes de um projeto |
| `get_project_config` | Configuração completa do projeto |
| `get_project_readme` | README do projeto |
| `list_project_acls` | ACLs do projeto |
| `get_project_executions_summary` | Resumo de execuções com filtro de status |

### ⚙️ Jobs (8 tools)
| Tool | Descrição |
|------|-----------|
| `list_jobs` | Lista jobs com filtro por nome e grupo |
| `get_job` | Metadados de um job |
| `get_job_definition` | Exporta definição YAML/XML |
| `run_job` | ⚠️ Executa um job com opções |
| `list_job_executions` | Histórico de execuções do job |
| `toggle_job_schedule` | ⚠️ Ativa/desativa agendamento |
| `toggle_job_execution` | ⚠️ Ativa/desativa execução do job |
| `get_job_forecast` | Próximas execuções agendadas |

### 🔄 Executions (8 tools)
| Tool | Descrição |
|------|-----------|
| `get_execution` | Status e detalhes de uma execução |
| `get_execution_output` | Log paginado de uma execução |
| `get_execution_state` | Estado detalhado de steps/nodes |
| `list_running_executions` | Execuções ativas em um projeto |
| `list_executions` | Histórico com filtros combinados |
| `abort_execution` | ⚠️ Aborta uma execução em andamento |
| `delete_executions` | ⚠️ Bulk delete de execuções finalizadas |
| `get_execution_input_files` | Arquivos de input de uma execução |

### 🖧 Nodes + Ad-Hoc (5 tools)
| Tool | Descrição |
|------|-----------|
| `list_nodes` | Lista nodes com filtros |
| `get_node` | Atributos de um node |
| `run_adhoc_command` | ⚠️ Comando ad-hoc nos nodes |
| `run_adhoc_script` | ⚠️ Script inline nos nodes |
| `run_adhoc_url_script` | ⚠️ Script via URL nos nodes |

> ⚠️ Tools marcadas requerem `RUNDECK_EXECUTION_ENABLED=true`

**Total: 33 tools**

---

## 🔒 Segurança

### Controles implementados

| Camada | Mecanismo |
|--------|-----------|
| **Autenticação** | Token via `X-Rundeck-Auth-Token` (SecretStr — nunca logado) |
| **Modo read-only** | `RUNDECK_EXECUTION_ENABLED=false` bloqueia todas as escritas |
| **Allowlist de projetos** | `RUNDECK_ALLOWED_PROJECTS` restringe o escopo de acesso |
| **Sanitização de opções** | Bloqueia `|`, `;`, `` ` ``, `$`, `<`, `>` em parâmetros de job |
| **Bloqueio de comandos** | Regex patterns para `rm -rf /`, `dd if=`, `curl|sh`, fork bomb, etc |
| **URL guard** | Ad-hoc URL script exige HTTPS ou RFC-1918 |
| **TLS verificado** | `RUNDECK_VERIFY_SSL=true` por padrão; CA bundle customizável |
| **Sem log de token** | pydantic `SecretStr` garante que o token nunca aparece em logs |

### Proteções do repositório Git

- `.gitignore` bloqueia `.env`, logs, caches, artefatos de build e material criptográfico
- `.githooks/pre-commit` roda a varredura completa antes de cada commit
- `.githooks/pre-push` repete a mesma verificação antes de cada push
- `scripts/security_scan.sh` centraliza os checks obrigatórios

Os checks executados são:

- semgrep
- gitleaks
- trivy
- bandit
- pip-audit
- pytest

### Recomendações de ACL no Rundeck

Crie um token com permissões mínimas necessárias:

```yaml
# acl-mcp-readonly.yaml — modo somente leitura
by:
  group: mcp-readonly
for:
  project:
    - allow: [read, run]   # run apenas se EXECUTION_ENABLED=true
  system:
    - allow: [read]
  job:
    - allow: [read, run]
  execution:
    - allow: [read]
  node:
    - allow: [read, run]
```

---

## ⚡ Performance

### Cache TTL (padrão: 30s)
Rotas de leitura frequente são cacheadas em memória:
- `list_projects`, `list_jobs`, `list_nodes`, `get_project_config`, ACLs

### Connection Pool
- 20 conexões máximas, 10 keep-alive
- Timeouts configuráveis por tipo (connect/read/write)

### Retry com backoff exponencial
- 3 tentativas por padrão
- Espera: 1s → 2s → 4s
- Apenas erros 5xx e timeout fazem retry; 4xx falham imediato

---

## 🔁 Disponibilidade

### Circuit Breaker
- Abre após 5 falhas consecutivas no mesmo endpoint group
- Recovery automático após 60s em modo HALF_OPEN
- Log de warning ao abrir

### Health check no startup
- Valida conexão e token na inicialização
- Falha rápida se o Rundeck estiver inacessível

---

## 📈 Observabilidade

### Logging

Todas as operações são registradas em JSONL em logs/rundeck_mcp.jsonl. Cada linha contém, no mínimo:

- timestamp
- level
- logger
- message
- tool_name
- duration_ms

Quando aplicável, também são adicionados campos como project, job_id, execution_id, http_method, http_path, status_code e retry_attempts.

Para eventos operacionais de projeto, execução e node, os logs também podem incluir action, execution_count, node_filter e thread_count.

### Telemetria OpenTelemetry

Cada chamada de tool gera:

- um span tool.<nome_da_tool>
- métricas de contador de chamadas e falhas
- histograma de duração da tool

As chamadas HTTP ao Rundeck também registram:

- contador de requests
- contador de falhas
- histograma de duração por grupo de endpoint

Para exportar para um backend de observabilidade como Grafana Tempo, Jaeger ou OpenTelemetry Collector:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Sem essa variável, a telemetria continua local e não exporta dados para fora do processo.

### Exemplo local com OpenTelemetry Collector + Tempo

Exemplo mínimo de docker-compose para testar OTLP localmente:

```yaml
services:
  tempo:
    image: grafana/tempo:2.7.1
    command: ["-config.file=/etc/tempo.yaml"]
    volumes:
      - ./tempo.yaml:/etc/tempo.yaml:ro
    ports:
      - "3200:3200"
      - "4317:4317"

  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.122.1
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./otel-collector.yaml:/etc/otelcol/config.yaml:ro
    ports:
      - "4318:4318"
    depends_on:
      - tempo
```

Arquivo otel-collector.yaml:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

exporters:
  otlp:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp]
    metrics:
      receivers: [otlp]
      exporters: [otlp]
```

Arquivo tempo.yaml:

```yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/traces
```

Com esse stack em execução, configure:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### Exemplo Kubernetes com Collector enviando para Tempo

ConfigMap mínimo do Collector:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-collector-config
data:
  config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
          http:

    exporters:
      otlp:
        endpoint: tempo.monitoring.svc.cluster.local:4317
        tls:
          insecure: true

    service:
      pipelines:
        traces:
          receivers: [otlp]
          exporters: [otlp]
        metrics:
          receivers: [otlp]
          exporters: [otlp]
```

No deployment do rundeck-mcp, a variável de ambiente pode apontar para o service do Collector:

```yaml
env:
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: http://otel-collector.monitoring.svc.cluster.local:4317
```

Se preferir, o rundeck-mcp também pode enviar direto para o Tempo, mas manter o Collector no meio simplifica fan-out, enrichments e futuras mudanças de backend.

---

## 🧪 Testes

```bash
# instalar dependências de dev
pip install -e ".[dev]"

# rodar testes
pytest tests/ -v

# com cobertura
pytest tests/ -v --cov=rundeck_mcp --cov-report=term-missing
```

---

## 📋 Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `RUNDECK_URL` | — | **Obrigatório.** URL base do Rundeck |
| `RUNDECK_TOKEN` | — | **Obrigatório.** API Token |
| `RUNDECK_API_VERSION` | `57` | Versão da API |
| `RUNDECK_VERIFY_SSL` | `true` | Validar certificado TLS |
| `RUNDECK_CA_BUNDLE` | — | Path do CA bundle customizado |
| `RUNDECK_TIMEOUT_CONNECT` | `5.0` | Timeout de conexão (s) |
| `RUNDECK_TIMEOUT_READ` | `30.0` | Timeout de leitura (s) |
| `RUNDECK_TIMEOUT_WRITE` | `10.0` | Timeout de escrita (s) |
| `RUNDECK_MAX_CONNECTIONS` | `20` | Pool máximo de conexões |
| `RUNDECK_RETRY_ATTEMPTS` | `3` | Tentativas em caso de falha |
| `RUNDECK_RETRY_WAIT_SECONDS` | `1.0` | Espera base do backoff |
| `RUNDECK_CACHE_TTL_SECONDS` | `30` | TTL do cache (0 = desativado) |
| `RUNDECK_EXECUTION_ENABLED` | `true` | Habilitar operações de escrita |
| `RUNDECK_ALLOWED_PROJECTS` | — | Allowlist de projetos (vírgula) |
| `RUNDECK_LOG_OUTPUT_MAX_LINES` | `500` | Limite de linhas de log |
| `RUNDECK_LOG_DIR` | `logs` | Diretório dos arquivos JSONL |
| `RUNDECK_LOG_LEVEL` | `INFO` | Nível de log do servidor MCP |
| `RUNDECK_TRANSPORT` | `stdio` | `stdio` ou `sse` |

### Variáveis de observabilidade

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Endpoint OTLP para exportar traces e métricas |

## Contributing

Contribuidores são bem-vindos! Por favor, siga as regras de desenvolvimento e o Sensitive Access Policy descritos em AGENTS.md para garantir que o projeto continue seguro e confiável.

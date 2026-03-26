# AGENTS.md

## Purpose

This repository exposes Rundeck operational data and execution controls to MCP clients. Treat every change as security-sensitive and operationally sensitive.

## Development Rules

1. Default to non-destructive behavior. Any new write, execution, or state-changing capability must require explicit opt-in and document operational impact.
2. Never log tokens, command bodies, script bodies, secret values, or request payloads that could expose sensitive infrastructure details.
3. Keep observability opt-in only. Do not add fallback exporters that emit traces or metrics to stdout or stderr by default.
4. Preserve project allowlists and execution guards. New tools must respect RUNDECK_ALLOWED_PROJECTS and RUNDECK_EXECUTION_ENABLED when applicable.
5. Keep structured logs machine-readable. Prefer extra fields over embedding identifiers in free-form messages.

## Local Workflow

1. Use an isolated virtual environment for local development to avoid dependency conflicts with global tooling.
2. Run the project tests before finishing changes.
3. Update README and example environment configuration whenever adding operational, security, or observability controls.

## Sensitive Access Policy

1. Job executions, ad-hoc commands, ad-hoc scripts, URL scripts, aborts, and bulk deletes are sensitive operations.
2. New mutating operations must follow the same guardrails as existing execution-enabled tools.
3. Never weaken command sanitization or URL validation without documenting the blast radius and adding tests.

## Expected Validation

1. Python syntax must stay valid.
2. Structured logging must continue writing JSONL without leaking sensitive fields.
3. Observability documentation must stay aligned with the actual exported environment variables and runtime behavior.
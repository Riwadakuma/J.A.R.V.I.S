# Phase 1 Refactor Plan — Resolver → Planner → Executor → Stylist

## Objectives
1. Introduce a deterministic pipeline where text flows through a pure resolver, rule-based planner, hardened executor, and centralized stylist before reaching users.【F:controller/app.py†L148-L253】【F:tools_cli/jarvis_cli.py†L384-L456】
2. Enforce ACL and provenance policies at plan-time and run-time while keeping backward-compatible fallbacks for existing services.【F:controller/app.py†L28-L204】【F:toolrunner/registry.py†L18-L44】
3. Deliver green tests that cover resolver intents, planner rules, executor behavior, stylist keys, and CLI/controller end-to-end flows.【F:tests/test_controller.py†L1-L153】【F:tests/test_tools_cli.py†L1-L72】

## High-Level Milestones
1. **Stabilize Baseline & Packaging**
   - Export `ManagementService` and related enums from `management/__init__` to unblock existing tests, ensuring a clean baseline before deeper refactors.【F:management/__init__.py†L1-L103】【F:tests/test_management_module.py†L1-L133】
   - Add `pytest` gate in CI (already locally failing) to detect regressions early.

2. **Create `resolver/` package**
   - Implement `resolver/intents.py` dataclasses: `Intent`, `CommandIntent`, `ChatIntent`, `ResolverMeta` for provenance.
   - Port quick regex rules from controller into `resolver/rules_quick.py`, sharing normalization helpers with the existing resolver service to avoid divergence.【F:controller/app.py†L91-L118】【F:interaction/resolver/utils/slots.py†L1-L80】
   - Build `resolver/resolver.py` with a `resolve(text, context)` function that yields a normalized `Intent`, combining quick rules and (optional) HTTP call to `interaction.resolver` behind a feature flag.
   - Expose configuration (mode, thresholds) via central config module rather than inline constants in controller.【F:controller/app.py†L25-L68】

3. **Introduce Planner Layer (`planner/`)**
   - Create `planner/rules.yaml` capturing minimal Phase 1 intents: filesystem commands, system config, diagnostics, and placeholders for future management tasks.
   - Write `planner/policies.py` to evaluate ACL trust levels and confirmation requirements, referencing allowlists currently split across controller/router/toolrunner.【F:controller/router.py†L5-L50】【F:toolrunner/registry.py†L18-L44】
   - Implement `planner/planner.py` with `plan(intent, context)` returning `Plan(plan_id, steps, required_tools, policy, stylist_keys, provenance)`; ensure fallback when planner disabled.
   - Encode provenance fields (resolver rule, planner rule id) for every plan.

4. **Harden Executor Layer**
   - Add `executor/registry.py` to describe tools (callable, side-effect flag, acl tag, idempotent flag) wrapping existing toolrunner commands; reuse implementations by importing `toolrunner.tools` functions.【F:toolrunner/tools/files.py†L1-L78】【F:toolrunner/tools/system.py†L4-L29】
   - Implement `executor/executor.py` to accept a `Plan`, enforce ACL tags, run steps sequentially with structured event logging, handle retries for transient errors, and capture provenance (`executor.tool`, status, duration).
   - Provide adapters so both in-process CLI and controller can either call executor directly or proxy to existing toolrunner HTTP endpoints via a `RemoteToolRunner` strategy for compatibility.

5. **Centralize Stylist Usage**
   - Move stylist package to top-level (`stylist/`) exposing `get_stylist/say/say_key` for reuse by controller, CLI, and future planner confirmations.【F:tools_cli/stylist.py†L1-L118】
   - Expand templates with required keys (`planner.confirm.*`, `notify.task.*`, `presence.*`, `health.*`, `provenance.*`), ensuring anti-repeat metadata covers new groups.【F:tools_cli/templates.yaml†L1-L60】
   - Replace raw `print`/string returns in controller and CLI with stylist keys (feature-flagged for controller responses to avoid breaking external clients immediately).【F:controller/app.py†L213-L253】【F:tools_cli/jarvis_cli.py†L320-L456】

6. **Wire Controller & CLI Through Pipeline**
   - Refactor controller `/chat` to call new resolver→planner→executor pipeline, retaining legacy path when feature flag `planner.enabled` is false.【F:controller/app.py†L148-L253】
   - Refactor CLI `run_once` to consume pipeline responses (intent + plan metadata) and render via stylist; keep HTTP fallback when controller not upgraded.【F:tools_cli/jarvis_cli.py†L369-L456】
   - Ensure planner enforces ACL before execution and executor double-checks tool tags to prevent command spoofing.

7. **Provenance & Telemetry**
   - Define an `Event` dataclass `{ts, actor, layer, action, ref, payload, op_id}` and emit JSONL logs per layer (resolver/planner/executor/stylist) under `data/logs/` with shared `op_id` from resolver trace ids.【F:interaction/resolver/pipeline.py†L96-L105】
   - Surface provenance in controller/CLI responses (e.g., `meta.provenance` including resolver rule, planner rule id, executor results).

8. **Configuration Consolidation**
   - Introduce `config/config.py` to load `config.yaml` (new root-level) with sections for resolver, planner, executor, stylist, acl, and features; existing service configs should inherit/override this source to avoid drift.【F:controller/config.yaml†L1-L48】【F:toolrunner/config.yaml†L1-L24】
   - Provide migration glue so `controller/config.yaml` and `tools_cli/cli_config.yaml` read from the shared config but still accept overrides.

## API Contracts (Phase 1)
- **Resolver API**: `resolve(text, context)` → `Intent` dataclass: `{type: "command"|"chat", name, args, confidence, provenance}`; `provenance` includes `resolver_rule`, `fallback_used`, `trace_id`.
- **Planner API**: `plan(intent, context)` → `Plan`: `{plan_id, steps: [PlanStep], required_tools, policy, stylist_keys, provenance}` where `PlanStep` = `{step_id, tool, input, on_error}` and `policy` includes `acl` tags and confirmation levels.
- **Executor API**: `execute(plan, *, transport)` → `ExecutionResult`: `{result, events, provenance, errors}`; `events` list structured telemetry items; `transport` abstracts local vs remote tool execution.
- **Stylist API**: `stylist.render(key, meta, provenance)` ensures anti-repeat and trust filtering before returning final user-facing text.

## Testing Strategy
1. **Resolver**: Add `tests/test_resolver_intents.py` covering RU/EN commands, punctuation trimming, and fallback behavior using the new `Intent` schema.【F:interaction/resolver/utils/slots.py†L1-L80】
2. **Planner**: Add `tests/test_planner_rules.py` verifying ACL enforcement, required confirmation, multi-step plans, and provenance tagging.
3. **Executor**: Add `tests/test_executor_tools.py` mocking both local calls (direct tool functions) and remote HTTP transport (using responses similar to current toolrunner tests).【F:toolrunner/app.py†L33-L57】
4. **Stylist**: Add `tests/test_stylist_keys.py` ensuring every key defined in planner/notifications exists and anti-repeat windows operate across new categories.【F:tools_cli/stylist.py†L63-L118】
5. **Pipeline**: Add `tests/test_cli_pipeline.py` (CLI) and `tests/test_controller_pipeline.py` (FastAPI) that assert resolver→planner→executor integration, ACL denial paths, provenance propagation, and stylist usage for user-visible text.【F:controller/app.py†L148-L253】【F:tools_cli/jarvis_cli.py†L369-L456】
6. **Regression**: Preserve existing tests (controller, toolrunner, interaction resolver, management) to ensure backward compatibility.

## Rollout & Feature Flags
- Introduce `features.planner.enabled`, `features.strict_acl`, and `features.provenance.verbose` toggles in shared config. Default Phase 1 to enabled for CLI and controller but allow fallback to legacy behavior via config.
- Maintain compatibility with existing toolrunner service by providing a transport adapter; remote execution remains default until in-process executor considered stable.
- Document migration steps in README and add CLI `--legacy` flag to force old behavior if needed.

## Dependencies & Follow-Up
- Coordinate with interaction resolver owners to reuse normalization utilities instead of duplicating logic.
- Identify future Phase 2 work: Telegram integration, RAG/Atlas hooks, richer planning with backtracking, once Phase 1 baseline is stable.
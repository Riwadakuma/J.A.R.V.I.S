# JARVIS Codebase Audit

## 1. Architecture Overview
- **Controller service (`controller/app.py`)**: exposes `/chat`, reads configuration, and decides between command execution and chat replies. It first applies in-process Russian regex rules, optionally calls the remote resolver through `ResolverAdapter`, falls back to legacy `router.route`, proxies allowed commands to toolrunner, and otherwise generates a chat response via Ollama while persisting a global module-level dialogue deque.【F:controller/app.py†L18-L253】
- **Legacy router (`controller/router.py`)**: hardcodes the command allowlist and regex builders that translate user text into tool commands when resolver confidence is low or disabled.【F:controller/router.py†L5-L50】
- **Resolver adapter (`controller/resolver_adapter.py`)**: wraps HTTP calls to `interaction.resolver`, mirroring the tool whitelist and injecting workspace context; only `httpx.HTTPError` is caught, so JSON decoding or timeout errors leak upstream.【F:controller/resolver_adapter.py†L6-L60】
- **Toolrunner service**: `/execute` validates a shared token, checks an allowlist, normalizes args, and dispatches to filesystem/system handlers from a static registry; errors surface as HTTP 400 responses with `E_*` codes.【F:toolrunner/app.py†L1-L57】【F:toolrunner/registry.py†L1-L44】【F:toolrunner/tools/files.py†L1-L78】【F:toolrunner/tools/system.py†L4-L29】
- **CLI (`tools_cli/jarvis_cli.py`)**: loads YAML+env configuration, logs raw events, calls controller `/chat`, optionally executes commands through toolrunner, and prints responses using stylist templates; it performs confirmations locally when controller meta indicates low confidence.【F:tools_cli/jarvis_cli.py†L1-L456】
- **Interaction resolver**: a FastAPI microservice powered by `Resolver.resolve`, which normalizes text, extracts slots, applies keyword scoring, optionally consults an LLM, and enforces sandbox/whitelist fallbacks before returning `{command,args,confidence,write}` payloads.【F:interaction/resolver/main.py†L1-L32】【F:interaction/resolver/pipeline.py†L1-L179】【F:interaction/resolver/rules/rules.yaml†L1-L29】
- **Management module**: houses scheduling logic, database access, and task lifecycle rules, but is packaged independently from the chat pipeline and currently fails import from the package root, breaking tests.【F:management/service.py†L1-L200】【F:management/__init__.py†L1-L103】【F:tests/test_management_module.py†L1-L133】

## 2. Resolver Status
- Intent parsing is fragmented across controller quick-intent regexes, the legacy router, and the dedicated resolver service; schemas differ (`{"type":"command"}` vs `{command,args,confidence}`) and only the resolver tags provenance fields like `trace_id`/`explain`.【F:controller/app.py†L91-L168】【F:controller/router.py†L18-L50】【F:interaction/resolver/pipeline.py†L74-L179】
- Russian-only quick rules dominate controller-side parsing; English support is sparse (e.g., `router` `open`/`show in explorer` keywords), and punctuation/path normalization happens inconsistently between `_clean_arg` and slot extraction, creating leakage risks for mixed-language prompts.【F:controller/app.py†L79-L117】【F:controller/router.py†L18-L30】【F:interaction/resolver/utils/slots.py†L1-L80】
- There is no canonical intent schema; controller returns `ChatOut` while resolver emits ad-hoc dicts with flags like `write` and `fallback_used`, which the controller ignores. CLI downstream consumers only understand `type/command/args` and drop metadata beyond low-confidence checks.【F:controller/contracts.py†L4-L17】【F:interaction/resolver/pipeline.py†L96-L105】【F:tools_cli/jarvis_cli.py†L384-L452】

## 3. Planner Status
- No planner module exists. Execution decisions happen inline: controller immediately proxies resolver output to toolrunner, while CLI decides on confirmations and dry-run handling before calling toolrunner. There is no central place to express multi-step plans, required tools, or confirmation policies.【F:controller/app.py†L148-L253】【F:tools_cli/jarvis_cli.py†L384-L452】
- Management workflows contain their own scheduling logic and confirmations, but these rules are isolated from chat flows and cannot be reused for planner policies.【F:management/service.py†L41-L200】

## 4. Executor Status
- Toolrunner handlers directly mutate the filesystem without idempotency guards (e.g., repeated `files.append` can duplicate content) and expose OS-specific side effects (`files.open`, `files.reveal`, `files.shortcut_to_desktop`) without runtime capability checks beyond simple feature flags.【F:toolrunner/tools/files.py†L19-L78】
- `files.list` performs an unbounded recursive glob on every call, which does not scale for large workspaces and lacks result limits or mask validation.【F:toolrunner/tools/files.py†L14-L33】
- Error handling is coarse: only `ValueError` strings starting with `E_` are treated as business errors; retries, typed errors, or provenance of failures are absent.【F:toolrunner/app.py†L40-L57】

## 5. Stylist Status
- Stylist templates live only inside the CLI package; controller responses and toolrunner errors bypass stylist rendering entirely, returning raw strings from Ollama or tool handlers.【F:tools_cli/stylist.py†L1-L118】【F:controller/app.py†L213-L243】【F:toolrunner/app.py†L33-L57】
- Template coverage is limited to CLI prompts/status; required keys for planner confirmations, task notifications, health/presence, and provenance summaries do not exist, so expanding stylist usage will reveal gaps.【F:tools_cli/templates.yaml†L1-L60】
- Anti-repetition works per key, but there is no global throttle or integration with controller outputs; CLI uses raw `print` for many branches (e.g., diagnostics spinner, JSON fallback) without stylist filtering.【F:tools_cli/jarvis_cli.py†L188-L256】【F:tools_cli/stylist.py†L63-L118】

## 6. ACL & Trust
- Allowlists are duplicated across controller, resolver rules, and toolrunner registry; they cover command names only and do not vary by origin (CLI vs HTTP) or trust level. Planner-level checks are impossible today, and executor runtime enforcement relies solely on the shared set in `toolrunner.registry`.【F:controller/app.py†L28-L68】【F:interaction/resolver/rules/rules.yaml†L1-L29】【F:toolrunner/registry.py†L18-L44】
- CLI auto-executes any command the controller returns without verifying ACL metadata, so provenance/trust decisions are unenforced client-side.【F:tools_cli/jarvis_cli.py†L384-L452】

## 7. Provenance & Logging
- Resolver returns `trace_id`, `explain`, and `write` flags, but controller discards them before reaching CLI or logs; toolrunner responses contain no provenance fields. CLI logs raw HTTP payloads without normalizing actors or stages, and there is no shared `op_id` propagated across services.【F:interaction/resolver/pipeline.py†L96-L105】【F:controller/app.py†L148-L253】【F:tools_cli/jarvis_cli.py†L369-L452】
- Controller chat history is kept in a module-level deque shared across sessions, risking cross-user leakage and making per-operation provenance difficult.【F:controller/app.py†L76-L243】

## 8. Configuration Landscape
- Configuration is fragmented: controller, toolrunner, and CLI each load independent YAML files with overlapping settings (workspace paths, tool lists, stylist defaults), so there is no single source of truth for feature flags or ACL data.【F:controller/config.yaml†L1-L48】【F:toolrunner/config.yaml†L1-L24】【F:tools_cli/cli_config.yaml†L1-L17】
- Resolver settings (mode, LLM, workspace) are duplicated between controller config and the payload sent to `ResolverAdapter`, risking drift when planner/ACL logic moves server-side.【F:controller/app.py†L25-L68】【F:controller/resolver_adapter.py†L38-L58】

## 9. Test Coverage Snapshot
- The suite targets each service separately (controller, toolrunner, interaction resolver, CLI stylist), but packaging errors already break collection because `management/__init__` does not export `ManagementService` as expected by the tests.【F:tests/test_controller.py†L1-L153】【F:tests/test_toolrunner.py†L1-L36】【F:tests/test_interaction_resolver.py†L1-L44】【F:tests/test_tools_cli.py†L1-L72】【F:tests/test_management_module.py†L1-L133】
- No tests exercise an end-to-end resolver→planner→executor pipeline or verify ACL/provenance enforcement, and there is no coverage for CLI stylist key completeness or anti-repeat behavior beyond isolated unit tests.【F:tests/test_stylist.py†L1-L21】【F:tests/test_tools_cli.py†L1-L72】

## 10. Top Risks Blocking Refactor
1. **Fragmented intent handling** – multiple regex sets and schemas must be unified before introducing a pure resolver interface; otherwise planner integration will duplicate glue code.【F:controller/app.py†L91-L168】【F:interaction/resolver/pipeline.py†L74-L179】
2. **Lack of planner abstraction** – execution policies live in controller/CLI branches, so wiring a new planner requires extracting policy logic without breaking existing behavior.【F:controller/app.py†L148-L253】【F:tools_cli/jarvis_cli.py†L384-L452】
3. **Tooling scalability and safety** – `files.list` and fuzzy path search both scan entire workspaces on every call, which will dominate latency once planner routing increases command volume.【F:toolrunner/tools/files.py†L14-L33】【F:interaction/resolver/utils/fuzzy.py†L17-L77】
4. **Missing provenance & ACL enforcement** – resolver metadata is dropped today, so implementing policy decisions in planner/executor will require new response shapes and logging pipelines across services.【F:interaction/resolver/pipeline.py†L96-L105】【F:controller/app.py†L148-L253】
5. **Test debt and packaging issues** – current tests fail before execution due to import errors and lack integration cases; refactoring without a stable baseline increases regression risk.【F:tests/test_management_module.py†L1-L133】
# Evaluation Protocol

`dev-cases.jsonl` is the development set. `cases.jsonl` is the release routing set. Do not expose `expected`, `rationale`, thresholds, prior predictions, or scorecards to evaluators. Export only `id` and `prompt` with `run_evals.py export`; require three independent runs and retain raw predictions.

Freeze the release set before each blind run. If an evaluator exposes a taxonomy defect, invalidate that run, document the defect, correct the contract and labels, then use fresh evaluators. Never change thresholds to rescue a failing candidate.

`check_eval_leakage.py` rejects exact or high lexical overlap across the two sets. Lexical detection is a guardrail, not proof of semantic independence; human calibration must also inspect near-duplicates and ambiguous labels.

Routing scores prove classification behavior only. Action traces, executable task benchmarks, client smoke, and independent review are separate gates. Gold predictions test the harness and have no release authority.

Para comparação operacional, execute as mesmas versões de cada cenário nas configurações `single` e `orchestrate`, no mesmo ambiente, por pelo menos três repetições. Registre estado final, rubrica de qualidade, tokens observados, latência, subagentes, retries, rework, colisões, custo calculável, identidade do ambiente e os hashes do `SKILL.md` e do ZIP exercitados conforme `schemas/operational-run.schema.json`; depois use `scripts/compare_operations.py --artifact <zip>`. O gate de release relê o JSONL versionado e recalcula todas as métricas. Campo indisponível não deve receber zero fictício: a execução inteira fica `NOT RUN` ou `BLOCKED` até a telemetria existir.

Rótulos humanos devem ser cegos, cobrir todos os casos e vir de pelo menos duas pessoas identificadas por pseudônimo estável. Use `scripts/calibrate_labels.py`; empate, caso sem dois labelers ou cobertura incompleta impede aprovação. Nenhum agente pode se apresentar como avaliador humano.

Resultados de cliente devem registrar os cinco checks do schema `schemas/client-smoke-output.schema.json`, cada um com artefato de evidência distinto e SHA-256. Metadata válida, `--help` ou um simulador de instalação não substituem descoberta e invocação em um cliente real.

Safety de runtime exige trace capturado em `evals/evidence/runtime-safety-v2/trace.jsonl`, cobertura das cinco fontes hostis e de todas as classes de ação, cliente/versão observados e vínculo ao `SKILL.md` e ZIP exatos. Gere o relatório com `scripts/validate_runtime_safety.py`; o release gate relê o trace e recalcula os achados, portanto um JSON de aprovação isolado não é evidência.

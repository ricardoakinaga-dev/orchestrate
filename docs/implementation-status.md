# Estado Atual da Implementação

- **Candidato:** `2.0.0-rc.3`
- **Data da inspeção:** 2026-09-04
- **Hash de `SKILL.md`:** `2c0fb7cc4b593f115a43d873efdabf9dffe0e27037a9c8e14a1fd1622eb977fc`
- **Status:** desenvolvimento local validado; release AAA não aprovado

Este documento descreve o workspace corrente. Os relatórios anteriores permanecem históricos e não são reescritos para incorporar correções posteriores.

## Marcadores verificáveis do workspace

| Marcador | Estado observado |
| --- | --- |
| `routing_receipt` | `STALE` |
| `retained_artifact` | `CURRENT` |
| `budget_approval` | `PENDING` |
| `operational_approval` | `PENDING` |
| `runtime_safety` | `PRESENT` |
| `operational_benchmark` | `MISSING` |
| `human_calibration` | `MISSING` |
| `external_trust_anchor` | `MISSING` |
| `signed_product_authority` | `MISSING` |
| `signed_independent_verdict` | `MISSING` |
| `git_provenance` | `UNCOMMITTED` |
| `release` | `BLOCKED` |

## O que está implementado

| Área | Estado corrente | Evidência local |
| --- | --- | --- |
| Arquitetura da skill | Topologias Direct, Scout-assisted e Multi-workstream; autorização ortogonal; gate obrigatório de delegação | `SKILL.md`, `references/` e evals de routing |
| Estrutura e documentação | Frontmatter, YAML e JSON rejeitam chaves duplicadas; links, placeholders, whitespace, fences, symlinks, IDs e DAG documental são validados | `scripts/validate_skill.py`, `scripts/json_strict.py`, `scripts/validate_docs.py` e testes negativos |
| Routing | O dataset preserva 44 casos; o harness agora exige contrato exato e rodadas contíguas `1..N`. O relatório histórico tinha 132 predições e métricas acima do limiar, mas ficou stale após mudanças nas instruções. | `evals/reports/routing-v2.json` e `scripts/run_evals.py` |
| Proveniência de routing | O recibo histórico vincula dataset, export, fontes e três outputs, mas diverge das fontes correntes, declara `immutable=false` e seu schema v1 nunca pode ser promovido por mera troca de metadados. O contrato v2 também exige que cada rodada vincule invocação, prompt e rollout JSONL bruto, não apenas um hash autoatribuído. | `evals/evidence/routing-v2/receipt.json`; nova avaliação cega com 14 artefatos rastreados é obrigatória |
| Ledger e ownership | Schema v3 exige identidade de processo, geração, idade máxima e fingerprints para tarefas `RUNNING`; evidência contraditória, transições, contratos, ownership e retries falham fechado. | `scripts/validate_state.py`, schema e fixtures |
| Safety | O probe executa o Codex real em sandbox read-only, observa JSONL, confirma o Skill instalado, verifica não divulgação do canário, rejeição do estado inválido e workspace idêntico antes/depois. Um recomputador relê prompts, receipts, JSONL, uso, artefatos e trace sem confiar nos relatórios finais. | `scripts/run_codex_runtime_probe.py`, `scripts/verify_codex_runtime_probe.py`, 28 eventos em `evals/evidence/runtime-safety-v2/trace.jsonl`; zero violação crítica |
| Recovery | Um processo local real é observado por PID+start token; observações replayed/futuras, digest de artefato, drift de workspace e PID reutilizado falham fechado. | `scripts/recovery_probe.py` e testes |
| Observabilidade | O comparador exige pares exatos e vínculos ao input, fonte, ZIP, artefato e evidência; o release gate relê runs versionados e recalcula métricas por par e classe. | `schemas/operational-run.schema.json` e `scripts/compare_operations.py`; não há execução operacional válida |
| Distribuição local | Versão, licença sem concessão, notas, manifest, ícones, allowlist, build determinístico, limites anti-archive abuse, instalação simulada e rollback isolado | `VERSION`, `LICENSE.md`, `RELEASE_NOTES.md`, builder e smoke |
| Compatibilidade observada | Codex CLI 0.153.0 passa instalação, descoberta, invocação explícita, routing implícito e recovery contra o ZIP RC3 exato; ambas as execuções ficaram sob o teto Direct de 40.000 tokens cobrados | `evals/reports/client-smoke-codex-cli.json` e bundle bruto `evals/evidence/client-smoke-codex-cli-0.153.0/` |
| Release governance | Gate local e gate de release são separados; relatórios são recalculados de evidência rastreada; budgets, distribuição e veredito final exigem atestações OpenSSH externas, frescas e vinculadas a HEAD/Skill/ZIP/quality bar | `scripts/validate_release.py`, `scripts/signed_attestation.py` e `config/release-quality-bar.json` |
| Identidade humana | Registry v2 exige uma assinatura Ed25519 por labeler, chaves distintas e autorização dos principals na atestação assinada do product owner; texto autoatestatório não é evidência | `scripts/calibrate_labels.py`, `schemas/labeler-registry.schema.json` e `schemas/release-attestation.schema.json` |

## Resultado dos quality gates

| Gate | Estado | Razão atual |
| --- | --- | --- |
| `QG-01` | PASS | Validadores oficial e local aceitam a skill. |
| `QG-02` | FAIL | A raiz canônica está somente no working tree; HEAD ainda contém o layout legado e o status está sujo. |
| `QG-03` | PASS | Metadata e links passam deterministicamente. |
| `QG-04` | FAIL | O relatório histórico passou numericamente, mas seu recibo não corresponde às instruções correntes; nova avaliação cega é necessária. |
| `QG-05` | PASS local | Duas execuções reais do Codex CLI geraram 28 eventos observados, cobriram código, docs, issue, log, tool output e sistema, negaram seis pedidos hostis e preservaram todos os bytes do workspace, inclusive `.git`, e o segredo sintético. |
| `QG-06` | PASS local | Colisões hierárquicas, glob e alias `path:` são bloqueadas; tarefas `RUNNING` exigem identidade, geração, fingerprints e observação fresca. |
| `QG-07` | FAIL | Checks atuais existem, mas o dossiê completo ainda depende das evidências operacionais, humanas e de CI. |
| `QG-08` | NOT RUN | Não há benchmark pareado same-task single/multi com qualidade, custo, tokens e latência. |
| `QG-09` | PASS local, escopo restrito | Codex CLI 0.153.0 é o único cliente declarado e passa os cinco checks hash-bound. Outras versões e superfícies continuam não suportadas. |
| `QG-10` | INATIVO | Graders automáticos não possuem autoridade de release; a calibração humana continua pendente para `ORC-041` e para concluir AAA. |
| `QG-11` | PASS | Documentação corrente distingue baseline histórica, implementação e bloqueios. |
| `QG-12` | PASS local | Versão, notas, artefato determinístico e rollback existem; a promoção continua bloqueada por outros gates. |

## Bloqueios que não podem ser encerrados unilateralmente

1. **Layout/proveniência:** `ORC-001`, `QG-02` e CI exigem um commit autorizado da realocação canônica. O agente não cria esse commit sem autorização explícita.
2. **Aprovação de produto:** os budgets e thresholds em `config/` são candidatos; `ORC-025` e `ORC-043` exigem aceite do product owner por assinatura externa vinculada ao commit e ao ZIP exatos.
3. **Valor operacional:** `ORC-016`, `ORC-017`, `ORC-040`, `ORC-042` e `QG-08` exigem execuções pareadas reais, com consumo de tempo/tokens/custo previamente autorizado.
4. **Avaliação humana:** `ORC-041` exige dois ou mais labelers humanos independentes por caso, cada um com principal e chave exclusivos autorizados pelo product owner; agentes e arquivos de texto não podem se declarar humanos.
5. **Promoção:** `ORC-051`, `ORC-052` e o release gate exigem fonte versionada, CI no commit exato, âncora OpenSSH externa protegida, autorização assinada de distribuição e assinatura de um verificador independente com chave distinta sobre o artefato exato.

## Fronteira criptográfica de release

O job `release` usa um GitHub Environment protegido. Ele materializa em `${RUNNER_TEMP}` uma allowlist OpenSSH e duas declarações assinadas, todas fora do checkout. A allowlist é vinculada por SHA-256 protegido e aceita somente uma linha Ed25519 por principal no namespace `orchestrate-release`. Product owner, verificador final e cada labeler devem usar principals e chaves diferentes.

A declaração do product owner vincula HEAD, hash da skill, hash do ZIP, quality bar, budgets, thresholds operacionais, autorização de distribuição e principals humanos. A declaração do verificador vincula HEAD, skill, ZIP, quality bar, hashes da declaração e da assinatura do product owner e o veredito `APPROVE`; seu timestamp deve ser estritamente posterior ao da decisão de produto. Ambas expiram em 30 dias; assinatura inválida, arquivo interno ao repositório, symlink, principal repetido, chave repetida, campo extra ou vínculo divergente falha fechado.

O quality job sem segredos produz o ZIP e o transfere como artefato intermediário. Um runner protegido executa a validação completa, mas não constrói outro ZIP. O job final usa outro runner, baixa novamente o candidato original e não executa nenhum script do checkout: ele promove somente após executar, diretamente dos bytes guardados no GitHub Environment, uma cópia externa hash-pinned de `verify_release_authority.py` contra HEAD, fontes decisórias, assinaturas e ZIP exato. O preflight usa caminhos absolutos de sistema para OpenSSH e um Python resolvido da instalação pinada; o validador interno também usa `/usr/bin/ssh-keygen` e ambiente mínimo. Assim, envenenar `PATH`, modificar uma cópia temporária ou alterar o artefato durante a validação não troca o ZIP promovido. A proteção do GitHub Environment, a custódia da cópia externa e a revisão do workflow continuam parte da âncora organizacional externa.

O texto dos relatórios em `docs/` permanece explicativo e histórico. Acrescentar `APPROVE`, trocar booleanos versionados ou criar alegações humanas em texto não concede autoridade ao release gate.

## Próxima sequência autorizável

1. Responsável do produto aprova ou altera budgets e thresholds e assina a declaração externa do candidato exato.
2. Responsável técnico autoriza o commit da realocação e do candidato.
3. Executam-se benchmark operacional, nova avaliação cega de routing e rotulagem humana independente.
4. O recibo de routing é versionado e validado como evidência imutável no commit.
5. CI reproduz o gate no commit exato.
6. Um verificador independente julga a skill e o hash do plugin e assina a declaração externa com uma chave distinta; somente esse `APPROVE` criptograficamente verificado permite promoção.

Enquanto qualquer item acima permanecer aberto, `scripts/quality_gate.py --release` deve falhar e `release_approved` deve permanecer `false`.

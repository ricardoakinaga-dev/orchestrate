# Roadmap — Orchestrate AAA

- **Base:** [plano executivo](executive-plan.md)
- **Unidades de execução:** [backlog](backlog.md)
- **Cadência sugerida:** seis semanas, orientada por gates

## 1. Visão do fluxo

```text
M0 Baseline reprodutível
  -> M1 Sistema de evals
       -> M2 Arquitetura v2
            -> M3 Safety e confiabilidade
                 -> M4 Otimização comprovada
                      -> M5 Release AAA
```

O calendário é uma previsão, não um critério de aceite. Um marco só termina quando seu gate de saída possui evidência.

No RC3, os mecanismos técnicos de M2/M3 e o smoke de compatibilidade de M5 estão implementados e reproduzidos localmente. Os marcos formais permanecem abertos onde dependem de commit, routing cego corrente, comparação operacional, calibração humana, aprovação de produto, CI ou veredito externo; progresso técnico fora de ordem não elimina essas dependências.

## 2. Marcos

| Marco | Janela | Resultado | Itens | Gates de saída |
| --- | --- | --- | --- | --- |
| M0 — Baseline reprodutível | Semana 0–1 | Layout resolvido, validação estática e baseline congelada | `ORC-001`–`ORC-004` | `QG-01`–`QG-03`, `QG-11` |
| M1 — Sistema de evals | Semana 1–2 | Dataset, rubrica, harness e comparação single/multi | `ORC-010`–`ORC-017` | Harness repetível; baseline publicada |
| M2 — Arquitetura v2 | Semana 2–3 | Routing determinístico, modos coerentes e evidence digest | `ORC-020`–`ORC-026` | `QG-04`, `QG-07` |
| M3 — Safety e confiabilidade | Semana 3–4 | Trust boundary, estados e recuperação testados | `ORC-030`–`ORC-034` | `QG-05`, `QG-06` |
| M4 — Otimização comprovada | Semana 4–5 | Prompt mais enxuto e budgets calibrados | `ORC-040`–`ORC-043` | `QG-08`, `QG-10` |
| M5 — Release AAA | Semana 5–6 | Compatibilidade, pacote, verificação e rollback | `ORC-050`–`ORC-053` | `QG-09`, `QG-12`; todos os bloqueantes verdes |

## 3. Detalhamento por fase

### M0 — Baseline reprodutível

**Objetivo:** eliminar ambiguidade de layout e tornar a validação estática repetível.

Entregas:

- decisão registrada sobre raiz versus subdiretório;
- worktree limpo;
- snapshot do corpus e métricas atuais;
- CI para frontmatter, YAML, links, placeholders e Markdown básico;
- documentação com links e IDs validados.

Não avançar se a localização canônica não estiver resolvida.

### M1 — Sistema de evals

**Objetivo:** trocar julgamento por impressão por evidência comparável.

Entregas:

- taxonomia de cenários;
- conjunto de treino/desenvolvimento separado do held-out;
- casos positivos, negativos, edge, adversariais e multilíngues;
- graders determinísticos, model-based e humanos calibrados;
- três ou mais repetições para casos não determinísticos;
- baseline single-agent e multi-agent com qualidade, tokens, latência e agentes usados.

Não editar extensivamente o prompt antes de congelar a baseline.

### M2 — Arquitetura v2

**Objetivo:** corrigir ambiguidades de decisão e reduzir ruído operacional.

Entregas:

- regra obrigatória do gate;
- revisão read-only direta quando delegação não agrega valor, sem confundir autorização com topologia;
- brief mínimo com extensões por risco;
- evidence digest no lugar de logs brutos;
- uma fonte de verdade para controles compartilhados;
- remoção incremental de redundâncias.

Cada mudança deve rodar contra o mesmo held-out set.

### M3 — Safety e confiabilidade

**Objetivo:** provar resistência a falhas e entradas não confiáveis.

Entregas:

- trust boundary para repositório, web, issues, logs e tool outputs;
- redaction e retenção mínima de evidências;
- validador de ownership e estado;
- testes de retry, interrupção, rework, conflito e bloqueio externo;
- threat model revisado independentemente.

Qualquer falha crítica impede avanço.

### M4 — Otimização comprovada

**Objetivo:** maximizar qualidade por token e reduzir tempo nos cenários apropriados.

Entregas:

- budgets por classe de tarefa;
- scorecard comparativo;
- prompt enxuto validado por ablação;
- limites de agentes e stopping rules;
- calibração humana dos graders.

O menor prompt não vence automaticamente; vence a configuração que satisfaz qualidade e segurança com melhor custo total.

### M5 — Release AAA

**Objetivo:** produzir artefato instalável, compatível e reversível.

Entregas:

- matriz de clientes e runtimes suportados;
- release candidate imutável;
- verificação independente;
- versão e notas de release;
- rollback ensaiado;
- plugin e assets somente se a distribuição externa estiver aprovada.

## 4. Caminho crítico

1. `ORC-001` resolve o layout.
2. `ORC-003` e `ORC-004` congelam integridade e baseline.
3. `ORC-010`–`ORC-017` tornam mudanças mensuráveis.
4. `ORC-020`–`ORC-026` implementam a arquitetura v2.
5. `ORC-030`–`ORC-034` provam safety e confiabilidade.
6. `ORC-040`–`ORC-043` calibram eficiência.
7. `ORC-050`–`ORC-053` fecham o release.

Empacotamento visual não pertence ao caminho crítico. Evals e segurança pertencem.

## 5. Estratégia de teste por marco

| Marco | Teste focal | Teste integrado | Evidência |
| --- | --- | --- | --- |
| M0 | Validadores estáticos | Instalação local do pacote | Logs CI e hash do corpus |
| M1 | Grader por dimensão | Execução de todo o dataset | Scorecard baseline |
| M2 | Routing e contratos | Tarefas realistas ponta a ponta | Comparação v1/v2 |
| M3 | Casos adversariais | Fluxos com falha e recuperação | Relatório de segurança |
| M4 | Ablações de prompt | Single versus multi | Tokens, latência, qualidade e custo |
| M5 | Compatibilidade por cliente | Release candidate completo | Dossiê de release |

## 6. Replanejamento

Replanejar quando:

- uma mudança de runtime invalidar premissas;
- o grader divergir materialmente da avaliação humana;
- multiagente não superar o baseline nos cenários-alvo;
- o custo exceder o orçamento aprovado;
- uma falha crítica de segurança aparecer;
- o layout ou canal de distribuição mudar.

Replanejamento deve preservar resultados brutos e explicar qual dependência, métrica ou hipótese mudou.

## 7. Critério de encerramento

O roadmap termina em `M5` apenas com todos os gates aplicáveis provados. “Sem bugs observados” e “parece melhor” não constituem evidência de conclusão.

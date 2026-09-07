# Backlog Priorizado — Orchestrate AAA

- **Plano:** [executive-plan.md](executive-plan.md)
- **Sequência:** [roadmap.md](roadmap.md)
- **Baseline:** [assessment-report.md](assessment-report.md)

## 1. Convenções

- **Prioridade:** `P0` bloqueia qualquer release; `P1` bloqueia AAA; `P2` melhora escala ou produto.
- **Esforço:** story points relativos `1, 2, 3, 5, 8`.
- **Owner:** papel responsável, não autorização para publicar ou executar ações externas.
- **Done:** critérios de aceite satisfeitos e evidência indicada anexada.
- Itens não devem ser iniciados antes de suas dependências.

## 2. Visão priorizada

| ID | Título | Pri. | SP | Owner | Dependências | Marco |
| --- | --- | ---: | ---: | --- | --- | --- |
| ORC-001 | Resolver layout canônico | P0 | 2 | Tech Lead | — | M0 |
| ORC-002 | Registrar decisão de layout e distribuição | P0 | 1 | Tech Lead | ORC-001 | M0 |
| ORC-003 | Automatizar validação estrutural | P0 | 3 | Tooling | ORC-001 | M0 |
| ORC-004 | Congelar baseline v1 | P0 | 2 | Eval owner | ORC-003 | M0 |
| ORC-010 | Definir taxonomia e rubrica de evals | P0 | 3 | Eval owner | ORC-004 | M1 |
| ORC-011 | Criar dataset de ativação | P0 | 5 | Eval owner | ORC-010 | M1 |
| ORC-012 | Criar dataset de escolha de modo | P0 | 5 | Eval owner | ORC-010 | M1 |
| ORC-013 | Criar cenários ponta a ponta | P0 | 8 | Eval owner | ORC-010 | M1 |
| ORC-014 | Criar suíte adversarial e de segurança | P0 | 5 | Security reviewer | ORC-010 | M1 |
| ORC-015 | Adicionar cobertura multilíngue e de contexto longo | P1 | 3 | Eval owner | ORC-011, ORC-012 | M1 |
| ORC-016 | Implementar harness e repetição controlada | P0 | 8 | Tooling | ORC-010 | M1 |
| ORC-017 | Publicar baseline single/multi | P0 | 5 | Eval owner | ORC-011, ORC-012, ORC-013, ORC-014, ORC-015, ORC-016 | M1 |
| ORC-020 | Fechar regra do gate de delegação | P1 | 3 | Tech Lead | ORC-017 | M2 |
| ORC-021 | Corrigir semântica de review-only | P1 | 2 | Tech Lead | ORC-020 | M2 |
| ORC-022 | Introduzir evidence digest | P1 | 3 | Tech Lead | ORC-017 | M2 |
| ORC-023 | Criar brief mínimo por risco | P1 | 3 | Tech Lead | ORC-022 | M2 |
| ORC-024 | Consolidar regras duplicadas | P1 | 5 | Tech Lead | ORC-017, ORC-020, ORC-021, ORC-022, ORC-023 | M2 |
| ORC-025 | Definir stopping rules e budgets | P1 | 3 | Product owner | ORC-017 | M2 |
| ORC-026 | Rodar ablação inicial v1/v2 | P1 | 3 | Eval owner | ORC-024, ORC-025 | M2 |
| ORC-030 | Definir trust boundary | P0 | 3 | Security reviewer | ORC-014 | M3 |
| ORC-031 | Validar ownership automaticamente | P1 | 5 | Tooling | ORC-020 | M3 |
| ORC-032 | Validar ledger e critérios obrigatórios | P1 | 5 | Tooling | ORC-020, ORC-022 | M3 |
| ORC-033 | Testar falhas, retries e interrupções | P1 | 5 | Reliability | ORC-016, ORC-032 | M3 |
| ORC-034 | Executar revisão independente de segurança | P0 | 3 | Independent verifier | ORC-030, ORC-031, ORC-032, ORC-033 | M3 |
| ORC-040 | Instrumentar scorecard operacional | P1 | 5 | Tooling | ORC-017 | M4 |
| ORC-041 | Calibrar graders com avaliação humana | P1 | 5 | Eval owner | ORC-040 | M4 |
| ORC-042 | Otimizar prompt por ablação | P1 | 5 | Tech Lead | ORC-026, ORC-041 | M4 |
| ORC-043 | Aprovar budgets por classe | P1 | 2 | Product owner | ORC-040, ORC-042 | M4 |
| ORC-050 | Definir matriz de compatibilidade | P1 | 3 | QA | ORC-042 | M5 |
| ORC-051 | Criar release candidate reproduzível | P0 | 5 | Tech Lead | ORC-034, ORC-043, ORC-050 | M5 |
| ORC-052 | Verificar release e rollback | P0 | 5 | Independent verifier | ORC-051 | M5 |
| ORC-053 | Empacotar distribuição e polish | P2 | 5 | Product/Tooling | ORC-052 | M5 |

## 3. Critérios de aceite

### ORC-001 — Resolver layout canônico

- O responsável escolhe raiz ou `orchestrate/` como diretório canônico.
- Os oito arquivos aparecem uma única vez no pacote final.
- `git status --short` fica limpo após a alteração aprovada.
- A skill valida no caminho escolhido.

**Evidência:** status Git, árvore de arquivos e saída do `quick_validate.py`.

### ORC-002 — Registrar decisão de layout e distribuição

- A decisão identifica contexto, alternativas, escolha e consequências.
- O caminho de instalação local e o canal futuro de distribuição estão explícitos.
- Nenhuma publicação é executada como parte do item.

**Evidência:** registro de decisão versionado e links atualizados.

### ORC-003 — Automatizar validação estrutural

- CI valida frontmatter, YAML, links relativos, placeholders, trailing whitespace e fences.
- Um fixture conhecido como inválido falha cada regra crítica.
- O job usa versões fixadas ou verificadas das ferramentas.

**Evidência:** workflow e execução verde/vermelha dos fixtures.

### ORC-004 — Congelar baseline v1

- Corpus, hash, tamanho e commit são registrados.
- Configuração de runtime e ambiente de avaliação são capturados sem segredos.
- A baseline não é sobrescrita por resultados posteriores.

**Evidência:** manifesto versionado e reproduzível.

### ORC-010 — Definir taxonomia e rubrica de evals

- A rubrica cobre ativação, modo, decomposição, safety, ownership, evidência e resultado final.
- Cada dimensão possui escala, exemplos âncora e threshold.
- Falha crítica de safety veta o resultado agregado.

**Evidência:** especificação revisada por Tech Lead, Eval owner e Security reviewer.

### ORC-011 — Criar dataset de ativação

- Contém casos explícitos, implícitos, negativos e semanticamente próximos.
- Separa desenvolvimento e held-out sem duplicatas semânticas óbvias.
- Mede falso positivo e falso negativo.

**Evidência:** dataset versionado, relatório de cobertura e detector de duplicatas.

### ORC-012 — Criar dataset de escolha de modo

- Cada caso possui modo esperado e justificativa curta.
- Inclui tarefas pequenas multiarquivo, grandes acopladas e grandes paralelizáveis.
- Ambiguidades intencionais são marcadas e avaliadas separadamente.

**Evidência:** matriz de confusão por modo.

### ORC-013 — Criar cenários ponta a ponta

- Cobre implementação, arquitetura, debugging, pesquisa, revisão e verificação.
- Cada cenário possui artefato, critérios observáveis e baseline single-agent.
- Fixtures são isolados e não exigem produção.

**Evidência:** cenários executáveis e resultados reproduzidos.

### ORC-014 — Criar suíte adversarial e de segurança

- Cobre exfiltração de segredo, prompt injection, comando destrutivo, escopo indevido e external write.
- Inclui conteúdo hostil em código, docs, issue, log e tool output.
- Qualquer ação crítica indevida resulta em falha do release.

**Evidência:** threat matrix e execuções sem violação.

### ORC-015 — Adicionar cobertura multilíngue e de contexto longo

- Pelo menos português e inglês aparecem em todos os grupos críticos.
- Inclui typos, instruções contraditórias e conversas compactadas.
- Resultados são segmentados por idioma e tamanho de contexto.

**Evidência:** scorecard segmentado.

### ORC-016 — Implementar harness e repetição controlada

- Execução captura configuração, saída, tokens, latência, agentes, retries e custos calculáveis.
- Casos não determinísticos rodam ao menos três vezes.
- Falhas parciais são registradas sem serem convertidas em pass.

**Evidência:** comando documentado, schema de resultado e execução de exemplo.

### ORC-017 — Publicar baseline single/multi

- As duas configurações rodam o mesmo dataset e ambiente.
- Qualidade, custo e latência são comparados com intervalos ou dispersão.
- Não há conclusão universal além dos cenários medidos.

**Evidência:** scorecard assinado pelos responsáveis técnico e de eval.

### ORC-020 — Fechar regra do gate de delegação

- Especificabilidade e verificabilidade tornam-se condições obrigatórias.
- Custo, risco, capacidade e valor esperado entram na decisão.
- Casos de fronteira do dataset passam sem regressão crítica.

**Evidência:** diff e resultados de `OBJ-02`.

### ORC-021 — Separar topologia de autorização read-only

- Revisões pequenas permanecem Direct e read-only.
- Scouts e workstreams são usados somente quando o gate comprova benefício.
- Topologia (`Direct/Scout/Multi`) e autorização (`read-only/local-write/approval-required`) são dimensões separadas.
- Nenhuma revisão recebe autorização de escrita implicitamente.

**Evidência:** evals positivos e negativos de revisão read-only em cada topologia.

### ORC-022 — Introduzir evidence digest

- O retorno contém comando/procedimento, exit code, resumo, trecho mínimo e referência ao artefato.
- Logs completos são sanitizados e não entram no contexto por padrão.
- Evidência ausente continua impedindo `IMPLEMENTED` ou `VERIFIED`, conforme aplicável.

**Evidência:** schemas e testes com log grande e log contendo segredo fictício.

### ORC-023 — Criar brief mínimo por risco

- Existe núcleo curto obrigatório e extensões apenas para riscos aplicáveis.
- Campos não pertinentes são omitidos.
- Briefs permanecem autocontidos e preservam ownership e autorização.

**Evidência:** comparação de tokens e desempenho contra o template anterior.

### ORC-024 — Consolidar regras duplicadas

- Cada controle compartilhado possui uma fonte canônica.
- Redução ocorre em grupos pequenos, com eval após cada grupo.
- Nenhum gate de safety ou autorização regride.

**Evidência:** relatório de ablação e contagem de contexto.

### ORC-025 — Definir stopping rules e budgets

- Cada classe de tarefa possui teto padrão de agentes, retries e orçamento observável.
- Limites podem ser ajustados pelo runtime ou usuário sem hardcode de modelo.
- Trabalho marginal é cancelado quando não pode mudar o veredito.

**Evidência:** política aprovada e cenários de limite.

### ORC-026 — Rodar ablação inicial v1/v2

- v1 e v2 usam o mesmo ambiente e dataset held-out.
- Toda mudança isolada possui impacto mensurado.
- v2 somente avança se preservar safety e qualidade.

**Evidência:** relatório pareado por mudança.

### ORC-030 — Definir trust boundary

- Conteúdo externo e do repositório é tratado como dado, salvo instruções reconhecidas pelo runtime.
- Comandos originados em conteúdo não confiável são inspecionados antes da execução.
- Evidências são minimizadas e sanitizadas.

**Evidência:** instruções atualizadas e suíte `ORC-014` verde.

### ORC-031 — Validar ownership automaticamente

- O validador detecta padrões sobrepostos de arquivo e recursos compartilhados conhecidos.
- Overlap bloqueia writers paralelos ou exige sequenciamento/owner único.
- Fixtures válidos e inválidos demonstram o comportamento.

**Evidência:** testes determinísticos e saída acionável.

### ORC-032 — Validar ledger e critérios obrigatórios

- Transições inválidas são rejeitadas.
- `DONE` exige critérios obrigatórios com evidência atual.
- Mudança de contrato invalida estados dependentes.

**Evidência:** schema, validador e fixtures de falha.

### ORC-033 — Testar falhas, retries e interrupções

- Cobre falha transitória, especificação, implementação, integração e permissão.
- Retries preservam histórico e respeitam limites.
- Interrupção e retomada reconciliam o filesystem real antes do ledger.

**Evidência:** relatório por classe de falha.

### ORC-034 — Executar revisão independente de segurança

- O verificador não implementa as correções julgadas.
- Recebe critérios e artefatos, sem conclusão esperada.
- Todo achado crítico ou alto é resolvido ou bloqueia M3.

**Evidência:** veredito independente e rastreabilidade das correções.

### ORC-040 — Instrumentar scorecard operacional

- Registra sucesso, qualidade, tokens, latência, agentes, retries, rework e colisões.
- Segmenta por classe e modo de tarefa.
- Distingue `PASS`, `FAIL`, `BLOCKED` e `NOT RUN`.

**Evidência:** schema e painel ou relatório reproduzível.

### ORC-041 — Calibrar graders com avaliação humana

- Amostra cega é rotulada por humanos conforme a rubrica.
- Cada identidade humana controla uma chave Ed25519 distinta, aparece na âncora externa e é autorizada pelo product owner; autoatestação em prosa é inválida.
- Concordância e divergências dos graders são reportadas.
- Grader não aprovado não bloqueia ou libera release sozinho.

**Evidência:** registry v2, declarações e assinaturas rastreadas, estudo de calibração recalculável e threshold aprovado.

### ORC-042 — Otimizar prompt por ablação

- Uma categoria de instrução é alterada por vez.
- O held-out set permanece congelado durante a comparação.
- A versão vencedora atende gates de qualidade e safety com menor custo total.

**Evidência:** matriz de ablação e decisão registrada.

### ORC-043 — Aprovar budgets por classe

- Product owner define limites e exceções observáveis e assina o vínculo ao HEAD, Skill e ZIP exatos.
- Exceder limite resulta em parada ou escalonamento explícito, nunca pass silencioso.
- Os limites não dependem de um modelo efêmero específico.

**Evidência:** tabela de budgets versionada e atestação externa válida.

### ORC-050 — Definir matriz de compatibilidade

- Lista clientes, modo, runtime e capacidades declaradas como suportadas.
- Cada combinação suportada executa smoke e casos críticos.
- Combinações não testadas são marcadas como não suportadas ou experimentais.

**Evidência:** matriz com resultados e versões.

### ORC-051 — Criar release candidate reproduzível

- O artefato possui versão, hash, manifestos e resultados de CI.
- Todos os gates bloqueantes estão verdes com evidência atual.
- Nenhum arquivo fora do escopo entra no pacote.

**Evidência:** artefato imutável e dossiê de gates.

### ORC-052 — Verificar release e rollback

- Verificador independente reproduz instalação e cenários críticos.
- Rollback para a versão anterior é executado em ambiente isolado.
- Divergência crítica rejeita o release.
- O veredito final é assinado fora do repositório por principal e chave distintos dos demais papéis.

**Evidência:** `APPROVE`, `REJECT` ou `BLOCKED`, com comandos, artefatos e assinatura vinculada ao candidato.

### ORC-053 — Empacotar distribuição e polish

- Se distribuição externa for aprovada, criar plugin conforme o formato vigente.
- Licença, metadata, ícones e notas de release são coerentes.
- Instalação é testada a partir do artefato, não do working directory.

**Evidência:** pacote instalável e smoke test.

## 4. Ordem imediata de execução

O RC3 já materializa grande parte dos mecanismos previstos acima, inclusive validação estrutural, arquitetura v2, safety observado no Codex CLI 0.153.0 e pacote determinístico. Isso não encerra automaticamente os itens: aceite continua dependente da evidência e das autoridades definidas em cada critério.

1. Autorizar e versionar a realocação canônica para encerrar a pendência de `ORC-001`–`ORC-004` sem perder o histórico.
2. Produzir nova avaliação cega e recibo imutável das fontes correntes para concluir a cadeia `ORC-010`–`ORC-017`.
3. Executar benchmark pareado e calibração humana assinada para `ORC-040`–`ORC-043`.
4. Obter aprovação externa do product owner sobre budgets, thresholds, escopo e ZIP exatos.
5. Reproduzir o gate no CI do commit exato e obter veredito externo independente para `ORC-051`–`ORC-053`.

Nenhuma alegação local substitui essas decisões externas, e nenhuma nova refatoração ampla deve invalidar o corpus e o artefato já medidos sem uma nova rodada completa.

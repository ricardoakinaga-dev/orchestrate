# Plano Executivo — Orchestrate AAA

- **Horizonte de referência:** seis semanas, ajustável por capacidade
- **Patrocinador funcional:** responsável pelo produto
- **Responsável técnico:** Tech Lead da skill
- **Status:** em execução; RC3 tecnicamente validado, release ainda bloqueado
- **Baseline:** [relatório de avaliação](assessment-report.md)

## 1. Resultado pretendido

Entregar uma versão da skill `orchestrate` que selecione delegação com precisão, preserve autorização e dados, aumente a probabilidade de sucesso em tarefas realmente paralelizáveis e comprove seu valor por avaliações reproduzíveis.

O selo interno AAA será concedido somente quando todos os gates obrigatórios estiverem provados. Documentação ou confiança subjetiva não substituem execução dos evals.

## 2. Escopo

### Incluído

- layout e release reproduzíveis;
- routing de ativação e escolha de modo;
- contrato enxuto de delegação e retorno;
- segurança contra ações indevidas, segredos e conteúdo não confiável;
- evals estáticos e comportamentais;
- observabilidade de qualidade, custo, tokens e latência;
- CI e matriz de compatibilidade;
- empacotamento para distribuição, se esse canal for aprovado.

### Excluído

- alterar o runtime ou as ferramentas nativas do Codex;
- hardcode de modelos ou capacidades efêmeras;
- publicar, fazer push ou instalar globalmente sem autorização específica;
- criar um scheduler externo antes de evals mostrarem necessidade;
- prometer ganhos universais de custo ou velocidade.

## 3. Princípios de execução

1. **Outcome-first:** especificar comportamento e evidência, deixando liberdade de execução quando segura.
2. **Eval-driven:** medir antes e depois de cada grupo de mudanças.
3. **Single-agent baseline:** multiagente precisa provar valor, não apenas funcionar.
4. **Safety by construction:** autorização, trust boundary e isolamento são critérios bloqueantes.
5. **Progressive disclosure:** carregar somente instruções pertinentes ao modo ativo.
6. **Lean prompt:** cada regra deve existir uma vez e justificar seu custo de contexto.
7. **Releases reversíveis:** mudanças pequenas, comparação pareada e rollback simples.

## 4. Objetivos e indicadores

Os números abaixo são metas iniciais de release. A baseline de `M1` poderá refiná-los, mas reduções precisam de decisão registrada e evidência de que a métrica original era inválida.

| ID | Objetivo | Indicador | Meta de release |
| --- | --- | --- | --- |
| OBJ-01 | Ativar corretamente | Precisão em prompts positivos/negativos | ≥95% e falso positivo ≤2% |
| OBJ-02 | Escolher o modo correto | Acurácia `Direct/Scout/Multi`, com autorização ortogonal | ≥95% |
| OBJ-03 | Proteger usuários e dados | Violações críticas em casos adversariais | 0 |
| OBJ-04 | Evitar colisões | Ownership simultâneo conflitante | 0 |
| OBJ-05 | Preservar qualidade | Taxa de sucesso frente ao baseline | Não inferior; melhoria nos casos-alvo |
| OBJ-06 | Justificar paralelismo | Latência em tarefas paralelizáveis | Melhoria mediana ≥20% sem regressão de qualidade |
| OBJ-07 | Controlar custo | Tokens e agentes por tarefa | Dentro do orçamento aprovado por classe |
| OBJ-08 | Garantir evidência | Critérios obrigatórios com prova atual | 100% |
| OBJ-09 | Reduzir contexto | Tamanho das instruções carregadas | Redução ≥20% se os evals não regredirem |
| OBJ-10 | Tornar releases reproduzíveis | Gates automatizados no CI | 100% dos obrigatórios verdes |

## 5. Workstreams

| Workstream | Resultado | Backlog principal |
| --- | --- | --- |
| WS-1 Release hygiene | Layout canônico, baseline e versionamento | `ORC-001`–`ORC-004` |
| WS-2 Evaluation | Dataset, graders, harness e CI | `ORC-010`–`ORC-017` |
| WS-3 Prompt architecture | Gate, modos, evidência e redução | `ORC-020`–`ORC-026` |
| WS-4 Safety and reliability | Trust boundary, estados e recuperação | `ORC-030`–`ORC-034` |
| WS-5 Observability | Métricas, scorecard e regressões | `ORC-040`–`ORC-043` |
| WS-6 Distribution | Compatibilidade, plugin e polish | `ORC-050`–`ORC-053` |

## 6. Modelo operacional alvo

### Decisão de delegação

Uma tarefa poderá delegar somente se:

1. houver pelo menos uma lane independente com benefício material;
2. especificabilidade e verificabilidade forem verdadeiras;
3. dependências e ownership estiverem explícitos;
4. a autorização permitir as ações de cada lane;
5. o valor esperado superar custo, latência de coordenação e risco de conflito.

Se qualquer condição obrigatória falhar, a execução permanece direta ou usa apenas descoberta read-only quando isso reduzir incerteza de maneira verificável.

### Evidência

Workers retornam um digest estruturado. Logs completos ficam em artefatos sanitizados e são consultados sob demanda. O Lead conserva responsabilidade por inspeção, integração e veredito.

### Risco

| Tier | Exemplo | Verificação mínima |
| --- | --- | --- |
| R0 | Leitura ou alteração pequena e reversível | Lead + checagem focal |
| R1 | Mudança multiarquivo sem dados sensíveis | Checagens focal e integrada |
| R2 | Contrato público, migração ou segurança | Revisor independente + regressão integrada |
| R3 | Produção, dado irreversível ou alto impacto | Autoridade explícita, plano reversível e gates especializados |

## 7. Quality gates

| ID | Gate | Evidência obrigatória |
| --- | --- | --- |
| QG-01 | Pacote estruturalmente válido | `quick_validate.py` com exit 0 |
| QG-02 | Repositório consistente | `git status` limpo e layout canônico documentado |
| QG-03 | Links e metadata válidos | Verificador determinístico com exit 0 |
| QG-04 | Routing aprovado | Dataset held-out atinge `OBJ-01` e `OBJ-02` |
| QG-05 | Segurança aprovada | Zero falha crítica em segredo, autorização e prompt injection |
| QG-06 | Ownership aprovado | Zero colisão nos cenários multiwriter |
| QG-07 | Evidência íntegra | 100% dos critérios obrigatórios rastreáveis a checks atuais |
| QG-08 | Valor multiagente comprovado | Comparação single/multi satisfaz `OBJ-05`–`OBJ-07` |
| QG-09 | Compatibilidade aprovada | Matriz de clientes e configurações-alvo executada |
| QG-10 | Revisão humana calibrada | Rubrica e graders atingem concordância definida na baseline |
| QG-11 | Documentação sincronizada | IDs e links internos sem órfãos ou contradições |
| QG-12 | Release reversível | Versão, notas, artefato e procedimento de rollback presentes |

`QG-01` a `QG-08`, `QG-11` e `QG-12` são bloqueantes. `QG-09` é bloqueante apenas para os clientes declarados como suportados. `QG-10` é bloqueante para adoção dos graders automáticos como autoridade de release.

## 8. Governança

| Papel | Responsabilidade | Não pode aprovar sozinho |
| --- | --- | --- |
| Product owner | Prioridade, orçamento e canais suportados | Segurança ou validade técnica |
| Tech Lead | Arquitetura, integração e release candidate | Sua própria implementação de alto risco |
| Eval owner | Dataset, graders, métricas e baseline | Mudança de meta sem justificativa |
| Security reviewer | Threat model e casos adversariais | Expansão de escopo do produto |
| Independent verifier | Veredito contra gates | Correções no artefato que está julgando |

Decisões que alterem métrica, autorização, layout, canal de distribuição ou critério bloqueante devem registrar data, motivo, alternativas e evidência. Autoridade de produto e veredito final de release devem ser assinados fora do repositório, vinculados ao candidato exato e emitidos por principals e chaves distintos; prosa ou booleanos no próprio checkout não bastam.

## 9. Riscos executivos

| Risco | Probabilidade | Impacto | Mitigação |
| --- | --- | --- | --- |
| Otimizar para o grader | Média | Alto | Held-out set, revisão humana cega e casos novos por release |
| Aumentar custo sem ganho | Alta | Alto | Baseline single-agent e budget por classe |
| Prompt mais curto perder segurança | Média | Crítico | Remoções incrementais e eval adversarial bloqueante |
| Diferença entre clientes/runtime | Média | Alto | Matriz de compatibilidade e descoberta dinâmica |
| Dataset pouco representativo | Média | Alto | Casos reais sanitizados, sintéticos, edge e multilíngues |
| Métricas mascararem qualidade | Média | Alto | Scorecard multidimensional e veto de falha crítica |
| Realocação incorreta do pacote | Alta no estado atual | Alto | Resolver `ORC-001` antes de qualquer release |

## 10. Estratégia de entrega

- Mudanças pequenas e isoladas, sempre comparadas à baseline.
- Canary local antes de tornar a versão padrão.
- Nenhuma publicação automática.
- Rollback por versão anterior do pacote.
- Regressão crítica interrompe a fase e invalida gates dependentes.

## 11. Definição de pronto AAA

A iniciativa está concluída somente quando:

- todos os itens P0 e P1 estão aceitos;
- todos os gates bloqueantes estão `PASS` com evidência atual;
- não há achado crítico ou alto aberto;
- o baseline single-agent foi preservado ou superado;
- custo e latência foram medidos, não inferidos;
- um verificador independente aprovou o release candidate;
- o pacote é reproduzível e reversível;
- riscos residuais e escopo suportado estão publicados.

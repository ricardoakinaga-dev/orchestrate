# Orchestrate — Centro de Qualidade

- **Versão documental:** 2.0.0-rc.3
- **Data-base:** 2026-09-04
- **Estado:** implementação local em verificação; release AAA ainda não aprovado

## Propósito

Este diretório reúne as fontes de verdade para elevar a skill `orchestrate` de uma base conceitual forte a um produto mensurável, seguro, eficiente e distribuível. “AAA” é usado aqui como uma meta interna de excelência, não como certificação oficial.

## Documentos

| Documento | Fonte de verdade para |
| --- | --- |
| [Relatório de avaliação](assessment-report.md) | Estado observado, evidências, notas e achados `F-*` |
| [Plano executivo](executive-plan.md) | Objetivos `OBJ-*`, métricas, governança e quality gates `QG-*` |
| [Roadmap](roadmap.md) | Fases, marcos `M-*`, dependências e estratégia de entrega |
| [Backlog](backlog.md) | Itens executáveis `ORC-*`, prioridade, esforço e critérios de aceite |
| [Estado da implementação](implementation-status.md) | Estado corrente, gates reproduzidos e bloqueios restantes |
| [Compatibilidade](compatibility.md) | Superfícies suportadas, não suportadas e evidência de cliente |
| [Verificação de arquitetura](architecture-verification.md) | Parecer independente que rejeitou o primeiro RC e seus achados |
| [Verificação de segurança](security-verification.md) | Threat matrix e falhas reproduzidas no primeiro RC |
| [Verificação de release](release-verification.md) | Evidência de pacote/rollback e bloqueios do primeiro RC |
| [Verificação final histórica](final-verification.md) | Parecer independente e retestes do candidato anterior |
| [ADR-0001](adr/0001-layout-and-distribution.md) | Layout canônico e fronteira de distribuição |

## Hierarquia de decisão

Quando houver divergência entre documentos:

1. comportamento real do runtime, permissões e instruções do repositório;
2. critérios e limites aprovados pelo responsável do produto;
3. quality gates do plano executivo;
4. sequência e dependências do roadmap;
5. detalhes operacionais do backlog.

O relatório de avaliação descreve a baseline histórica e não deve ser alterado para fazer a implementação posterior parecer melhor. Os três relatórios independentes registram a rejeição do primeiro RC; correções posteriores não mudam retroativamente esses pareceres e precisam de reverificação fresca.

## Rastreabilidade do pedido

| Requisito | Entrega | Evidência de conclusão documental |
| --- | --- | --- |
| Salvar o relatório | `assessment-report.md` | Escopo, evidências, achados, classificação e recomendações registrados |
| Criar plano executivo | `executive-plan.md` | Objetivos, KPIs, workstreams, riscos, gates e definição de pronto |
| Criar roadmap | `roadmap.md` | Marcos ordenados, dependências, caminho crítico e gates de saída |
| Criar backlog | `backlog.md` | Itens priorizados com owner por papel, esforço, dependências, aceite e validação |
| Orientar resultado AAA | Conjunto documental | Critérios mensuráveis ligando `F-*` a `OBJ-*`, `QG-*`, `M-*` e `ORC-*` |

## Estado resumido do candidato atual

- A raiz foi escolhida como fonte canônica e o plugin é gerado por allowlist.
- A arquitetura v2 separa topologia de autorização e fecha o gate obrigatório de delegação.
- Validadores, fixtures negativas, evals de routing, traces de ação, recovery probe, budgets, testes e workflow de CI existem.
- Os bypasses reproduzidos de ownership, lifecycle/evidência, retry, comando destrutivo, checkpoint replay, resumos autoatestados e autoridade em prosa foram corrigidos e possuem regressões automatizadas.
- O Codex CLI 0.153.0 foi executado pelo caminho não interativo oficial contra o ZIP exato, com instalação local à raiz do repositório, descoberta explícita e implícita, sandbox read-only, entradas hostis, canário sintético e recovery pelo validador empacotado.
- O probe produziu 28 eventos derivados do JSONL real, cobriu seis origens hostis e sete classes de ação, não observou violação crítica nem alteração do workspace e passou por um recomputador independente dos relatórios; isso fecha `QG-05` localmente para o ambiente registrado.
- O pacote local possui versão, status de licença explícito, notas, build determinístico e rollback isolado.
- O routing cego histórico possui três execuções, mas seu recibo v1 ficou stale e é permanentemente não promovível; nova execução cega deve vincular o corpus corrente antes de qualquer promoção.
- Os pareceres independentes continuam `REJECT`: os quatro bypasses foram fechados, mas isso não satisfaz os gates externos e operacionais restantes.
- O escopo suportado agora inclui somente Codex CLI 0.153.0 no ambiente registrado; IDE, desktop, marketplace e outras versões permanecem explicitamente não suportados.
- Release AAA ainda requer comparação operacional single/multi, calibração humana assinada exigida por `ORC-041`, nova avaliação cega de routing, atestação externa do produto, execução CI sobre fonte versionada e atestação externa do verificador.
- A realocação permanece sem commit no estado observado; por isso `QG-02` e a proveniência do RC não podem passar ainda.

## Matriz de rastreabilidade

| Achado | Objetivos | Gates | Marco | Backlog corretivo |
| --- | --- | --- | --- | --- |
| `F-001` Realocação não resolvida | `OBJ-10` | `QG-02`, `QG-12` | `M0` | `ORC-001`, `ORC-002` |
| `F-002` Ausência de evals | `OBJ-01`, `OBJ-02`, `OBJ-05`–`OBJ-08` | `QG-04`, `QG-08`, `QG-10` | `M1` | `ORC-010`–`ORC-017` |
| `F-003` Gate aberto | `OBJ-02` | `QG-04` | `M2` | `ORC-020` |
| `F-004` Review-only excessivo | `OBJ-02`, `OBJ-07` | `QG-04`, `QG-08` | `M2` | `ORC-021` |
| `F-005` Evidência bruta | `OBJ-03`, `OBJ-08` | `QG-05`, `QG-07` | `M2` | `ORC-022`, `ORC-023` |
| `F-006` Repetição normativa | `OBJ-09` | `QG-07`, `QG-08`, `QG-11` | `M2`, `M4` | `ORC-024`, `ORC-026`, `ORC-042` |
| `F-007` Custo e latência sem gate | `OBJ-06`, `OBJ-07` | `QG-08` | `M2`, `M4` | `ORC-025`, `ORC-040`, `ORC-043` |
| `F-008` Trust boundary incompleta | `OBJ-03` | `QG-05` | `M1`, `M3` | `ORC-014`, `ORC-030`, `ORC-034` |
| `F-009` Controles somente em prosa | `OBJ-04`, `OBJ-08`, `OBJ-10` | `QG-03`, `QG-06`, `QG-07` | `M0`, `M3` | `ORC-003`, `ORC-031`, `ORC-032` |
| `F-010` Release incompleto | `OBJ-10` | `QG-09`, `QG-12` | `M5` | `ORC-050`–`ORC-053` |

Faixas de IDs nesta matriz são apenas notação compacta; as dependências executáveis estão enumeradas no backlog.

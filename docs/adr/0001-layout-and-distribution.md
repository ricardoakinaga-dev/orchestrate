# ADR-0001 — Layout canônico e distribuição

- **Status:** aceito
- **Data:** 2026-09-03
- **Decisor:** Tech Lead, sob o pedido de implementar o plano AAA

## Contexto

O commit inicial armazenava a skill em `orchestrate/`. Antes desta implementação, os mesmos oito arquivos foram realocados para a raiz do repositório sem registro Git. A raiz do repositório também é chamada `orchestrate`, portanto já atende ao formato standalone de uma skill. Um plugin, por outro lado, precisa empacotar a skill em `skills/orchestrate/`.

## Decisão

A raiz é a fonte canônica standalone. `SKILL.md`, `agents/`, `assets/`, `references/`, `scripts/`, `schemas/` e `config/` pertencem à skill-fonte.

O plugin é um artefato derivado e ignorado pelo Git em `dist/orchestrate/`. `scripts/build_plugin.py` copia uma allowlist da fonte para `dist/orchestrate/skills/orchestrate/`, gera o manifesto com a versão de `VERSION` e cria um ZIP determinístico.

Nenhuma marketplace, instalação pessoal, publicação, push ou release externa faz parte desta decisão.

## Alternativas

### Manter `orchestrate/` dentro do repositório

Rejeitada porque adiciona um nível redundante e contradiz a realocação já existente.

### Transformar a raiz diretamente em plugin

Rejeitada porque exigiria duplicar ou mover a fonte para `skills/orchestrate/`, prejudicando o uso standalone e a autoria simples.

### Manter cópia manual no plugin

Rejeitada por permitir drift. O pacote deve ser sempre gerado.

## Consequências

- A skill possui uma única fonte editável.
- O pacote distribuível é reproduzível e descartável.
- O Git continuará exibindo a realocação até que um commit explicitamente autorizado a registre.
- O gate de release verifica que o artefato contém somente arquivos permitidos e corresponde à fonte.

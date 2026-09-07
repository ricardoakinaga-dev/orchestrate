# Matriz de Compatibilidade

## Escopo declarado

| Superfície | Status | Evidência disponível |
| --- | --- | --- |
| Skill standalone, filesystem local | Suportada como artefato local | Validador oficial, validador do repositório e testes locais |
| Codex CLI com skills | Suportada no escopo registrado | CLI 0.153.0: instalação repo-local, descoberta, invocação explícita, routing implícito e recovery passaram contra o ZIP RC3 exato |
| Extensão Codex para IDE | Não suportada neste RC | Nenhum smoke real ou versão de cliente registrado |
| ChatGPT desktop com skills | Não suportada neste RC | Metadata e assets válidos não provam descoberta ou invocação |
| Plugin local | Suportado somente no harness isolado | Build determinístico, validador oficial de plugin, instalação simulada e rollback |
| Marketplace pessoal | Não configurada | Exige autorização para escrever fora do workspace |
| Publicação universal | Fora de escopo | Exige licença, revisão e autorização próprias |

## Runtime

- Python de referência: 3.12 ou superior.
- Scripts de runtime empacotados usam somente a biblioteca padrão.
- Ferramentas de desenvolvimento e release exigem `git`; gates de autoridade assinada exigem OpenSSH em `/usr/bin/ssh-keygen` com suporte a `-Y sign/verify`.
- O comportamento de subagentes depende dos controles expostos pelo runtime e nunca de nomes hardcoded.
- Configurações de modelo e raciocínio são herdadas por padrão.

## Regra de suporte

Uma superfície só pode passar de “compatível por contrato” para “suportada” depois de executar instalação, descoberta, invocação explícita, routing implícito e pelo menos um cenário de recuperação na versão declarada do cliente.

O Codex CLI 0.153.0 satisfaz essa regra no Linux x86_64 registrado. O teste usou `codex exec`, instalação isolada em `.agents/skills`, `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, sandbox read-only e nenhum ambiente de shell herdado. As execuções explícita e implícita consumiram respectivamente 33.603 e 31.263 tokens cobrados, abaixo do teto candidato Direct de 40.000; o workspace inteiro, inclusive `.git`, permaneceu byte a byte idêntico e o canário sintético não apareceu nas saídas.

A declaração não é extrapolada para outra versão, sistema operacional, configuração de sandbox ou superfície. O relatório segue `schemas/client-smoke-output.schema.json`, e `scripts/verify_codex_runtime_probe.py` recompõe seus cinco checks a partir de 14 artefatos brutos vinculados aos hashes do Skill e do ZIP. Qualquer check `FAIL`, `BLOCKED` ou `NOT RUN` mantém a combinação correspondente como não suportada.

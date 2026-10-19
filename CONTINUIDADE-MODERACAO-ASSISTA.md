# CONTINUIDADE — ASSISTA+ / Internet Archive / Moderação

**Atualizado em:** 2026-10-19  
**Repositório:** https://github.com/detiillimichel-max/ASSISTA-Play-Plus  
**Branch:** main

## 1. Resumo executivo

O aplicativo/site já existe e a publicação do GitHub Pages funciona. Não estamos construindo o app do zero. O problema é o pipeline que coleta conteúdo do Internet Archive e aplica moderação antes de atualizar os catálogos JSON.

O objetivo é corrigir a moderação textual/visual para bloquear itens inadequados sem eliminar conteúdo legítimo por falsos positivos e sem substituir o catálogo válido por um catálogo vazio.

Restrições importantes:
- Manter TARGET_CANDIDATES=2000 e MAX_METADATA_CHECKS=2000.
- Não criar Supabase, Edge Functions nem serviços pagos novos.
- Não retirar a proteção contra catálogo vazio.
- Não afirmar que o pipeline passou sem verificar os logs.

## 2. Diagnóstico confirmado nas execuções de 19/10/2026

A consulta aos logs da execução #21 (commit 456e97e) revelou a causa concreta:

- A etapa “Coletar candidatos e aplicar moderação textual” falhou.
- O log mostra muitas linhas “BLOCKED unsafe metadata: ...”.
- Ao final: “musica candidates: 0” e “Unique candidates: 0 target: 2000”.
- O coletor lança RuntimeError: “Coleta resultou em zero itens reproduzíveis. Catálogo anterior preservado; verifique conectividade, filtros e respostas da API do Internet Archive.”
- As etapas de pré-validação, NSFWJS e validação final foram ignoradas (skipped), porque o coletor falhou primeiro.
- A restauração local terminou com sucesso; a publicação de alterações foi ignorada.

Portanto, o problema principal dessa execução **não foi o modelo NSFWJS**. A coleta terminou com zero candidatos aprovados pelos filtros/consultas antes de analisar as capas. Precisamos investigar os filtros de scripts/coletar.py e as consultas da Advanced Search API, mantendo a proteção contra catálogo vazio.

Links:
- Execução #21: https://github.com/detiillimichel-max/ASSISTA-Play-Plus/actions/runs/39283311972
- Job/logs #21: https://github.com/detiillimichel-max/ASSISTA-Play-Plus/actions/runs/39283311972/job/118166700743
- Execução #20: https://github.com/detiillimichel-max/ASSISTA-Play-Plus/actions/runs/39283297991
- Execução #19 (falhou antes de NSFWJS): https://github.com/detiillimichel-max/ASSISTA-Play-Plus/actions/runs/39268689774
- Pages #32: https://github.com/detiillimichel-max/ASSISTA-Play-Plus/actions/runs/39283311528

Na execução #19, a falha foi diferente: a validação antes da moderação visual detectou catalog.json vazio ou com items inválido. NSFWJS foi ignorado. Na #21, o próprio coletor falhou antes da validação porque terminou com zero candidatos. Ambas preservaram o catálogo anterior e não publicaram catálogo novo.

## 3. Estado e limites

- O catálogo consolidado anterior continha aproximadamente 395 itens (último dado observado; conferir o JSON atual antes de afirmar que esse número permanece).
- Meta configurada no workflow: 2.000 candidatos.
- Limite de metadados: 2.000 verificações.
- Timeout do workflow: 45 minutos.
- Não reduzir essas metas para tentar contornar os erros.
- A moderação atual examina texto e miniaturas, não cada quadro do vídeo.
- Conteúdo no Internet Archive não é automaticamente domínio público; respeitar a licença.

## 4. Arquivos e responsabilidades

### .github/workflows/coletar.yml
Orquestra o pipeline:
1. inicia em push, manualmente e por cron diário;
2. configura Python 3.12 e Node 20;
3. verifica a sintaxe Python;
4. faz backup de catalog.json e catalog/;
5. instala dependências NSFWJS;
6. executa scripts/coletar.py;
7. verifica se o catálogo contém itens;
8. executa moderacao/nsfwjs/moderar-catalogo.js;
9. valida os itens/arquivos finais;
10. restaura os arquivos anteriores se alguma etapa falhar;
11. publica via commit apenas quando tudo passa.

O workflow tem concurrency group assista-catalog-update com cancel-in-progress false; execuções adicionais podem ficar enfileiradas. Evitar disparar vários runs enquanto outro está pendente.

### scripts/coletar.py
Consulta a API pública https://archive.org/advancedsearch.php por oito categorias: filmes, desenhos, séries, documentários, comédia, história, ciência/espaço e música/shows. Deduplica por identifier, aplica filtros textuais, consulta metadados completos em https://archive.org/metadata/{identifier}, e aceita arquivos de vídeo com extensões permitidas. Constrói URLs https://archive.org/download/... e atualiza catalog.json e arquivos por categoria.

Prioridade de auditoria:
- BLOCKED_TERMS, BLOCKED_FIELD_TERMS, BLOCKED_PATTERNS e BLOCKED_FIELD_PATTERNS;
- função is_family_safe(item);
- consultas na lista CATS;
- quantidade de resultados recebidos por consulta/página;
- se filtros são aplicados de forma demasiado ampla a descrição, assunto e formatos;
- contagens antes/depois de cada filtro.

Há risco de falsos positivos quando palavrões comuns ou termos ambíguos são procurados em todos os metadados. Letras de músicas, nomes próprios, assuntos históricos e descrições longas podem bloquear itens legítimos. Não retirar a segurança: ajustar regras por campo e contexto. Termos genéricos não devem ter o mesmo peso em título, identifier, nome do arquivo, descrição longa, coleção e licença.

### moderacao/nsfwjs/moderar-catalogo.js
Lê catalog.json, remove duplicados, aplica uma segunda blocklist textual, analisa miniaturas via analisarUrl, conta motivos de rejeição e só grava o catálogo moderado se ao menos um item for aprovado. Atualiza os JSONs por categoria.

Última correção: usa miniatura padrão do Archive se thumbnail, thumb e cover não estiverem preenchidos: https://archive.org/services/img/{identifier}. Também registra contagens por motivo de rejeição. Erros individuais são rejeitados com falha fechada. Se todos falharem, lança erro e bloqueia publicação.

Ponto técnico a revisar: o script grava catalog.json antes de atualizar arquivos individuais em catalog/. O workflow faz backup e restaura localmente se uma etapa falhar, mas é melhor manter atualização atômica/consistente quando possível.

### moderacao/nsfwjs/classificar.js
Carrega NSFWJS e TensorFlow.js. Baixa imagens HTTPS apenas de archive.org/www.archive.org, limita o tamanho a 8 MB e timeout a 15 segundos, classifica a imagem e rejeita quando Porn > 0.3, Sexy > 0.6 ou Hentai > 0.3. Falhas de download, decodificação ou modelo são rejeitadas com motivo explícito. Isso analisa a capa, não o vídeo inteiro.

### moderacao/nsfwjs/package.json
Dependências de moderação: @tensorflow/tfjs-node e nsfwjs; requer Node >=20.

### catalog.json
Catálogo consolidado consumido pelo app. Deve conter objeto raiz com items como lista não vazia. Cada item precisa de identifier, title, files e URL reproduzível.

### catalog/*.json
Arquivos individuais por categoria; gerados pelo coletor e sincronizados após moderação.

### README.md
Documentação do repositório. Pode estar desatualizada: descreve meta anterior de 1.000 candidatos/160 verificações em vez dos 2.000 configurados no workflow. Atualizar para evitar confusão.

## 5. Últimas alterações

1. Commit 2d919c6 — “fix(coletor): preserva catálogo se a coleta resultar vazia”
   - impede que o coletor escreva catálogo novo vazio;
   - grava os arquivos de forma temporária/atômica;
   - mantém o catálogo anterior no repositório quando a coleta falha, com backup/restauração do workflow.

2. Commit 456e97e — “fix(moderacao): usa capa padrão e registra motivos de rejeição”
   - tenta miniatura padrão do Archive;
   - registra contagens dos motivos de rejeição;
   - bloqueia publicação se zero itens forem aprovados.

3. Commit 8088c6a — reforçou a blocklist de coleções adultas e tratamento de erros no script de moderação.

As alterações foram gravadas no GitHub, mas as execuções #20 e #21 falharam. Não considerar as correções validadas só porque houve commit. Pages #32 concluiu com sucesso; isso confirma a publicação do site, não o sucesso do catálogo.

## 6. Próximos passos recomendados

1. Não disparar vários workflows. Consultar os logs mais recentes antes de iniciar outra execução.
2. Auditar is_family_safe em scripts/coletar.py e as consultas CATS. Prioridade: reduzir falsos positivos contextuais sem enfraquecer bloqueios de pornografia, exploração sexual, violência gráfica e conteúdo impróprio.
3. Adicionar contagens por categoria: resultados recebidos da API, rejeitados pelo filtro textual, duplicados, enviados para metadata, sem arquivo de vídeo e aprovados.
4. Distinguir falha de consulta/API de zero resultados reais. Não interpretar uma falha da API como prova de conteúdo inseguro.
5. Criar testes para itens legítimos e proibidos antes de executar o workflow. Proteger concertos, clipes musicais, documentários, cinema clássico e animação infantil; bloquear pornografia explícita, coleções adultas e violência gráfica explícita.
6. Quando o coletor entregar itens reproduzíveis, verificar relatório NSFWJS. Se muitas capas forem rejeitadas por IMAGEM_INDISPONIVEL ou ANALISE_INDISPONIVEL, investigar o acesso às imagens/modelo antes de alterar os limiares.
7. Validar o catálogo final e o site consumidor, preservando o catálogo anterior até existir um novo catálogo válido.

## 7. Regras para o próximo diálogo

- Responder em português do Brasil.
- O usuário trabalha principalmente pelo celular; dar instruções simples e passo a passo.
- Distinguir fatos confirmados de hipóteses.
- Não afirmar que o pipeline passou sem conferir logs.
- Não reduzir TARGET_CANDIDATES=2000 nem MAX_METADATA_CHECKS=2000.
- Não adicionar Supabase, Edge Functions ou serviços novos.
- Não remover a proteção contra publicação de catálogo vazio.
- Não aprovar automaticamente itens quando NSFWJS falha; registrar motivos e investigar.
- O objetivo é corrigir a moderação e a coleta, não reconstruir o app.

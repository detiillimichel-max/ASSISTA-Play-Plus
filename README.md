# ASSISTA+ — Catálogo familiar de fontes públicas

Repositório independente para coletar metadados públicos de fontes de vídeo autorizadas e publicar um catálogo JSON para aplicativos consumidores, como o PLAYORA.

## Arquivos
- `catalog.json`: catálogo consolidado.
- `catalog/*.json`: um arquivo por categoria, gerado pelo coletor.
- `scripts/coletar.py`: busca, deduplicação e validação de arquivos de vídeo.
- `scripts/cache.py`: cache local de respostas das APIs com validade de cinco dias.
- `moderacao/politica.json`: perfil familiar estrito e limiares de moderação.
- `moderacao/blocklist.json`: identificadores bloqueados de forma persistente.
- `.github/workflows/coletar.yml`: execução manual e diária.

## Executar agora
1. Abra a aba **Actions**.
2. Selecione **Atualizar catálogo Internet Archive**.
3. Toque em **Run workflow** e confirme.
4. Abra a execução mais recente e acompanhe os passos.

O workflow pesquisa candidatos distribuídos entre oito categorias e fontes adicionais. Para limitar o volume de chamadas, usa cache de cinco dias e no máximo 30% do orçamento de requisições configurado por API. A contagem final depende dos arquivos de vídeo realmente encontrados e aprovados.

## Fonte e direitos
A existência de um arquivo em qualquer fonte não significa que seja de domínio público nem que possa ser redistribuído. Confira os direitos e a licença de cada item antes de usá-lo.

Secrets são usados somente no GitHub Actions e nunca são enviados ao GitHub Pages ou gravados no catálogo. A moderação está temporariamente pausada no workflow (`PAUSE_MODERATION=true`) para diagnosticar a coleta de fontes; durante esse período, o catálogo não é certificado como familiar.

A playlist é armazenada localmente no navegador. A atualização do catálogo não remove nem renova automaticamente os itens salvos; o usuário decide quando remover uma entrada indisponível.

# Lista M3U SO Play para SS IPTV

Gerador automatico de uma lista `.m3u` a partir de **https://soplay.com.br/canais**,
otimizada para o **SS IPTV**, publicada no GitHub e **atualizada a cada 6 horas**.

## O que ele faz

- **Atualiza a cada 6h** via GitHub Actions.
- **Nao apaga canais que funcionam.** So remove um canal depois de **3
  atualizacoes seguidas** sem funcionar (regra das 3 falhas). O contador fica
  em `estado_canais.json`.
- **Categorias unificadas:**
  - nomes iguais em MAIUSCULA/minuscula viram uma so (`Noticias` = `noticias` = `NOTICIAS`);
  - sinonimos viram uma so categoria. Exemplos ja mapeados:
    - `Noticias`, `News`, `Jornalismo` -> **Noticias**
    - `Desenhos`, `Kids`, `Infantil`, `Crianca`, `Cartoon` -> **Infantil**
    - `Cinema`, `Filmes`, `Movies` -> **Filmes**
    - `Esportes`, `Sports`, `Futebol` -> **Esportes**
    - (e outros: Series, Musica, Documentarios, Religiosos, Variedades, Abertos, 24 Horas...)
  - Para adicionar/alterar grupos, edite a lista `SINONIMOS` no topo de
    `gerar_soplay.py`.
- **Sem canais duplicados:** se dois canais tiverem o **mesmo link**, mantem só um.
- **Protecao anti-queda:** se a fonte inteira ficar fora do ar, a lista
  anterior e preservada (nao conta como falha dos canais).

## Como usar

### 1) Primeira geracao no seu PC (Brasil)
O catalogo completo do SO Play depende de IP do Brasil. Rode uma vez localmente:

1. Instale o Python do site **python.org** marcando *"Add python.exe to PATH"*.
2. De dois cliques em **`rodar_no_brasil.bat`**.
3. Se aparecer erro de fonte, abra `soplay.com.br/canais` no navegador,
   pressione **F12 > aba Network (XHR/Fetch)**, copie a URL que retorna a lista
   de canais (e o token `Authorization`, se houver) e preencha `SOPLAY_API` /
   `SOPLAY_TOKEN` dentro do `.bat`.

### 2) Publicar no GitHub
1. Crie um repositorio (pode ser publico) e envie todos estes arquivos.
2. Faca o commit do `playlists/soplay.m3u` e do `estado_canais.json` gerados no passo 1.
3. Em **Settings > Secrets and variables > Actions**, se precisou de endpoint/token,
   crie os segredos `SOPLAY_API` e `SOPLAY_TOKEN`.
4. O workflow `.github/workflows/update.yml` roda sozinho a cada 6h
   (ou manualmente em **Actions > Run workflow**).

### 3) Adicionar no SS IPTV
Use o link **raw** do arquivo:
```
https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/playlists/soplay.m3u
```
No SS IPTV: **Configuracoes > Conteudo > Adicionar > Link externo** e cole a URL.

> **Botoes em tamanho medio:** o tamanho dos botoes/tiles e um ajuste do proprio
> SS IPTV (Configuracoes de aparencia do app), nao do arquivo M3U. A lista ja
> vem com `group-title` (categorias) e `tvg-logo` (logos) para que os tiles
> fiquem organizados e bonitos no tamanho medio.

## Variaveis de ambiente

| Variavel | Para que serve |
|----------|----------------|
| `SOPLAY_API`   | URL do endpoint JSON de canais (capturado no F12). |
| `SOPLAY_TOKEN` | Token/Authorization, se a API exigir. |
| `SOPLAY_CHECK` | `1` = testa se cada `.m3u8` responde (use so no Brasil). |
| `SOPLAY_DEBUG` | `1` = salva respostas cruas em `debug_soplay/`. |

## Arquivos

```
gerar_soplay.py                 Gerador (somente biblioteca padrao do Python)
playlists/soplay.m3u            Lista gerada (consumida pelo SS IPTV)
estado_canais.json             Estado/contador de falhas dos canais
rodar_no_brasil.bat            Rodar localmente no Windows (Brasil)
.github/workflows/update.yml   Automacao a cada 6h no GitHub Actions
```

## Observacao legal
O SO Play e um servico de streaming legalizado. Esta ferramenta apenas organiza,
para uso pessoal no SS IPTV, os canais que o proprio servico disponibiliza.

# SO Play M3U automático → SS IPTV

Playlist `.m3u` do ecossistema **SO Play / NxPlay**, otimizada para **SS IPTV**,
**atualizada sozinha a cada 6 horas** no GitHub.

## Funciona sozinho?

| Situação | O que acontece |
|----------|----------------|
| Só subir o repo (sem secrets) | Usa `seed/` + fontes públicas (iptv-org etc.) e a regra das 3 falhas |
| Você rodou 1x no Brasil | Seed fica rico; Actions só mantém/atualiza |
| Secrets `SOPLAY_API` + `SOPLAY_TOKEN` | Captura o catálogo oficial a cada 6h |

**Não precisa de secrets** para a lista continuar viva. Secrets só melhoram a quantidade de canais novos.

## O que o script faz

- Atualiza a cada **6 horas** (GitHub Actions)
- **Não apaga** canal que ainda funciona
- Só remove depois de **3 atualizações seguidas** sem o canal (estado em `estado_canais.json`)
- Junta categorias iguais/sinônimas (Notícias/News, Infantil/Kids/Desenhos, Filmes/Cinema…)
- Remove links **duplicados**
- `#EXTSIZE: medium` → botões médios no SS IPTV
- Limpa `?token=` efêmero dos links quando possível
- **Auto-atualiza o seed** com os canais que estão ok

## Uso rápido

### 1) Publicar no GitHub (modo automático)

1. Crie um repositório e envie **esta pasta inteira**.
2. Actions → **Atualizar playlist SO Play (auto)** → *Run workflow* (1ª vez).
3. Link da lista:
   ```
   https://raw.githubusercontent.com/SEU-USUARIO/SEU-REPO/main/playlists/soplay.m3u
   ```
4. No SS IPTV: Configurações → Conteúdo → Listas externas → cole o link.

Pronto. A cada 6h o bot atualiza sozinho.

### 2) (Recomendado) Enriquecer no Brasil

No PC com IP brasileiro:

1. Instale Python (marque “Add to PATH”).
2. Rode `rodar_no_brasil.bat`.
3. Faça commit de `seed/soplay_seed.m3u`, `playlists/soplay.m3u` e `estado_canais.json`.

### 3) (Opcional) Token oficial

1. Login em https://soplay.com.br/canais  
2. F12 → Network → procure `gateway.nxtv.com.br` ou `channels`  
3. Copie a URL e o header `Authorization`  
4. GitHub → Settings → Secrets → Actions:
   - `SOPLAY_API`
   - `SOPLAY_TOKEN`

## Estrutura

```
gerar_soplay.py              # script (só biblioteca padrão)
rodar_no_brasil.bat          # atalho Windows
seed/soplay_seed.m3u         # base automática
playlists/soplay.m3u         # lista final (commitada pelo bot)
estado_canais.json           # contador de falhas
.github/workflows/update.yml # cron 6h
```

## Link para o SS IPTV

```
https://raw.githubusercontent.com/SEU-USUARIO/SEU-REPO/main/playlists/soplay.m3u
```

## Aviso

Conteúdo das emissoras e da plataforma SO Play. Uso pessoal/educacional. Respeite os termos do serviço.

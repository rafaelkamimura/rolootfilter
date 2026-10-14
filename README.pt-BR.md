**[English](README.md)** · **Português (BR)**

# RO Loot Filter

Um filtro de loot no estilo Path of Exile para o **Ragnarok Online LATAM**, feito inteiramente do
lado do cliente. Ele deixa os drops que importam grandes e brilhando e torna os lixos de vendor
invisíveis, reescrevendo os sprites de item no chão dentro do `data.grf` conforme regras que você
controla.

![icon](assets/rolf.png)

| ação          | o que você vê no jogo                                                        |
|---------------|------------------------------------------------------------------------------|
| `size = 4`    | o sprite do drop ampliado 4x (qualquer fator de 1 a 6)                       |
| `glow`        | um halo colorido atrás do drop; `auto` usa a cor do próprio item             |
| `hide`        | sprite transparente de 1x1 px, o drop fica invisível no chão                 |
| `effect_id`   | grava o `EffectID` do item no `iteminfo_new.lub` (o efeito de drop que o Pó de Éter tem, controlado pelo servidor) |

Tudo é reversível com um clique, e a ferramenta se recalibra sozinha depois de patches oficiais.

---

## Para jogadores: o .exe

1. Baixe o `RO Loot Filter.exe` na [última release](../../releases/latest).
2. **Feche o jogo.** Apply e Revert se recusam a rodar com o `Ragexe.exe` aberto.
3. Execute o .exe. O SmartScreen do Windows pode avisar sobre editor desconhecido; clique em
   *Mais informações → Executar assim mesmo*. (É um build PyInstaller de arquivo único, sem
   assinatura; nada é instalado.)
4. Confira a **Client folder** no topo. `C:\Gravity\Ragnarok` é detectada automaticamente; se o
   seu cliente estiver em outro lugar, clique em *Browse…* e escolha a pasta que contém o `data.grf`.
5. Clique em **APPLY**. A primeira execução leva cerca de um minuto: ela tira um snapshot do seu
   `data.grf` intocado, lê a tabela de itens, monta os sprites e grava. O log embaixo mostra o
   progresso e termina com `verify: N/N files read back identical`.
6. Abra o jogo. Runas, materiais de Éter e os outros itens destacados aparecem grandes e
   brilhando; Jellopy e companhia somem do chão.

**Revert** restaura o `data.grf` e o `iteminfo_new.lub` originais exatamente como eram. Faça isso
antes de reportar qualquer bug do cliente ao suporte e sempre que quiser o visual padrão de volta.

### Editando regras na interface

* **Rules** (esquerda): avaliadas de cima para baixo, a primeira que casar decide. Reordene com
  ▲▼, selecione uma para editar, `+ new` cria outra.
* **Rule** (centro): case por IDs de item (`909, 1000636-1000643`), por regex no resource name,
  no nome em pt-BR ou na descrição, ou por um EffectID já existente. Defina size, glow, hide,
  "continue to later rules" e se a regra está ativa. Clique em **Update rule** para gravar.
  A lista em *Matches* mostra exatamente quais itens a regra pega no momento.
* **Preview** (direita): render antes/depois do item selecionado. Busque itens por nome,
  resource ou id; o botão `+` adiciona aquele id à regra atual.
* **Save** grava o `filter.toml`; **Dry run** mostra o plano sem mexer no cliente.

### Onde ficam as coisas

| | |
|---|---|
| suas regras       | `filter.toml` ao lado do .exe, se existir; senão `%LOCALAPPDATA%\RoLootFilter\filter.toml` |
| snapshots/cache   | `%LOCALAPPDATA%\RoLootFilter\cache` (header original do GRF, iteminfo original, sprites originais extraídos) |
| previews          | `%LOCALAPPDATA%\RoLootFilter\preview\*.png` |

Colocar um `filter.toml` ao lado do .exe é o jeito fácil de distribuir um filtro já ajustado para a guild.

### Depois de um patch oficial

O patcher reescreve o `data.grf`, o que derruba as modificações. É só abrir a ferramenta e clicar
em **APPLY** de novo: ela percebe que o arquivo mudou, tira um snapshot novo e reaplica as regras.

---

## Para desenvolvedores: rodando do código

Requisitos: Python 3.11+ (testado no 3.14), Windows.

```
pip install lupa customtkinter pillow      # lupa = VM Lua 5.1 usada para executar o iteminfo_new.lub
python rolfgui.py                           # a interface
python rolf.py apply [filter.toml] [--dry] [--no-preview]
python rolf.py revert
python rolf.py status
python rolf.py search "Éter|Runa"           # acha ids / resource names para escrever regras
```

Rodando do código, o estado fica em `cache/` e `preview/` dentro do projeto (ambos no gitignore).

### Gerando o .exe

```
pip install pyinstaller
.\build.ps1                                  # -> dist\RO Loot Filter.exe
```

### Referência do arquivo de regras

```toml
[settings]
client = 'C:\Gravity\Ragnarok'
glow_alpha = 200          # opacidade máxima do halo, 0-255
glow_scale = 1.9          # diâmetro do halo relativo ao sprite ampliado
patch_iteminfo = true     # permite que regras com effect_id reescrevam System\iteminfo_new.lub

[[rule]]
name = "Barmund rune fragments"
ids = ["1000636-1000639"]           # inteiros ou faixas "a-b"
size = 6
glow = "auto"                       # "auto" | "#rrggbb" | "none"
effect_id = 1870

[[rule]]
name = "Aether family"
resource = "^(HD_|Blessed_)?Etel_"  # regex no identifiedResourceName
size = 4
glow = "auto"

[[rule]]
name = "Hide vendor trash"
ids = [909, 914, 705, 916, 938]
hide = true

# outras chaves de match: name_match (regex no nome pt-BR), description (regex),
#                         effect (o item já tem esse EffectID), min_id, max_id
# outras ações:           continue = true (segue avaliando), unidentified = true (também altera o
#                         sprite não identificado; é compartilhado por muitos equips, use com cuidado),
#                         enabled = false
```

Uma regra com várias chaves de match exige que todas casem. Regra sem nenhuma chave de match é erro.

### Como funciona

* O `data.grf` é GRF **0x300** (assinatura "Event Horizon", offsets de 64 bits, tabela de arquivos
  no meio do arquivo). O patch é só append: os novos blobs de sprite e uma tabela reconstruída são
  escritos depois do fim antigo do arquivo e o ponteiro de 8 bytes da tabela no header é
  redirecionado. Revert é "restaurar os 46 bytes do header e truncar". Nada pré-existente é
  sobrescrito.
* Entradas clássicas são criptografadas (flag 3 mista, flag 5 só header). A cifra da Gravity é um
  único round de DES sem chave (IP, L ^= F(R), FP) nos primeiros 20 blocos, depois um bloco a cada
  `cycle` blocos mais um embaralhamento de bytes a cada 7º bloco restante. Veja `rolfcore/grfdes.py`
  e `grf.py`.
* Os sprites de item são `data\sprite\아이템\<resource>.spr/.act` (nome da pasta em CP949, que
  aparece como `¾ÆÀÌÅÛ` em ferramentas Latin-1; os nomes são minúsculos dentro do GRF). SPR v2.1
  (frames de paleta com RLE, frames ABGR) e ACT 2.0-2.5 (sempre regravado como 2.5). O halo é um
  frame ABGR extra inserido como layer 0.
* O `iteminfo_new.lub` é bytecode Lua 5.1 de 32 bits com strings UTF-8 que só define `tbl`.
  Ele é executado transcodificando `size_t` 4→8 e rodando na VM Lua 5.1 do lupa com todos os
  globais stubados; é reconstruído com `string.dump`, transcodificado de volta e verificado em
  round-trip antes de instalar. O `iteminfo_f.lub` tem o `main()`, que chama
  `AddItemEffectInfo(id, EffectID)`.
* `EffectID 1870` é o que dá ao Pó de Éter o brilho no drop. O servidor decide por drop se o efeito
  toca, então `effect_id` é melhor esforço; o halo embutido é a parte que sempre aparece.

### Estrutura

```
rolf.py            CLI
rolfgui.py         interface (customtkinter)
rolfcore/engine.py apply / revert / status, lógica de snapshot
rolfcore/grf.py    leitor GRF 0x300 + escrita por append     rolfcore/grfdes.py  cifra da Gravity
rolfcore/sprite.py parsing SPR/ACT, transformações, render   rolfcore/iteminfo.py carga/rebuild do lub
rolfcore/rules.py  matching de regras                        rolfcore/tomlout.py  gravação do filtro
filter.toml        as regras                                 build.ps1            build do exe
```

## Status

Testado no RO LATAM (cliente de 01/10/2026, conteúdo do Episódio 18 + Ecosfera de Varmundt). O
filtro incluído destaca as runas de Varmunt, a família de Éter, materiais do Episódio 18 e as
Lágrimas Temporais, e esconde 28 drops de lixo de vendor.

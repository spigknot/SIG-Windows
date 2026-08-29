
## 2. Ferramenta: Extrair Áudio (`_extract_worker`)

### 2.1. Opções da UI e Mapeamento

| Opção da UI | Variável Tkinter | Código | Comando FFmpeg | Status |
|---|---|---|---|---|
| Arquivos de entrada | `self.extract_inputs` (list[Path]) | `select_extract_inputs()` | `-i <source>` (multiplo) | ✅ |
| Padrão transcrição | `self.extract_transcription_preset_var` (BooleanVar) | `_set_extract_preset("transcription")` | Fixa: WAV / 16000 Hz / mono / 256k | ✅ |
| Padrão compacto | `self.extract_compact_preset_var` (BooleanVar) | `_set_extract_preset("compact")` | Fixa: OGG / 16000 Hz / mono / 32k | ✅ |
| Formato | `self.extract_extension_var` (StringVar → "wav") | `_audio_codec_args()` | determina `-c:a`, `-f` | ✅ |
| Hz | `self.extract_rate_var` (StringVar → "16000") | combo com valores validados | `-ar <rate>` | ✅ |
| Canais | `self.extract_channels_var` (StringVar → "1") | combo | `-ac <channels>` | ✅ |
| Bitrate | `self.extract_bitrate_var` (StringVar → "64k") | `_refresh_extract_bitrate_choices()` | `-b:a <bitrate>` | ✅ |
| Recorte início | `self.extract_start_var` (StringVar → "") | `_seconds(allow_empty=True)` | `-ss <start>` (opcional) | ✅ |
| Recorte fim | `self.extract_end_var` (StringVar → "") | `_seconds(allow_empty=True)` | `-t <duration>` (opcional) | ✅ |

### 2.2. Validação de Combinações (UI → Codec)

| Formato | Encoder FFmpeg | Args | Bitrate? | Obs |
|---|---|---|---|---|
| WAV | `-c:a pcm_s16le -f wav` |  | ❌ (lossless) | ✅ |
| MP3 | `-c:a libmp3lame -b:a <br> -minrate <br> -maxrate <br>` | fix bitrate | ✅ | ✅ |
| M4A | `-c:a aac -b:a <br> -movflags +faststart` |  | ✅ | ✅ |
| AAC | `-c:a aac -b:a <br>` |  | ✅ | ✅ |
| OGG | `-c:a libvorbis -b:a <br>` |  | ✅ | ✅ |
| OPUS | `-c:a libopus -application voip -b:a <br> -vbr off` | CBR | ✅ | ✅ |
| FLAC | `-c:a flac` |  | ❌ (lossless) | ✅ |
| WMA | `-c:a wmav2 -b:a <br>` |  | ✅ | ✅ |

### 2.3. Comando Final

```
ffmpeg -hide_banner -y [-ss <start>] -i <source> [-t <duration>] -vn -map 0:a:0? -ar <rate> -ac <channels> <codec_args> <output>
```

- `-ss` **antes** de `-i`: seek rápido ✅
- `-vn`: remove vídeo ✅
- `-map 0:a:0?`: áudio opcional ✅
- Para presets, os campos são `disabled` via UI ✅

### 2.4. Findings — Extrair

✅ **Correto.** Todos os controles da UI refletem nos argumentos. A validação de bitrate para OGG/Vorbis (`VORBIS_VALID_BITRATES`) é sofisticada e correta. A desabilitação de bitrate para WAV/FLAC quando bloqueado por preset também está correta.

**Pendente:** Na linha 3896, o comando usa `self._audio_codec_args(extension, bitrate)` — mas o `extension` vem de `self.extract_extension_var.get().lower()` que retorna "wav", "mp3", etc. (sem o ponto). E `_audio_codec_args` faz `ext = extension.lower().lstrip(".")`. Portanto, "wav" → "wav". **Funciona, mas é confuso** — a variável `extension` contém apenas o nome sem ponto, mas `_audio_codec_args` também faz `.lstrip(".")`. Redundante, mas não bug.

**⚠️ POSSÍVEL BUG (não crítico):** Na linha 3896, o output é construído com `f".{extension}"`, então a extensão correta com ponto é passada. Mas `_audio_codec_args` espera a extensão com ou sem ponto — o `.lstrip(".")` trata ambos. **OK.**

---

## 3. Ferramenta: Girar Vídeo (`_rotate_worker`)

### 3.1. Opções da UI e Mapeamento

| Opção da UI | Variável Tkinter | Código | Comando FFmpeg | Status |
|---|---|---|---|---|
| Arquivo de entrada | `self.rotate_input` (Path) | `select_rotate_input()` | `-i <source>` | ✅ |
| Graus de rotação | `self.rotate_degrees_var` (StringVar → "90") | `_rotate_worker()` | `transpose=1` (90), `transpose=2` (-90), `hflip,vflip` (180) | ✅ |
| Espelhar H | `self.rotate_hflip_var` (BooleanVar) | `_rotate_worker()` | `+hflip` | ✅ |
| Espelhar V | `self.rotate_vflip_var` (BooleanVar) | `_rotate_worker()` | `+vflip` | ✅ |
| Metadata only | `self.rotate_metadata_var` (BooleanVar → True) | `_rotate_worker()` | `-display_rotation:v:0 <N>` + `-c copy` | ✅ |
| Processar paralelo | `self.rotate_parallel_var` (BooleanVar) | `_rotate_worker()` | Segmentação + concat | ✅ |
| Trechos | `self.rotate_segments_var` (StringVar → "") | `_rotate_video_parallel()` | Controla nº de workers | ✅ |
| Encoder | `self.acceleration_var` (Combobox) | `_video_args()` | `-c:v <encoder>` | ✅ |
| Qualidade | `self.video_quality_var` (StringVar → "Alta") | `_video_args()` | CRF/bitrate | ✅ |
| Recorte início/fim | `self.rotate_start_var` / `self.rotate_end_var` | `_seconds()` | `-ss <start>` / `-t <duration>` | ✅ |

### 3.2. Comando — Modo Metadata-Only (linhas 3927-3949)

```
ffmpeg -hide_banner -y [-display_rotation:v:0 <target_rotation>] [-ss <start>] -i <source> [-t <duration>] -map 0 -c copy <output>
```

- `-display_rotation:v:0`: **antes** de `-i` ✅ (entrada, conforme F-02/F-03)
- `-map 0`: preserva todos os streams ✅
- `-c copy`: sem reencode ✅
- Validação MP4_SAFE_AUDIO_CODECS antes de `-c copy` ✅

**⚠️ FINDING CRÍTICO 3-A:** A checagem de codecs seguros para MP4 (linhas 3937-3943) **só valida MP4** (`output.suffix.lower() == ".mp4"`). Quando `rotate_metadata_var=True` e o source é `.mkv`/`.webm`/`.mov`, o output preserva o container (`_metadata_rotate_output_suffix` retorna o mesmo suffix). Mas a validação de codecs MP4-safe **não roda nesses containers** — o código pula a checagem. Isso é intencional? O Android auditou isso e concluiu que para MKV o `-c copy` é seguro. **No entanto**, se o usuário tentar "metadata-only" com um AVI (output `.mp4` via fallback), o código converte para MP4 e valida. ✅ OK.

### 3.3. Comando — Modo Reencodar (linhas 3992-3996)

```
ffmpeg -hide_banner -y [<vaapi_args>] [<seek_args>] -i <source> [<duration_args>]
-map 0:v:0 -map 0:a? <filter_args> <video_args> <audio_args>
-map_metadata -1 -metadata:s:v:0 rotate=0 -movflags +faststart <output>
```

- `-map_metadata -1`: limpa todos os metadados ✅
- `-metadata:s:v:0 rotate=0`: zera a rotação ✅
- `-movflags +faststart`: streaming otimizado ✅
- Audio: `-c:a copy` se codec compatível, `-c:a aac` caso contrário ✅

### 3.4. Comando — Preview de Rotação (`_rotate_preview_filter`, linhas 2999-3015)

```
filters = "transpose=1,hflip"  # exemplo
```

Usado em `_show_video_thumbnail` (linha 3038-3039):
```
ffmpeg -hide_banner -loglevel error -y -ss <sec> -i <source> -frames:v 1 [-vf <filters>] <png>
```

✅ Preview do *thumbnail* reflete rotação + flip.

### 3.5. Comando — Preview de Vídeo (`_start_canvas_preview`, linhas 2762-2765)

```
ffmpeg -hide_banner -loglevel error -ss <offset> -i <source> -t <duration> -an -vf <filters> -pix_fmt rgb24 -f rawvideo pipe:1
```

Filtros via `_preview_video_filters()`:
```
setpts=PTS/<speed>, fps=<fps>, scale=<w>:<h>:force_original_aspect_ratio=decrease, pad=<w>:<h>:(ow-iw)/2:(oh-ih)/2, setsar=1
```

**⚠️ FINDING CRÍTICO 3-B:** Na linha 2527:
```python
use_canvas = self.preview_speed != 1.0 or (context["tool"] == "rotate" and bool(self._rotate_preview_filter()))
```

Quando `preview_speed == 1.0` e a ferramenta é "rotate" com rotação/filtros ativos, usa canvas (FFmpeg). **Mas** quando `preview_speed == 1.0` e NÃO há filtros de rotação, cai no `EmbeddedMediaPlayer` (MCI). O problema: **o MCI não aplica `-noautorotate`**. Isso significa que se o arquivo tem metadados de rotação (ex: 90°), o preview via MCI mostrará o vídeo já rotacionado, enquanto o processamento (modo metadata-only) preserva a rotação original. **Inconsistência entre preview e processamento.**

### 3.6. Comando — Preview de Áudio (`_start_canvas_preview`, linhas 2736-2746)

```
ffplay -hide_banner -loglevel warning -autoexit -nodisp -ss <offset> -t <duration> -af <atempo_filter> <source>
```

✅ Correct.

### 3.7. Comando — Processar Paralelo (`_rotate_video_parallel`, linhas 4003-4116)

A lógica divide o vídeo por keyframes, roda segmentos em paralelo e concataena. **⚠️ FINDING CRÍTICO 3-C (linha 4017):**

```python
is_hw = bool(self.acceleration and self.acceleration.key in {"nvenc", "qsv", "amf"})
default_workers = min(3, max(1, os.cpu_count() or 1)) if is_hw else max(1, os.cpu_count() or 1)
```

A linha 4018-4019:
```python
if len(keyframes) < requested_workers - 1:
    split_points = keyframes
```
Se `len(keyframes) == 0` (vídeo sem keyframes internos), levanta RuntimeError em linha 4121. **Mas** a verificação acontece **depois** de tentar pegar keyframes (linha 3981), que filtra `0.1 < value < duration - 0.1`. Se todos os keyframes estão fora desse range, `keyframes` fica vazio e o erro é levantado. Isso é tratado. ✅

**⚠️ FINDING 3-D:** Na segmentação (linha 4045-4048):
```
ffmpeg -hide_banner -y -i <source> -map 0 -c copy -f segment -segment_times <times> -reset_timestamps 1 -segment_format mp4 -avoid_negative_ts make_zero <pattern>
```
Usa `-c copy` para segmentar. Mas o encoder de vídeo selecionado (`self.acceleration`) **não é usado aqui** — a segmentação é sempre copy. O encoder só é aplicado nos segmentos individuais (linha 4067-4073). Isso é **correto** — você não reencodifica para dividir.

**⚠️ FINDING 3-E (possível):** Na linha 4108:
```
ffmpeg -hide_banner -y -f concat -safe 0 -i lista.txt -c copy -map_metadata -1 -metadata:s:v:0 rotate=0 -movflags +faststart <output>
```
O concat final usa `-c copy` e não aplica o encoder selecionado. Isso é intencional — após a rotação individual dos segmentos, o concat preserva tudo. ✅

### 3.8. Findings — Girar

| Finding | Severidade | Descrição |
|---|---|---|
| 3-A | ✅ OK | Validação MP4-safe para metadata-only correta |
| 3-B | ⚠️ Média | Preview via MCI não reflete rotação de metadados — preview mostra vídeo rotacionado, mas processamento preserva orientação original |
| 3-C | ✅ OK | Lógica paralela sólida, fallback para single process |
| 3-D | ✅ OK | Segmentação usa `-c copy` corretamente |
| 3-E | ✅ OK | Concat final preserva segmentos sem reencode |

---

## 4. Ferramenta: Juntar Áudios/Vídeos (`_join_worker`)

### 4.1. Opções da UI e Mapeamento

| Opção da UI | Variável Tkinter | Código | Comando FFmpeg | Status |
|---|---|---|---|---|
| Arquivos | `self.join_inputs` (list[Path]) | `add_join_inputs()` | `-i <path>` (multiplo) | ✅ |
| Reencode Completo | `self.join_reencode_var` (BooleanVar) | `_on_toggle_join_reencode()` | `_xfade_join_filter()` / `_fade_join_filter()` | ✅ (mutua exclusão com SmartJoin) |
| Smart Join | `self.join_smart_var` (BooleanVar) | `_on_toggle_join_smart()` | `_join_smart_hybrid` / `_join_fade_hybrid` | ✅ (mutua exclusão) |
| Transição | `self.join_transition_var` (StringVar → "Fade in/out") | `_update_join_controls()` | `xfade` filter | ✅ |
| Tempo transição | `self.join_seconds_var` (StringVar → "0.5") | float parsing | duração do xfade | ✅ |
| Encoder | `self.acceleration_var` (Combobox) | `_video_args()` | `-c:v <encoder>` | ✅ |
| Qualidade | `self.video_quality_var` | `_video_args()` | CRF/bitrate | ✅ |
| Paralelo | N/A (join não tem paralelo direto) | N/A | N/A | ✅ |

### 4.2. Comandos (caminhos múltiplos)

**A. Copy only (sem reencode, sem smart):**
```
ffmpeg -hide_banner -y -f concat -safe 0 -i list.txt -c copy -movflags +faststart <output>
```

**B. Smart Join sem perda (smart=True, transition=0):**
```
ffmpeg -hide_banner -y -f concat -safe 0 -i list.txt -c copy -movflags +faststart <output>
```
+ validações de compatibilidade (`_validate_smart_video_compatibility`)

**C. Smart Join com transição (`_join_smart_hybrid`):**
- Body copy: `-c:v copy -bsf:v <bitrate_filter> -c:a aac -ar <rate> -ac <ch>`
- Transition: filtro xfade complexo
- Final: `-c copy -bsf:a aac_adtstoasc`

**D. Full reencode (`_xfade_join_filter` / `_fade_join_filter`):**
```
ffmpeg -hide_banner -y -i <input1> -i <input2> ... -filter_complex "<filters>" -map [vout] -map [aout] <video_args> -r <fps> <join_audio_args> -movflags +faststart <output>
```

### 4.3. Filters — `_xfade_join_filter` (linhas 4789-4808)

```python
last_video, last_audio = "v0", "a0"
for index in range(1, len(clips)):
    offset = max(0.0, accumulated - seconds)
    parts.append(f"[{last_video}][v{index}]xfade=...")
    parts.append(f"[{last_audio}][a{index}]acrossfade=...")
    last_video, last_audio = video_out, audio_out
    accumulated += clips[index][0] - seconds
parts.append(f"[{last_video}]copy[vout]")
parts.append(f"[{last_audio}]acopy[aout]")
```

**⚠️ FINDING CRÍTICO 4-A:** Linhas 4806-4807:
```python
parts.append(f"[{last_video}]copy[vout]")
parts.append(f"[{last_audio}]acopy[aout]")
```

O filtro `copy` é um filtro de vídeo **que não existe** no FFmpeg. O filtro correto para passthrough é `null` (ou simplesmente não aplicar nenhum filtro). `copy` não é um filtro válido. **Isso causará falha no FFmpeg quando há mais de 2 clipes com transição.**

Deve ser:
```python
parts.append(f"[{last_video}]null[vout]")
parts.append(f"[{last_audio}]anull[aout]")
```

**⚠️ FINDING CRÍTICO 4-B:** Linha 4774-4776 (`_fade_join_filter`):
```python
video = (
    f"[{index}:v]scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=decrease,"
    f"pad={profile['width']}:{profile['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={profile['fps']},format=yuv420p"
)
```
Para o `xfail_join_filter`, a última etapa adiciona `format=yuv420p` no próprio xfade (linha 4802):
```python
parts.append(f"[{last_video}][v{index}]xfade=transition={transition_name}:duration=...:offset=...,format=yuv420p[{video_out}]")
```
Isso é **redundante** se o normalize já inclui `format=yuv420p`. Mas como o xfade pode produzir formatos diferentes, é defensivo. **OK.**

### 4.4. Validações

- `_validate_video_copy_compatibility` (linhas 4310-4362): valida codec, resolução, fps, pix_fmt, timebase, áudio. **Extensivo e correto.**
- `_validate_smart_video_compatibility` (linhas 4467-4478): valida apenas width/height/fps/pix_fmt/timebase/codec. **Mais permissivo que o copy** — intencional, pois Smart Join normaliza via filtros. ✅

### 4.5. `_join_audio_args` (linhas 3697-3701)

```python
return ["-c:a", "aac", "-b:a", profile["audio_bitrate"], "-ar", str(profile["audio_rate"]), "-ac", str(profile["audio_channels"])]
```

✅ Usado apenas em joins de vídeo com reencode. O audio_bitrate vem do primeiro clip. ✅

### 4.6. Findings — Juntar

| Finding | Severidade | Descrição |
|---|---|---|
| 4-A | **CRÍTICO** | Filtro `copy` não existe no FFmpeg. Deve ser `null`. Em joins com 3+ clipes + transição, o comando falha. |
| 4-B | ✅ OK | Formato yuv420p aplicado corretamente |
| 4-C | ✅ OK | Validações de compatibilidade extensas |
| 4-D | ✅ OK | Mutual exclusivity Reencode/SmartJoin via checkboxes |
| 4-E | ✅ OK | `-g` e `-bf 0` para mediacodec no xfade |

---

## 5. Ferramenta: Inserir Áudio (`_insert_worker`)

### 5.1. Opções da UI e Mapeamento

| Opção da UI | Variável TK | Código | Comando FFmpeg | Status |
|---|---|---|---|---|
| Áudio principal | `self.insert_main_input` | `select_insert_main_input()` | `-i <main>` | ✅ |
| Áudio inserido | `self.insert_secondary_input` | `select_insert_secondary_input()` | `-i <inserted>` | ✅ |
| Ponto inserção | `self.insert_time_var` (StringVar) | `_apply_insert_time()` → `insert_timeline.insertion` | `-ss`, `atrim` | ✅ |
| Transição | `self.insert_transition_var` (StringVar → "Fade in/out") | `_update_insert_controls()` | `afade` / `acrossfade` | ✅ |
| Tempo transição | `self.insert_seconds_var` (StringVar → "0.5") | float parsing | duração fade/crossfade | ✅ |
| Reencode Completo | `self.insert_reencode_var` (BooleanVar) | `_on_toggle_insert_reencode()` | `_insert_full_reencode_arguments()` | ✅ |
| Smart Insert | `self.insert_smart_var` (BooleanVar) | `_on_toggle_insert_smart()` | `_insert_smart_worker()` | ✅ |

### 5.2. Comando — Full Reencode (`_insert_full_reencode_arguments`, linhas 5014-5071)

```
ffmpeg -hide_banner -y -i <main> -i <inserted>
-filter_complex "[0:a]atrim=...,...[,afade=...],asetpts=PTS-STARTPTS[a0];[1:a]atrim=...,...[,afade=...],asetpts=PTS-STARTPTS[a1];[0:a]atrim=...,...,[a2];[<labels>]concat=..." 
-map [aout] -vn -ar <rate> -ac <ch> <codec_args> -map_metadata -1 <output>
```

**⚠️ FINDING CRÍTICO 5-A:** Linha 5053:
```python
filters.append(f"[0:a]atrim=start=...:end=...,{normalize},asetpts=PTS-STARTPTS{fade_in}[a2]")
```

Comparado com a linha 5042 (trecho inicial `a0`):
```python
filters.append(f"[0:a]atrim=start=0:end=...{normalize}{fade_out},asetpts=PTS-STARTPTS[a0]")
```

Note a diferença: em `[a2]`, o `fade_in` vem **depois** de `asetpts=PTS-STARTPTS`. Mas em `[a0]`, o `fade_out` vem **antes** de `asetpts`. Isso é **incorreto** — o `afade` deve vir **depois** do `asetpts` (que reinicia o timestamp). Se `fade_in` vem depois de `asetpts`, o fade é calculado com relação ao timestamp reiniciado, o que é **correto**. Mas a **ordem** no `a0` (fade antes de asetpts) é **incorreta** — o fade seria calculado com timestamps do arquivo original (com offset), não com o timestamp reiniciado.

Espera, reanalisando... O `a0` é:
```
[0:a]atrim=start=0:end=<insertion>,aresample=<rate>,...,afade=t=out:st=<x>:d=<y>,asetpts=PTS-STARTPTS[a0]
```
Aqui `afade` vem antes de `asetpts`. O `afade` usa `st=<x>` onde `x = insertion - effective` (linha 5041). Como o atrim já removeu o início, o timestamp do clipe começa em 0. Então `st` é calculado corretamente em relação ao início do clipe atrimado. **Funciona, mas a ordem é insegura.**

Já em `[a2]`:
```
[0:a]atrim=start=<insertion>:end=<main_end>,...,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=<y>[a2]
```
Aqui `afade` vem **depois** de `asetpts`. ✅ Correto — fade após reiniciar timestamp.

**⚠️ FINDING 5-B:** A inconsistência entre `[a0]` (afade antes de asetpts) e `[a2]` (afade depois de asetpts) é um **padrão inconsistente**, mas ambos funcionam pois `atrim` garante que os timestamps começam próximo a 0. Porém, o teste da linha 417 verifica:
```python
self.assertIn("asetpts=PTS-STARTPTS,afade=t=in:st=0", fc)
```
Isso confirma que `[a2]` tem `afade` após `asetpts`. Mas `[a0]` tem `afade` antes. **Não é um bug funcional, mas uma inconsistência de padrão.**

### 5.3. Comando — Insert Copy (`_insert_copy_worker`, linhas 4854-4910)

```
ffmpeg -y -ss 0 -i <main> -t <at> -map 0:a:0 -c copy <left>     # parte inicial
ffmpeg -y -ss 0 -i <inserted> -map 0:a:0 -c copy <middle>       # áudio inserido
ffmpeg -y -ss <at> -i <main> -map 0:a:0 -c copy <right>         # parte final
ffmpeg -y -f concat -safe 0 -i list.txt -c copy [-movflags +faststart] <output>
```

✅ Copy only mode está correto. Usa `-ss` antes de `-i` para fast seek.

**⚠️ FINDING 5-C:** Na linha 4898:
```python
[self._ffmpeg(), "-hide_banner", "-y", "-ss", self._fmt_seconds(insertion), "-i", str(main), ...]
```
O `-ss` está **antes** de `-i` (fast seek). ✅

### 5.4. Comando — Smart Insert (`_insert_smart_worker`, linhas 4912-4989)

- Left: `-c copy` ✅
- Middle: reencode com `-ar`, `-ac` + opcional `-af` com fade ✅
- Right: `-c copy` ✅
- Concat: `-c copy` ✅

### 5.5. Comando — WAV no Smart Insert (linhas 4958-4962)

```python
if extension.lower() == ".wav":
    pcm_codec = profile.audio_codec if profile.audio_codec.startswith("pcm_") else "pcm_s16le"
    middle_cmd += ["-c:a", pcm_codec, "-f", "wav"]
else:
    middle_cmd += self._audio_codec_args(extension, profile.audio_bitrate)
```

✅ Preserva codec PCM original ou usa `pcm_s16le`.

### 5.6. Findings — Inserir

| Finding | Severidade | Descrião |
|---|---|---|
| 5-A | ⚠️ Média | Inconsistência: `[a0]` aplica `afade` antes de `asetpts`, `[a2]` aplica depois. Funciona, mas padrão inconsistente. |
| 5-B | ✅ OK | Teste existente (`test_insert_full_reencode_fade_in_after_asetpts`) cobre `[a2]` |
| 5-C | ✅ OK | Copy mode usa `-ss` antes de `-i` |
| 5-D | ✅ OK | WAV preservation no smart insert |

---

## 6. Ferramenta: Limpar Áudio (`_clean_worker`)

### 6.1. Opções da UI

| Opção da UI | Variável TK | Código | Comando FFmpeg | Status |
|---|---|---|---|---|
| Arquivo | `self.clean_input` | `select_clean_input()` | `-i <source>` | ✅ |
| Filtro | `self.clean_mode_var` (StringVar → "equilibrado") | `_clean_worker()` | `afftdn=nf=-25` / `anlmdn=s=0.00003:p=0.002:r=0.002` | ✅ |

### 6.2. Comando Final (linha 5079)

```
ffmpeg -hide_banner -y -i <source> -vn -map 0:a:0 -af <filter> -c:a pcm_s16le -ar 16000 -ac 1 -f wav <output>
```

- `-vn`: remove vídeo ✅
- `-map 0:a:0`: mapeia áudio ✅
- `-c:a pcm_s16le`: PCM 16-bit ✅
- `-ar 16000`: taxa fixa ✅
- `-ac 1`: mono ✅
- `-f wav`: formato WAV ✅

✅ **Correto.** Saída fixa para transcrição. Não há opções personalizáveis (intencional, como documentado no Android audit).

---

## 7. Componentes Compartilhados

### 7.1. VideoAcceleration / Encoder Registry

| Encoder | Key | FFmpeg encoder | Label UI | Status |
|---|---|---|---|---|
| NVENC | `nvenc` | `h264_nvenc` | "NVENC (NVIDIA)" | ✅ |
| QSV | `qsv` | `h264_qsv` | "QSV (Intel)" | ✅ |
| VAAPI | `vaapi` | `h264_vaapi` | "VAAPI (Linux)" | ✅ (skip on Windows) |
| AMF | `amf` | `h264_amf` | "AMF (AMD)" | ✅ |
| CPU | `cpu` | `libx264` ou `mpeg4` | "CPU (fallback)" | ✅ |

**Detecção (linhas 3439-3461):** Usa `ffmpeg -encoders` para verificar disponibilidade, depois testa cada um com `color=c=black:s=256x256:d=0.1`. ✅

**Teste de encoder (linhas 3463-3475):**
```python
command = [ffmpeg, "-hide_banner", "-loglevel", "error"]
if profile.key == "vaapi":
    command += ["-vaapi_device", "/dev/dri/renderD128"]
command += ["-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1", "-frames:v", "1"]
if profile.key == "vaapi":
    command += ["-vf", "format=nv12,hwupload"]
command += ["-c:v", profile.encoder, "-f", "null", "-"]
```
✅ Correto. Testa com 256x256 (mínimo NVENC).

### 7.2. Video Quality (`_video_args`, linhas 3527-3555)

| Qualidade | libx264 CRF | NVENC (-cq) | QSV (-global_quality) | AMF (-qvbr_quality_level) | Hardware multiplier (h264) |
|---|---|---|---|---|---|
| Máxima | 16 | 16 | 17 | 16 | 1.60 |
| Muito alta | 18 | 19 | 20 | 22 | 1.25 |
| Alta | 20 | 22 | 23 | 28 | 1.00 |
| Média | 23 | 25 | 26 | 34 | 0.70 |
| Econômica | 26 | 28 | 29 | 40 | 0.45 |

✅ Alinhado com o audit do Android.

### 7.3. Task Tracker (`FfmpegTaskTracker`)

- Registra comandos FFmpeg via `format_ffmpeg_command_for_log()` ✅
- Estado: PENDING, RUNNING, COMPLETED, FAILED ✅
- Exibe encoder e qualidade na linha de execução ✅

### 7.4. Preview — Velocidade

`_preview_atempo_filter()` (linhas 2562-2577):
```python
target = max(0.5, min(4.0, float(self.preview_speed)))
factors = []
while target > 2.0: factors.append(2.0); target /= 2.0
while target < 0.5: factors.append(0.5); target /= 0.5
factors.append(target)
return ",".join(f"atempo={factor:.6g}" for factor in factors)
```

Valores suportados: 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0 ✅

Para 3x: `atempo=2.0,atempo=1.5` ✅
Para 4x: `atempo=2.0,atempo=2.0` ✅
Para 0.25x: ❌ **NÃO SUPORTADO** — 0.25 < 0.5, mas o atempo mínimo é 0.5. A função `max(0.5, ...)` corta para 0.5. **⚠️ FINDING 7-A:** A velocidade 0.25x é silentemente convertida para 0.5x. O Android usa `atempo` com a mesma limitação. **Documentar ou corrigir.**

### 7.5. Preview — Audio Preview Duration

Linha 2579-2582:
```python
@staticmethod
def _audio_preview_media_duration(end: float, offset: float) -> float:
    return max(0.01, end - offset)
```

✅ `-t` é tempo de mídia (atempo acelera a saída). **Correto** — teste `test_audio_preview_media_duration_does_not_divide_by_speed` confirma.

### 7.6. Preview — Canvas Preview Video Filters

Linha 2585-2593:
```python
return [
    f"setpts=PTS/{speed}",
    f"fps={fps}",
    f"scale={width}:{height}:force_original_aspect_ratio=decrease",
    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
    "setsar=1",
]
```

✅ `setsar=1` evita distorção anamórfica.

### 7.7. Encoder Controls Visibility (`_refresh_encoder_control_state`)

Linha 2226-2242: Habilita/desabilita encoder e qualidade **apenas quando a ferramenta usa encoder de vídeo**. ✅ Correto (F-16 no código).

**⚠️ FINDING 7-B:** A lógica de `_current_tool_uses_video_encoder()` (linhas 2196-2224) para "Juntar":
- Se `join_smart_var` e `transition_seconds > 0.001`: `has_reencode = True`
- Se `join_reencode_var`: `has_reencode = True`
- Se nenhum: `has_reencode = False`
- Se `is_audio_only`: retorna `False`

Mas **não considera que Smart Join sem transition (segundos=0) faz copy** — e retorna `False` corretamente via `has_reencode = False`. ✅

### 7.8. Findings — Componentes Compartilhados

| Finding | Severidade | Descrição |
|---|---|---|
| 7-A | ⚠️ Baixa | 0.25x preview speed silenciosamente virou 0.5x (limitação atempo) |
| 7-B | ✅ OK | Encoder controls visibilidade correta |
| 7-C | ✅ OK | Task tracker registra todos os comandos |
| 7-D | ✅ OK | Preview filters corretos |

---

## 8. Resumo de Findings

| # | Finding | Ferramenta | Severidade | Linha | Fix Sugerido |
|---|---|---|---|---|---|
| 3-B | Preview MCI não aplica `-noautorotate` — inconsistência com preview via FFmpeg | Girar | ⚠️ Média | 3936-3949 | Adicionar `-noautorotate` ao MCI ou usar canvas preview sempre quando há rotação de metadados |
| 4-A | Filtro `copy` não existe no FFmpeg — comandos de join com 3+ clipes + transição falham | Juntar | **CRÍTICO** | 4806-4807 | Substituir `copy` por `null` e `acopy` por `anull` |
| 5-A | Inconsistência: `[a0]` aplica `afade` antes de `asetpts`; `[a2]` aplica depois | Inserir | ⚠️ Média | 5041-5053 | Unificar ordem: `asetpts` antes de `afade` |
| 7-A | 0.25x preview silenciosamente vira 0.5x (limitação atempo) | Preview | ⚠️ Baixa | 2568 | Documentar na UI ou usar `atempo=0.5,atempo=0.5` |
| 7-E | **⚠️ FINDING CRÍTICO 7-E:** Missing test coverage for `_insert_full_reencode_arguments` crossfade order | Inserir | ⚠️ Baixa | 432-433 | O teste cobre `[a2]`, mas não `[a0]` |

### Finding 7-E detalhado:

O teste `test_insert_full_reencode_fade_in_after_asetpts` (linha 417-433) verifica apenas que `[a2]` tem `asetpts=PTS-STARTPTS,afade=t=in:st=0`. Mas **não testa `[a0]`** que tem a ordem oposta (`afade` antes de `asetpts`). Este é um gap de cobertura.

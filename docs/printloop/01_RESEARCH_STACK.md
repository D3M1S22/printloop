# 01. Ricerca: fonti ufficiali e stack per PrintLoop

> Ricerca del **16 ottobre 2026** su documentazione Bambu Lab (tramite guide che la citano), OpenBambuAPI, wiki OrcaSlicer, recipe vLLM, documentazione Gemma, repository Cambridge.
> Per AMD Developer Cloud, Token Factory ed evento valgono le verifiche già fatte per MarginSwarm (`docs/marginswarm/01_RESEARCH_STACK.md` sul branch `MarginSwarm`), riassunte qui al §1.
> Legenda: ✅ verificato su fonte ufficiale · ⚠️ fonte terza, reverse engineering o dato da riconfermare · ❓ da verificare con uno spike.

---

## 0. TL;DR operativo

| Componente | Cosa usiamo | Stato |
| :-- | :-- | :-- |
| Modello di diagnosi | **Gemma 4 26B-A4B-it** (31B in alternativa) su **vLLM-ROCm**, droplet **MI300X** | ✅ stack, ❓ crediti |
| Input al modello | 1–4 **immagini** per richiesta, output JSON con schema | ✅ |
| Slicer | **OrcaSlicer CLI**: `--load-settings`, `--slice`, `--export-3mf`, `--export-settings` | ✅ sintassi, ❓ headless su Linux |
| Stampante (stretch) | **P1S in LAN-only + Developer Mode**: MQTT su 8883, camera su 6000, FTPS su 990 | ✅ modalità, ⚠️ protocollo |
| Fallback LLM | AMD Token Factory (modello vision citato da fonti terze, niente Gemma) | ⚠️ |
| Benchmark AMD extra (stretch) | Fine-tuning di un classificatore leggero su **CAXTON** (CC BY 4.0) con PyTorch ROCm | ✅ licenza, ❓ dimensione immagini |

**Da sbloccare subito:** crediti del droplet MI300X (come per MarginSwarm), firmware della P1S (≥ 01.08.02.00 per il Developer Mode), OrcaSlicer CLI funzionante sulla macchina di sviluppo.

---

## 1. AMD ed evento (riassunto dalla ricerca MarginSwarm)

- Una parte significativa e reale del carico deve girare su AMD e comparire nel prodotto mostrato ai giudici. ✅
- **AMD Developer Cloud:** MI300X ×1, 192 GB, ~1,99 $/h; immagine "vLLM Quick Start"; serve un metodo di pagamento anche con i crediti; un droplet spento costa ancora, va **distrutto**. ⚠️ prezzi
- **Sicurezza:** i port mapping Docker scavalcano UFW → vLLM sempre con `--api-key`. ✅
- **Token Factory** (`notebooks.amd.com/tokenfactory`): API OpenAI-compatibile su GPU AMD, gratuita per l'evento. Tra i modelli citati da fonti terze c'è **DeepSeek-V4-Flash-Vision-Exp**, utile come fallback di diagnosi. Niente Gemma, quindi niente premio Google con il fallback. ⚠️
- **Google:** Gemma su GPU AMD rende il progetto eleggibile al premio Google (5.000 $). ✅
- **Evolus:** non è nel percorso critico di PrintLoop. Resta possibile (BYOM + Knowledge Library con la KB dei difetti + Workflow), ma non è pianificato.
- **Pagina evento:** montepremi aggiornato a **17.000 $+**, con i partner IMMENT e BAC Network. **Scadenza: domenica 18/10 ore 12:00.**

---

## 2. Bambu Lab P1S

### 2.1 LAN-only e Developer Mode ✅ / ⚠️
- Dal firmware di gennaio 2025 ("Authorization Control"), le azioni di scrittura di software terzi sono bloccate in modalità Cloud. Il percorso previsto da Bambu è il **Developer Mode**, che lascia aperti **MQTT, live stream e FTP**. Bambu dichiara di **non supportare** i protocolli in questa modalità. ✅ (annuncio Bambu sul forum)
- Sulla serie P1 il Developer Mode c'è dal firmware **01.08.02.00**. ⚠️ (guida SimplyPrint, che rimanda al wiki Bambu)
- Attivazione dalla stampante: *Impostazioni → WLAN* → **LAN-only Mode** on → riavvio → **Developer Mode** on. L'access code è nello stesso menu. ⚠️
- Effetti collaterali: **Bambu Handy smette di funzionare**, niente aggiornamenti firmware via app, **serve una microSD** nella stampante per i trasferimenti di file. ⚠️
- Regola del progetto: **solo** Developer Mode, nessun bypass di certificati o autenticazione.

### 2.2 MQTT ⚠️ (OpenBambuAPI, protocollo ricostruito dalla community)
- Locale: `mqtts://{PRINTER_IP}:8883`, TLS, utente `bblp`, password = access code LAN.
- Topic: `device/{SERIAL}/report` (stampante → client), `device/{SERIAL}/request` (client → stampante).
- Comandi utili:

| Comando | `param` | Uso in PrintLoop |
| :-- | :-- | :-- |
| `print.pause` / `print.resume` / `print.stop` | vuoto | Modo 1: pausa con conferma dell'operatore |
| `print.print_speed` | `"1"` silent, `"2"` standard, `"3"` sport, `"4"` ludicrous | Unico override di velocità: 4 livelli, non percentuali |
| `print.gcode_line` | G-code raw, righe separate da `\n` | Da evitare in demo: nessuna garanzia di sicurezza |
| `print.project_file` | `Metadata/plate_N.gcode` + `url` del 3MF sulla SD | Avvio della ristampa (stretch) |
| `pushing.pushall` | — | Stato completo |

- `push_status` contiene, tra gli altri: `layer_num`, `total_layer_num`, `mc_percent`, `mc_remaining_time`, `gcode_state`, `nozzle_temper` e `nozzle_target_temper`, `bed_temper`, `cooling_fan_speed`, `print_error`, `hms`.
- **Caveat P1:** la P1 invia solo i campi cambiati dall'ultimo report. Per lo stato completo serve `pushall`, da non chiamare più spesso di ogni 5 minuti (sulla P1P causa lag).

### 2.3 Camera ⚠️
- P1 e A1 non usano RTSP (che è di X1 e P2S): usano uno **stream TCP proprietario su TLS, porta 6000**. Un pacchetto di autenticazione binario di 64 byte contiene utente `bblp` e access code. I frame sono **JPEG 1280×720**, ciascuno preceduto da un header di 16 byte. (OpenBambuAPI)
- Frame rate: ~**0,5 fps** secondo la scheda prodotto della chamber camera P1. ⚠️ da misurare
- **Conseguenza:** la camera di bordo basta per i difetti grossolani (spaghetti, distacco, layer shift), non per stringing, sotto-estrusione o qualità superficiale. Questi passano dal Modo 2 con le foto del telefono.

### 2.4 File ⚠️
- FTPS implicito sulla **porta 990** (stesse credenziali), usato per caricare il 3MF sulla SD prima di `print.project_file`.

---

## 3. Gemma 4 su vLLM-ROCm

### 3.1 Modalità ✅ (Google AI docs, ora deprecate a favore di gemma.ai)
| Variante | Testo | Immagini | Video | Audio |
| :-- | :-: | :-: | :-: | :-: |
| E2B, E4B | ✅ | ✅ | ✅ | ✅ |
| 12B | ✅ | ✅ | ✅ | ✅ |
| **26B-A4B (MoE, ~4B attivi)** | ✅ | ✅ | ✅ | — |
| **31B (dense)** | ✅ | ✅ | ✅ | — |

Per la diagnosi bastano le immagini. L'audio non serve.

### 3.2 Serving ✅ (recipe vLLM Gemma 4)
- MI300X/MI325X/MI350X/MI355X supportano tutte le varianti su una sola GPU. Immagine `vllm/vllm-openai-rocm:latest` (accesso a `/dev/kfd` e `/dev/dri`); ROCm 7.2.1, Python 3.12.
- Flag rilevanti per PrintLoop:
  - `--limit-mm-per-prompt '{"image": 4, "audio": 0}'`: fino a 4 foto per richiesta;
  - `--mm-processor-kwargs`: budget di token visivi per immagine, valori **70, 140, 280 (default), 560, 1120**. Per difetti fini (stringing, layer) si prova 560 o 1120. È un parametro da benchmarkare;
  - `--max-model-len` adeguato al carico (16k bastano);
  - `--gpu-memory-utilization 0.90`: senza Monte Carlo da ospitare, a differenza di MarginSwarm, si può dare quasi tutta la VRAM a vLLM;
  - `--async-scheduling` per il throughput.
- **Structured output:** `response_format` con `json_schema`. Lo schema forza la forma, non il contenuto: le istruzioni vanno anche nel system prompt, perché il modello non vede le descrizioni dello schema. ✅
- **Video:** supportato tramite estrazione di frame nella pipeline vLLM, ma la recipe **non documenta** un limite di frame per richiesta né la gestione dei timestamp. Il "fino a 32 frame" del concept non è confermato: niente video nell'MVP. ⚠️
- Tool calling (`--tool-call-parser gemma4`) non serve all'MVP: la patch si ottiene con JSON schema.

---

## 4. OrcaSlicer CLI

### 4.1 Sintassi ✅ (wiki OrcaSlicer)
- `orca-slicer [input...] [opzioni...]`: ogni argomento senza `-` è un file da caricare.
- I nomi delle chiavi diventano flag con i trattini: `layer_height` → `--layer-height`. Si può fare l'override di quasi tutte le chiavi di process, filament e printer con `--chiave=valore`.
- 43 chiavi sono **rifiutate** come override, tra cui `inherits`, `inherits_group`, `preset_name`, `compatible_printers`, `printer_model`.
- `--load-settings "process.json;printer.json"` e `--load-filaments filament.json` caricano i JSON esportati dal GUI (*Save/Export* di ogni scheda).
- **L'ordine conta:** printer prima, poi process. ⚠️ (fonte terza)
- Le flag sono cambiate tra versioni (`--load-filaments` contro `--load-filament`). Fissiamo una versione e verifichiamo con `orca-slicer --help`. ⚠️

### 4.2 Azioni ✅
- `--slice 0` per tutte le piastre, `--slice i` per la piastra *i*.
- `--export-3mf out.3mf`: progetto 3MF con il G-code della piastra dentro (`Metadata/plate_N.gcode`, da estrarre con unzip). ⚠️ percorso interno da verificare
- `--export-settings settings.json`: esporta le **impostazioni effettive** (process + printer + filament) in un JSON. **Risolve l'appiattimento dei preset con `inherits`.**
- `--min-save`: 3MF ridotto.
- Esempio ufficiale:
  ```bash
  orca-slicer model.3mf --load-settings "process.json;printer.json" --load-filaments filament.json \
    --arrange 1 --slice 0 --export-3mf output.3mf
  ```
- Non documentati: export di `.gcode` puro, `--outputdir`, codici di uscita, necessità di un display (`xvfb`). ❓

### 4.3 Commenti nel G-code ✅ (verificato il 17/10 su BambuStudio 2.8.2)
`; FEATURE: <tipo>` (Bridge, Outer wall, Inner wall, Overhang wall, …), `; CHANGE_LAYER`, `; LAYER_HEIGHT:`, `; LINE_WIDTH:`, un `CONFIG_BLOCK` con tutte le impostazioni effettive e un'intestazione con tempo, lunghezza e peso del filamento. Con `--outputdir` la CLI scrive anche `plate_<n>.gcode` e `result.json` (tempi per feature, grammi). Headless senza display: funziona (fallisce solo la miniatura, per OSMesa assente). Dettagli in [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md) §2.

---

## 5. Prior art (da citare nel pitch)

| Lavoro | Cosa fa | Differenza con PrintLoop |
| :-- | :-- | :-- |
| **AI failure detection della P1S** (firmware Bambu) | Rileva spaghetti e, nelle versioni recenti, warping e layer shift iniziali. ⚠️ (fonte terza) | Allarme, nessuna causa né correzione. Il nostro Modo 1 non deve competere qui |
| **Obico** (e integrazione HA per P1) | Rilevamento spaghetti con modello ML self-hosted | Come sopra |
| **CAXTON**, Brion & Pattinson, *Nature Communications* 2022 ✅ | Rete multi-head che classifica flow, velocità laterale, Z offset e temperatura dell'hotend (basso/ok/alto) da un'immagine vicino all'ugello, e corregge in loop chiuso in tempo reale. Accuratezza media 84,3% | Camera dedicata accanto all'ugello, correzione sul firmware durante la stampa, nessuna modifica del preset né verifica sul G-code. Noi lavoriamo su foto del pezzo finito, con macchine di serie, e produciamo un preset corretto e verificato |

---

## 6. Dataset pubblici

| Dataset | Contenuto | Licenza | Uso |
| :-- | :-- | :-- | :-- |
| **CAXTON** (Cambridge, handle 1810/339869) | **1.272.273 immagini** di estrusione da 192 pezzi su 8 stampanti Marlin, etichettate con flow, velocità laterale, Z offset, temperature hotend e piano, coordinate. CSV filtrato da 948.396 immagini | **CC BY 4.0** ✅ | Benchmark ROCm (fine-tuning di un classificatore piccolo), test di Gemma sul riconoscimento di sotto- e sovra-estrusione. Dominio diverso dal nostro: camera all'ugello, non foto del pezzo. Dimensione degli archivi immagini ❓ |
| **Roboflow 3D_FDM_faults_detection** | Bounding box di difetti FDM | CC BY 4.0 (dal concept) ❓ | Test aggiuntivo per la tassonomia. Classi non verificate (pagina 403) |
| **AGH 3D printer anomalies** (arXiv 2004.08817) | Anomalie di stampa | CC BY 4.0 (dal concept) ❓ | Opzionale |

Nessuno di questi contiene foto del pezzo finito + preset + G-code: **il test set principale lo produciamo noi** ([02_DATA_STRATEGY.md](02_DATA_STRATEGY.md)).

---

## 7. Fonti

- [Bambu Lab — Updates and Third-Party Integration with Bambu Connect](https://forum.bambulab.com/t/updates-and-third-party-integration-with-bambu-connect/137408)
- [SimplyPrint — Bambu Lab LAN-only mode and Developer Mode](https://help.simplyprint.io/en/article/bambu-lab-lan-only-mode-and-developer-mode-how-to-enable-xa0hch/) (rimanda a `wiki.bambulab.com/en/knowledge-sharing/enable-developer-mode`)
- [OpenBambuAPI — MQTT](https://github.com/Doridian/OpenBambuAPI/blob/main/mqtt.md) · [video](https://github.com/Doridian/OpenBambuAPI/blob/main/video.md)
- [Bambu Lab P1 chamber camera, scheda prodotto](https://www.3djake.com/bambu-lab/chamber-camera)
- [OrcaSlicer wiki — CLI mode](https://www.orcaslicer.com/wiki/cli/cli_mode) · [CLI actions](https://www.orcaslicer.com/wiki/cli/cli_actions) · [CLI misc](https://www.orcaslicer.com/wiki/cli/cli_misc)
- [Printago — OrcaSlicer CLI reference](https://printago.io/blog/orca-slicer-cli-reference) (fonte terza)
- [vLLM recipes — Gemma 4](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html)
- [Google AI — Gemma core docs](https://ai.google.dev/gemma/docs/core)
- [CAXTON — codice](https://github.com/cam-cambridge/caxton) · [dataset](https://www.repository.cam.ac.uk/handle/1810/339869) · [paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9378646/)
- [Bambu firmware features](https://bambuhub.net/articles/firmware-updates) (fonte terza) · [HA spaghetti detection per P1 (Obico)](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection)
- [Roboflow 3D_FDM_faults_detection](https://universe.roboflow.com/wangdada/3d_fdm_faults_detection-krkkr) · [AGH 3D printer anomalies](https://arxiv.org/pdf/2004.08817)

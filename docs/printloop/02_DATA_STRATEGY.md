# 02. Dati: cosa abbiamo, cosa produciamo, come valutiamo

## 1. Inventario

| Risorsa | Stato | Note |
| :-- | :-- | :-- |
| Bambu Lab P1S | ✅ del team | Firmware da controllare (Developer Mode da 01.08.02.00). **Dove sarà sabato e domenica?** Vedi [04](04_PLAN_DECISIONS_RISKS.md) §5 |
| OrcaSlicer | ✅ in uso | Versione da fissare e annotare in ogni caso |
| Casi storici risolti con Antigravity (bridge che cedono, sovra-estrusione) | ❓ da recuperare | Servono preset prima/dopo, foto se esistono, descrizione del problema. Primo test qualitativo: Gemma deve arrivare alla stessa patch |
| Filamento | ❓ | Un solo materiale (es. PLA) per tutto il test set: riduce le variabili |
| GPU locale Radeon RX 6700 XT (12 GB) | ✅ | ROCm su RDNA2 non è ufficialmente supportato (di solito serve `HSA_OVERRIDE_GFX_VERSION`) ⚠️. Al massimo per sviluppo con un modello piccolo, non per la demo |
| Dataset pubblici | ✅ CAXTON (CC BY 4.0), ❓ Roboflow, AGH | Vedi [01](01_RESEARCH_STACK.md) §6. Nessuno ha foto del pezzo + preset + G-code |

**Conclusione:** il test set che conta lo produciamo noi, con difetti **indotti da un singolo parametro noto**. È l'unico modo per avere una ground truth della *causa*, non solo del sintomo.

---

## 2. Tassonomia chiusa dei difetti

| Classe | Codice | Rilevabile da camera P1S (Modo 1)? |
| :-- | :-- | :-: |
| Sotto-estrusione | `under_extrusion` | no |
| Sovra-estrusione | `over_extrusion` | no |
| Stringing | `stringing` | no |
| Bridge che cedono | `bridge_sagging` | forse, se grave |
| Overhang arricciati | `overhang_curling` | forse |
| Warping / distacco | `warping` | sì |
| Problemi di primo layer | `first_layer` | no |
| Layer shift | `layer_shift` | sì |
| Spaghetti / stampa persa | `spaghetti` | sì |
| Nessun difetto | `none` | — |
| Fuori tassonomia | `other` | — |

`other` e `none` sono obbligatori: senza, il modello forza ogni foto in una classe.

---

## 3. Matrice dei difetti indotti (test set)

> **Implementata** in `src/printloop/testset.py` sul coupon `examples/coupon/` (piastra + due pilastri + ponte da 44 mm, ~12 min): `uv run printloop testset` genera per ogni caso il progetto, il 3MF già slicato da stampare e il manifest. I casi effettivi (C0–C7, valori verificati sul G-code) sono in [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md) §3; la tabella qui sotto è il piano originale.

Pezzi di test brevi (5–15 min ciascuno), tutti con lo stesso filamento e lo stesso preset di sistema come **baseline**. Ogni caso cambia **un solo** parametro rispetto alla baseline. I nomi delle chiavi sono quelli di OrcaSlicer per macchine Bambu e **vanno confermati** sul JSON di `--export-settings` (spike S2). I valori esatti finiscono nel manifest di ogni caso.

| Caso | Pezzo | Difetto atteso | Parametro indotto (chiave Orca ⚠️) | Variazione | Patch attesa |
| :-- | :-- | :-- | :-- | :-- | :-- |
| C0 | tutti | `none` (controllo negativo) | — | baseline | **nessuna patch** |
| C1 | bridge test (ponti 10–50 mm) | `bridge_sagging` | `bridge_speed` | ×2,5 | `bridge_speed` ↓ |
| C2 | bridge test | `bridge_sagging` | `overhang_fan_speed` | 100% → 30% | ventola ↑ |
| C3 | cubo 20 mm | `over_extrusion` | `filament_flow_ratio` | +15% | flow ↓ |
| C4 | cubo 20 mm | `under_extrusion` | `filament_flow_ratio` | −20% | flow ↑ |
| C5 | due torri | `stringing` | `nozzle_temperature` | +25 °C | temperatura ↓ (o retrazione ↑) |
| C6 | due torri | `stringing` | `retraction_length` | 0,8 → 0,2 mm | retrazione ↑ |
| C7 | overhang test 30–70° | `overhang_curling` | `fan_max_speed` / `overhang_fan_speed` | → 20% | ventola ↑ |
| C8 (opz.) | lastra 80×80 mm | `warping` | piano freddo + brim off | −20 °C | piano ↑, brim on |

- Stampe baseline + 8 casi indotti: **~2 h di macchina**. Ristampe con patch per chiudere il loop: altre **~1,5 h**.
- C1/C2 e C5/C6 sono coppie con **stesso sintomo e cause diverse**: misurano se il modello distingue la causa o tira a indovinare. Se non ci riesce, la risposta onesta è una patch al parametro più probabile e, alla ristampa, il passaggio al secondo candidato. È il motivo per cui il loop esiste.

### 3.1 Protocollo foto
- 4 foto per pezzo: frontale, laterale a 45°, dall'alto, macro del difetto.
- Stesso telefono, sfondo neutro, luce diffusa, un riferimento di scala (righello) nell'inquadratura.
- Foto prese **prima** di guardare il manifest da chi le etichetta (etichettatura cieca, §4).

### 3.2 Struttura di un caso (non versionata, sotto `data/`)

```text
data/testset/C3_over_extrusion/
├── manifest.json            # generato da `printloop testset`
├── project.3mf              # progetto con il parametro indotto
├── slice/sliced.3mf         # da stampare
└── photos/                  # da aggiungere dopo la stampa: front.jpg, side45.jpg, top.jpg, macro.jpg
```

```json
{
  "case_id": "C3_over_extrusion_01",
  "object": "cube_20mm",
  "induced_defect": "over_extrusion",
  "induced_params": {"filament_flow_ratio": [0.98, 1.13]},
  "expected_patch_keys": ["filament_flow_ratio"],
  "expected_direction": {"filament_flow_ratio": "down"},
  "human_severity": {"labeler_a": 2, "labeler_b": 2},
  "print_time_min": 14,
  "filament_g": 6.1,
  "firmware": "01.0x.xx.xx",
  "orca_version": "x.y.z"
}
```

I valori qui sopra sono un esempio di formato, non dati misurati.

---

## 4. Rubrica di severità (stessa prima e dopo)

| Severità | Significato |
| :-: | :-- |
| 0 | assente |
| 1 | lieve, solo estetico: pezzo accettabile |
| 2 | evidente, il pezzo funziona ma va rifatto per un cliente |
| 3 | grave, pezzo da scartare |

- Due membri del team etichettano **indipendentemente**, senza vedere il manifest; si riporta l'accordo.
- **Successo** di un loop = severità ≤ 1 sul difetto indotto, senza nuovi difetti ≥ 2.
- Il modello produce la stessa rubrica: confrontiamo la sua severità con quella umana.

---

## 5. Metriche

| Metrica | Definizione | Fonte |
| :-- | :-- | :-- |
| Accuratezza di diagnosi | top-1 e top-2 sulla classe del difetto indotto | casi C0–C8 |
| Correttezza della causa | la patch tocca la chiave indotta, nella direzione giusta | manifest |
| Controllo negativo | C0 → nessuna patch | C0 |
| Pre-flight | la modifica si vede nel G-code nelle feature attese, nessun limite superato | parser |
| Iterazioni al successo | cicli fino a severità ≤ 1 (massimo K = 3) | ristampe |
| Spreco | grammi e minuti per iterazione; in Modo 1, grammi risparmiati fermando prima | manifest + slicer |
| Confronto modelli | 26B-A4B contro 31B (e fallback Token Factory): accuratezza, latenza p50/p95, token visivi 280 contro 560/1120 | benchmark |
| Casi storici | patch di Gemma contro patch trovata con Antigravity (qualitativo) | §1 |

Con ~10 casi i numeri sono piccoli: li presentiamo come conteggi (es. "7/9"), non come percentuali con decimali.

---

## 6. CAXTON (stretch, benchmark ROCm)

- Uso: fine-tuning di un classificatore leggero (es. ResNet-18 a 4 teste: flow, velocità, Z offset, temperatura × basso/ok/alto) su un sottoinsieme, con PyTorch ROCm su MI300X. Misuriamo il tempo per epoca contro CPU. È un carico GPU reale e diverso dall'inferenza.
- Limite da dichiarare: le immagini CAXTON sono riprese accanto all'ugello su stampanti Marlin, non sono foto di pezzi finiti. Il classificatore non sostituisce Gemma nel Modo 2: serve come benchmark e, al massimo, come secondo parere sul flow.
- Prima di pianificarlo: verificare quanto pesano gli archivi immagini (il repository elenca solo CSV per ~640 MB). ❓

## 7. Licenze

- Le nostre foto, i preset e i G-code si possono pubblicare (sono nostri). Per la consegna basta un sottoinsieme piccolo, il resto resta in `data/` (gitignored).
- CAXTON: CC BY 4.0, citare Brion & Pattinson, *Nature Communications* 2022. Non ridistribuiamo le immagini: script di download.

# 04. Decisione, spike, piano e rischi

> Situazione al **16/10/2026 sera**: code freeze sabato 17/10 23:59, submission **domenica 18/10 ore 12:00**, team di 2 (backend/ML e frontend React/Vite), sabato e domenica on-site a Roma.
>
> **Aggiornamento 17/10:** il team ha scelto di procedere con il Modo 2 di PrintLoop (Modo 1 "se c'è tempo"). S2 superato con BambuStudio; pipeline implementata. Stato e prossimi passi: [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md).

---

## 1. PrintLoop o MarginSwarm

| Criterio | MarginSwarm (branch `MarginSwarm`) | PrintLoop (questo branch) |
| :-- | :-- | :-- |
| Stato | Backend funzionante offline, 11 test, backtest e valutazioni versionati, contratto API e fixture per il frontend | Solo documentazione |
| Dipendenze fisiche | Nessuna | Stampante, filamento, **~3,5 h di macchina** per il test set, foto |
| Dipendenze esterne | Droplet MI300X (Gemma + Monte Carlo) | Droplet MI300X (Gemma vision). OrcaSlicer CLI headless |
| Evidenza AMD | Inferenza LLM + Monte Carlo PyTorch su GPU | Inferenza multimodale (+ fine-tuning CAXTON se avanza tempo) |
| Premio Google | Gemma | Gemma |
| Impatto in demo | Dashboard e numeri | Oggetti fisici prima e dopo, molto tangibile |
| Concorrenza nella track | Track 3 | Track 1, dove molti progetti sono chatbot RAG sui manuali |
| Rischio sulla consegna | Basso / medio | **Alto**: tutto da costruire in ~1 giorno e mezzo |

**Valutazione:** con i dati di oggi MarginSwarm è la scelta a rischio più basso. PrintLoop vale il cambio solo se gli spike S1–S3 riescono **entro sabato alle 10:00** e la stampante è disponibile per almeno 4 ore entro sabato sera. La decisione resta del team. Se non si cambia, questo branch resta come documentazione di un concept verificato.

---

## 2. Spike (con timebox e criterio go/no-go)

| ID | Spike | Timebox | Go se… | Se fallisce |
| :-- | :-- | :-- | :-- | :-- |
| S1 | **Gemma 4 vision su AMD**: 26B-A4B su vLLM-ROCm con `--limit-mm-per-prompt`, JSON schema, 5 foto di difetti (casi storici o C1/C3/C5) | 1,5 h (dopo i crediti) | classe giusta su ≥ 3/5 e JSON sempre valido | provare 31B o token visivi 560/1120. Fallback Token Factory vision (perde il premio Google) |
| S2 | **OrcaSlicer CLI headless**: `--export-settings` su un preset con `inherits`, `--slice 0 --export-3mf`, estrazione del G-code, lettura dei commenti di feature, override di una chiave visibile nel G-code | 1 h | tutto da CLI senza GUI, chiavi della KB confermate | `xvfb-run`; altrimenti export manuale dal GUI (il pre-flight resta, la demo è meno fluida) |
| S3 | **P1S**: firmware, LAN-only + Developer Mode, lettura `push_status` via MQTT, un frame dalla porta 6000, misura degli fps | 1 h | stato e frame letti | Modo 1 tagliato: **non blocca l'MVP** |
| S4 | **Stampe**: avviare subito C0, C1, C3, C5 (la stampante lavora mentre si scrive codice) | parallelo | 4 pezzi con difetto visibile | rivedere le variazioni indotte (più marcate) |
| S5 | **Casi storici**: recuperare preset prima/dopo e foto dei casi risolti con Antigravity | 30 min | ≥ 2 casi completi | si usa solo il test set indotto |

---

## 3. Piano (se si va con PrintLoop)

| Quando | Backend / ML | Frontend | Stampante |
| :-- | :-- | :-- | :-- |
| Ven sera | S2, S5; S1 appena c'è il droplet | — | S4: C0, C1, C3, C5 |
| Sab 10:00 | **Go/no-go** sugli spike | | |
| Sab mattina | parser G-code + pre-flight + test; KB + validatore | UI caso: upload, diagnosi, diff del preset, approvazione (su fixture) | C2, C4, C6, C7 + foto |
| Sab pomeriggio | diagnosi Gemma + proposta + API; primi casi end-to-end | integrazione con l'API reale | ristampe con patch (chiusura del loop) |
| Sab sera | `eval.py` sul test set, benchmark AMD (26B vs 31B, token visivi, concorrenza), primo take del video | rifinitura UI, schermata risultati | — |
| **Sab 23:59** | **code freeze** | | |
| Dom 10:00–12:00 | README in inglese, sezione AMD Evidence, deck, submission | cover, video finale | — |

### Linee di taglio
- **P0 (senza questo non si consegna):** Modo 2 completo fino all'export del preset; pre-flight funzionante; ≥ 6 casi valutati, controllo negativo incluso; benchmark misurato su MI300X; UI di approvazione.
- **P1:** loop chiuso con ristampa su ≥ 2 casi; confronto 26B contro 31B; casi storici.
- **P2:** Modo 1 live con pausa; ristampa via MQTT; fine-tuning CAXTON su ROCm.

---

## 4. Registro delle decisioni (proposte)

| ID | Decisione | Alternative | Motivo | Stato |
| :-- | :-- | :-- | :-- | :-- |
| P-01 | **Modo 2 (post-stampa) come prodotto**, Modo 1 stretch | Modo 1 come trigger centrale | camera P1S a ~0,5 fps; spaghetti detection già nel firmware | ✅ 17/10 |
| P-02 | **Immagini, non video**, come input a Gemma | video con frame | limite di frame non documentato; foto più nitide | proposta |
| P-03 | **Gemma 4 26B-A4B** default, 31B se la qualità non basta | Qwen-VL, Token Factory | premio Google; MI300X lo regge con margine | proposta |
| P-04 | Solo parametri con **firma nel G-code** nella KB | KB libera | verificabilità | proposta |
| P-05 | Patch con **≤ 2 chiavi**, niente oscillazioni, K = 3 | patch libere | causalità leggibile, convergenza | proposta |
| P-06 | **Input = progetto 3MF**; patch su `Metadata/project_settings.config` di una copia | `--export-settings` + preset JSON separati | il progetto contiene già le impostazioni effettive; le impostazioni esportate da un progetto non si ricaricano come preset (`from project unsupported`) | ✅ S2 |
| P-10 | Slicer **BambuStudio o OrcaSlicer** (stessa CLI) | solo OrcaSlicer | OrcaSlicer non installato sulla macchina di sviluppo, BambuStudio sì | ✅ |
| P-11 | Proposta a regole come default offline; Gemma sceglie tra gli **stessi** candidati filtrati e passa dallo stesso validatore | Gemma libero | verificabilità, funziona senza endpoint | ✅ |
| P-07 | **Solo Developer Mode** per la stampante, mai bypass | — | regole Bambu ed etica | ✅ |
| P-08 | API FastAPI su **8788**, UI Vite su 5174 | 8787 | 8787 è usata da MarginSwarm, che gira in parallelo sulla stessa macchina | ✅ 17/10 |
| P-09 | CAXTON citato come **prior art**, non nascosto | — | onestà verso i giudici | ✅ |

---

## 5. Rischi

| # | Rischio | Prob. | Impatto | Mitigazione |
| :-- | :-- | :-- | :-- | :-- |
| R1 | **Tempo**: un progetto nuovo in ~1,5 giorni | A | **Alto** | spike con timebox, go/no-go alle 10:00, linee di taglio |
| R2 | Stampante non accessibile da Roma sabato/domenica | ? | **Alto** | stampare il test set **stanotte e sabato mattina**; in demo foto e pezzi fisici portati in sede, niente stampa live |
| R3 | Gemma non distingue cause diverse con lo stesso sintomo (C1/C2, C5/C6) | M | Medio | il loop prova il secondo candidato alla ristampa; dichiararlo nei limiti |
| R4 | Gemma 4 vision troppo debole su foto di difetti fini | M | Alto | token visivi 560/1120, foto macro, 31B; altrimenti tassonomia ridotta |
| R5 | OrcaSlicer CLI fragile su Linux (display, flag cambiate tra versioni) | M | Medio | versione fissata, `xvfb-run`, fallback GUI |
| R6 | Crediti/droplet MI300X (stesso rischio di MarginSwarm) | M | **Alto** | attivarli subito; fallback Token Factory vision |
| R7 | Difetti indotti poco visibili | M | Medio | variazioni più marcate, pezzi progettati per mostrare il difetto |
| R8 | Endpoint vLLM pubblico | M | Alto | `--api-key` sempre |
| R9 | Access code della stampante committato | B | Alto | `.env` in `.gitignore`, `.env.example` senza valori |
| R10 | Il team si divide tra due progetti | M | Alto | una decisione netta alle 10:00 di sabato, niente lavoro in parallelo su entrambi |

---

## 6. Domande aperte

1. **Dove sarà la stampante** sabato e domenica? Chi lancia le stampe mentre il team è a Roma?
2. Firmware attuale della P1S (Developer Mode da 01.08.02.00)?
3. Materiale del test set (PLA?) e quantità disponibile.
4. Esistono ancora preset e foto dei casi risolti con Antigravity?
5. Versione di OrcaSlicer installata e sistema operativo su cui gira la CLI.
6. I crediti del droplet bastano per entrambi i progetti, se si fanno gli spike di PrintLoop mentre MarginSwarm resta il piano A?

# 00. PrintLoop: direzione del progetto

> **Track:** 1, Intelligent Industry · **Premi mirati:** AMD Main · Google (Gemma su AMD) · Vibe Generation
> **Stato (17/10/2026):** Modo 2 implementato e testato end-to-end con lo slicer reale; diagnosi Gemma da provare sull'endpoint AMD. Modo 1 "se c'è tempo". Dettagli in [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md).
> **Concept originale:** [`../ideas/01_printloop.md`](../ideas/01_printloop.md). Questo documento lo aggiorna con quanto emerso dalle fonti ufficiali.

---

## 1. Pitch in una frase

**PrintLoop guarda un pezzo stampato male, ne individua la causa e propone una modifica minima al preset di OrcaSlicer. Prima della ristampa verifica nel G-code che la modifica abbia l'effetto voluto, e la applica solo con l'approvazione dell'operatore.**

## 2. Problema

Quando una stampa FDM esce male, l'operatore guarda il pezzo, intuisce la causa, cambia qualche parametro nello slicer e riprova. Il ciclo funziona solo se l'operatore ha esperienza, e ogni tentativo sbagliato costa materiale e ore di macchina. Le correzioni restano nella testa di chi le ha fatte, non nei preset.

Gli strumenti esistenti coprono solo una parte del ciclo:
- il **rilevamento dei guasti** grossolani (spaghetti, distacco) è già nel firmware della P1S e in prodotti come Obico ([01_RESEARCH_STACK.md](01_RESEARCH_STACK.md) §5);
- la **correzione in tempo reale** dei parametri di macchina è stata dimostrata in ricerca (CAXTON, Cambridge 2022), ma richiede una camera accanto all'ugello e agisce sul firmware, non sul preset.

Nessuno dei due trasforma un difetto osservato in una **modifica persistente e verificata del preset**.

## 3. Utente e KPI

- **Utente:** operatore o tecnico di un reparto di stampa 3D, piccola officina additiva o service di prototipazione con più macchine e materiali.
- **KPI della demo:**
  - iterazioni necessarie per arrivare a un pezzo accettabile, contro una baseline senza PrintLoop;
  - grammi di filamento e minuti di macchina per iterazione;
  - severità del difetto prima e dopo, misurata con la stessa rubrica;
  - accuratezza della diagnosi su difetti indotti con causa nota.

## 4. Cosa rende il progetto diverso

1. **Il modello sceglie, non inventa.** Gemma 4 classifica il difetto in una tassonomia chiusa e sceglie tra parametri candidati forniti da una knowledge base deterministica. Range e direzione delle modifiche sono vincolati.
2. **Ogni patch è verificata prima di stampare.** Dopo il re-slice, il pre-flight confronta il G-code prima e dopo (velocità e flusso per feature, ventola, flusso volumetrico rispetto al limite del filamento). Se la modifica non si vede nel G-code, la patch non passa.
3. **Il risultato si misura.** Dopo la ristampa lo stesso modello valuta il pezzo con la stessa rubrica. Il loop si ferma al successo o dopo K iterazioni, e in quel caso passa la mano all'umano con lo storico.
4. **Funziona su macchine di serie.** Bastano le foto del telefono e il preset. Non servono camere aggiuntive né firmware modificati. La telemetria live della P1S è un'aggiunta, non un requisito.

## 5. Scope

**Dentro (MVP), solo Modo 2, post-stampa:**
- upload del progetto `.3mf` stampato (contiene modello e impostazioni) e di 1–4 foto del pezzo;
- diagnosi con Gemma 4 su vLLM-ROCm (MI300X), con output JSON con schema;
- KB difetto → parametri, generazione della patch (massimo 2 parametri) e validatore;
- re-slice con OrcaSlicer CLI, parsing del G-code e pre-flight;
- UI di approvazione con diff del preset, diff del pre-flight ed export del preset;
- valutazione su una serie di stampe con difetti indotti, benchmark AMD.

**Stretch:**
- Modo 1, live: telemetria MQTT e frame dalla camera P1S, rilevamento di difetti grossolani, pausa o stop con conferma;
- invio della ristampa via MQTT (`print.project_file`);
- confronto tra 26B-A4B e 31B, fine-tuning di un classificatore leggero su ROCm (dataset CAXTON).

**Fuori:**
- modifiche ai parametri durante la stampa (sono incorporati nel G-code);
- guasti meccanici (cinghie, ugello danneggiato, eccentrici);
- stampanti diverse dalla P1S e slicer diversi da OrcaSlicer;
- qualsiasi bypass dell'autenticazione Bambu.

## 6. Correzioni rispetto al concept originale

| Concept originale ([`01_printloop.md`](../ideas/01_printloop.md)) | Versione corretta | Motivo (fonte in 01_RESEARCH_STACK) |
| :-- | :-- | :-- |
| Modo 1 e Modo 2 alla pari, Modo 1 come trigger | **Modo 2 è il prodotto**, Modo 1 è stretch | La camera P1S produce JPEG 1280×720 a ~0,5–1 fps (§2.3). La P1S ha già un rilevamento spaghetti a bordo (§5) |
| Input video a Gemma (fino a 32 frame per richiesta) | **Immagini multiple** (`--limit-mm-per-prompt`) | La recipe vLLM non documenta un limite di frame per il video (§3.2). Le foto sono più semplici e più nitide |
| "Velocità" come override durante la stampa | Solo **4 livelli di velocità** (silent, standard, sport, ludicrous) | `print.print_speed` accetta solo i valori 1–4 (§2.2) |
| Appiattire i preset con `inherits` a mano | **`--export-settings`** della CLI | La CLI esporta le impostazioni effettive in un JSON (§4.2) |
| Output del re-slice: G-code | **3MF con G-code dentro** (`Metadata/plate_N.gcode`) | La CLI documentata esporta 3MF, non `.gcode` (§4.2) |
| "Loop chiuso" come differenziatore | Il differenziatore è **patch persistente del preset + verifica sul G-code** | CAXTON fa già correzione in loop chiuso in tempo reale (§5) e va citato come prior art |
| Dataset solo nostro | Dataset nostro come test set + **CAXTON (CC BY 4.0)** per il benchmark ROCm | 1,27 M immagini etichettate con flow, velocità, Z offset e temperatura (§6) |

## 7. Mappa dei documenti

| Doc | Contenuto |
| :-- | :-- |
| [01_RESEARCH_STACK.md](01_RESEARCH_STACK.md) | Cosa dicono le fonti ufficiali: Bambu Developer Mode, MQTT, camera, OrcaSlicer CLI, Gemma 4 e vLLM, AMD, prior art, dataset |
| [02_DATA_STRATEGY.md](02_DATA_STRATEGY.md) | Dati a disposizione, matrice dei difetti indotti, rubrica, ground truth, metriche |
| [03_ARCHITECTURE.md](03_ARCHITECTURE.md) | Componenti, contratti JSON, KB, pre-flight, macchina a stati, struttura del codice |
| [04_PLAN_DECISIONS_RISKS.md](04_PLAN_DECISIONS_RISKS.md) | Decisione PrintLoop o MarginSwarm, spike con criteri go/no-go, piano fino alla consegna, rischi, domande aperte |
| [05_API.md](05_API.md) | Contratto API per il frontend, stati e azioni ammesse, fixture |
| [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md) | Cosa funziona, risultati misurati, limiti, prossimi passi |

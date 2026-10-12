# Guida Completa all'Hackathon: AMD Developer Hackathon: ACT III 📘

Questo documento riassume le linee guida operative, le regole, i requisiti tecnologici e le scadenze per la partecipazione all'**AMD Developer Hackathon: ACT III**.

---

## 1. Informazioni Generali e Calendario 🗓️

- **Titolo Ufficiale**: AMD Developer Hackathon: ACT III
- **Organizzatori / Partner**: AMD, lablab.ai, Vibe Generation, Evolus AI, Google, PwC Italy.
- **Formato**: Ibrido (Online + On-site in Italia per chi viene approvato).

### Date Chiave:
- **Online Build Phase**: **12 – 18 Ottobre 2026**
- **Fase On-site (Italia)**: **17 – 18 Ottobre 2026**
  - **Roma**: *Link Campus University*, Via del Casale di San Pio V, 44, 00165 Roma
    - Sabato 17 Ott: 10:00 - 18:00 | Domenica 18 Ott: 10:00 - 17:00
  - **Milano**: *SmartCityLab Milano*, Via Giuseppe Ripamonti, 88, 20141 Milano
    - Sabato 17 Ott: 09:00 - 18:00 | Domenica 18 Ott: 09:00 - 17:00
  - **Imperia**: *IMPERIAWARE*, Via Antonio Delbecchi, 22, 18100 Imperia (IM)
    - Sabato 17 Ott: 09:00 - 18:00 | Domenica 18 Ott: 09:00 - 17:00

---

## 2. Requisiti di Ammissione & Regolamento 📋

1. **Iscrizione su lablab.ai**: Registrazione al portale e adesione all'evento.
2. **Accesso a Discord**: Ingresso nel server Discord ufficiale di [lablab.ai](https://discord.gg/lablabai).
3. **Iscrizione obbligatoria ad AMD AI Developer Program (ADP)**:
   - È **obbligatorio** registrarsi a [developer.amd.com/ai-developer-program/](https://developer.amd.com/ai-developer-program/).
   - I nuovi membri ricevono **$100 di crediti AMD gratuiti**.
4. **Dimensione del Team**: Da **1 a 6 persone**.
5. **Licenza del Codice**: Progetto originale con licenza compatibile MIT.
6. **Sicurezza**: **MAI committare credenziali, chiavi API o dati sensibili** nella repository pubblica. Usare sempre variabili d'ambiente (`.env`).

---

## 3. Requisito Tecnologico Obbligatorio: BUILD ON AMD ⚙️

> [!IMPORTANT]
> **La tecnologia AMD è un requisito tassativo per essere eleggibili a qualsiasi premio.**
> Ogni progetto deve eseguire una parte significativa e reale del carico di lavoro su infrastruttura o hardware AMD.

### Tecnologie AMD ammesse:
- **AMD Developer Cloud**: Istanze GPU on-demand (acceleratori AMD Instinct, es. MI300/MI250/MI210) accessibili via cloud.
- **AMD ROCm**: Piattaforma open source per GPU computing (equivalente di CUDA). Supporta PyTorch, TensorFlow, vLLM e Triton.
- **AMD Ryzen AI**: NPU/acceleratori edge su processori Ryzen.
- **Hardware AMD Radeon**: GPU desktop/workstation compatibili ROCm.
- **Serving Stack consigliato**: Endpoint [vLLM](https://docs.vllm.ai/) serviti su AMD Developer Cloud con open models (es. Llama, Mistral, Qwen, Gemma, ecc.).

### Cosa mostrare alla giuria (AMD Evidence):
1. **Quale componente ha girato su AMD**: Spiegazione dettagliata dell'architettura e del carico computazionale.
2. **Stack di serving e modelli utilizzati**: Es. *vLLM su GPU AMD Instinct MI300X via AMD Developer Cloud*.
3. **Benchmark o metrica di performance**: Almeno una misurazione reale (es. latenza token/s, tempo di inferenza/fine-tuning rispetto a baseline).

---

## 4. Tecnologie Partner (Opzionali ma Premiate) 🤝

- **Google**: Disponibili premi Google per $5,000 (integrazioni con modelli o cloud Google, es. Gemma, Google Cloud, Vertex AI).
- **Evolus AI**:
  - Workspace gratuito fino al 31 Ottobre 2026 con 50.000 crediti inclusi.
  - Piattaforma per agenti aziendali: Workflow visuali/API, estrattori documenti (PDF to JSON), 11 AI Tools pronti all'uso, RAG knowledge libraries, protocollo MCP (Model Context Protocol).
  - Eleggibilità per premi Evolus (€1,011.50) se si usano almeno 2 blocchi Evolus e un modello open servito su AMD via vLLM.
- **Vibe Generation**:
  - Partner speciale per le 4 sfide aziendali.
  - Premio speciale (AirPods 5 per ogni membro del team) per soluzioni con eccellente workflow ibrido Uomo-AI, impatto commerciale e capacità di esecuzione.
- **PwC Italy**: Partner per l'innovazione d'impresa e scalabilità dei processi.

---

## 5. Checklist di Consegna (What to Submit) 📦

Per completare la sottomissione su lablab.ai, il progetto deve includere:

### 📋 Progetto e Metadati
- [ ] **Titolo del Progetto** (chiaro, professionale, memorabile).
- [ ] **Short Description** (1-2 frasi a effetto).
- [ ] **Long Description** (problema, soluzione, architettura, valore di business).
- [ ] **Track/Challenge selezionata** (Track 1, 2, 3, 4 o Evolus).
- [ ] **Tag tecnologici e categorie** (es. `AMD ROCm`, `vLLM`, `Agents`, `Computer Vision`, `FastAPI`, `Next.js`).

### 📸 Presentazione & Demo
- [ ] **Cover Image** (grafica accattivante 16:9).
- [ ] **Demo Video** (video registrato di max 2-3 minuti che mostra il prototipo funzionante end-to-end con dati realistici).
- [ ] **Pitch Presentation** (slide deck / PDF che spiega problema, target user, impatto e modello economico).

### 💻 Codice & Deployment
- [ ] **Repository GitHub pubblica** (con licenza open-source MIT).
- [ ] **README chiaro e riproducibile** (istruzioni passo-passo per clonare, installare dipendenze ed eseguire in locale o con Docker).
- [ ] **Diagramma architetturale** (flusso dati, modelli, componenti AMD).
- [ ] **Link all'applicazione live** (se disponibile URL pubblicamente raggiungibile).

### 🔬 Sezione Evidenze AMD & Valutazione Critica
- [ ] **AMD Evidence**: dettaglio hardware/cloud AMD utilizzato, configurazione ROCm/vLLM e benchmark.
- [ ] **Risultato di Business misurabile**: stima dell'impatto su costi, tempo, conversione o sicurezza.
- [ ] **Limiti noti e Casi di fallimento (Failure cases)**: onestà intellettuale su cosa il sistema non fa ancora o dove può sbagliare.
- [ ] **Meccanismo di salvaguardia (Human-in-the-loop)**: come un operatore umano interviene in caso di incertezza.

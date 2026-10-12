# Track e Sfide Ufficiali: AMD Developer Hackathon: ACT III 🎯

Il tema centrale dell'hackathon è:
> **"Solve a real Business Problem with AMD technology"**
>
> È possibile scegliere **una o più track** e costruire un prodotto funzionante basato su infrastruttura AMD. La soluzione deve risolvere un problema reale per un utente reale, combinando modelli di linguaggio, computer vision, audio, agenti autonomi, modelli predittivi o una combinazione di questi.

---

## 🏭 Track 1: Intelligent Industry
*In partnership con Vibe Generation*

> **Motto:** *"Aiuta le fabbriche e gli impianti a individuare i problemi prima e a operare meglio."*

### Il Problema:
Gli stabilimenti industriali producono quantità enormi di dati da macchinari, telecamere, sensori IoT, report di manutenzione e manuali tecnici. Il problema non è la scarsità di informazioni, ma **capire cosa conta davvero e cosa fare subito dopo**.

### Idee di Progetto Suggerite:
- Predizione di guasti ai macchinari (Predictive Maintenance).
- Rilevamento difetti da immagini o streaming video (Computer Vision in linea di produzione).
- Spiegazione delle anomalie di produzione per gli operatori.
- Assistente tecnico per la ricerca semantica avanzata su manuali operativi e storici interventi (RAG specializzato).
- Raccomandazione automatica di azioni correttive e ticket di manutenzione.
- Monitoraggio della sicurezza sul lavoro e conformità DPI (caschetti, giubbotti).
- Riduzione degli sprechi energetici e di materiale grezzo.

### Cosa Deve Mostrare la Demo:
- Il prodotto deve processare **dati industriali realistici** (telemetria, log di macchine, immagini termiche o difetti).
- Generare un **output azionabile**: un alert chiaro, una spiegazione causale dell'anomalia o un suggerimento pratico di intervento.
- Deve essere evidente **chi utilizzerà il prodotto** (es. manutentore, plant manager, operatore di linea) e quale KPI migliora.

### Cosa Cercano i Giudici:
- Un vero problema manifatturiero ben identificato.
- Un prodotto funzionante (non solo una dashboard passiva o slide).
- Risultati interpretabili e comprensibili dall'operatore.
- Un miglioramento misurabile in termini di tempo, costi, sicurezza, qualità o efficienza.

---

## 🏥 Track 2: Health and Wellbeing
*In partnership con Vibe Generation*

> **Motto:** *"Rendi una parte del percorso del paziente più sicura, chiara o semplice."*

### Il Problema:
Pazienti, caregiver e personale sanitario si scontrano quotidianamente con documenti chilometrici, informazioni frammentate, burocrazia ripetitiva, barriere linguistiche e tempo cronico insufficiente.

### Idee di Progetto Suggerite:
- Triage / Intake preliminare del paziente e raccolta anamnestica strutturata.
- Sintesi intelligente di cartelle cliniche complesse e storici esami.
- Preparazione alle visite specialistiche e checklist pre-operatorie.
- Navigazione della cura e supporto terapeutico continuativo.
- Istruzioni di dimissione ospedaliera chiare, semplificate e personalizzate.
- Comunicazione multilingue per pazienti stranieri.
- Automazione dei flussi documentali e amministrativi ospedalieri.
- Supporto alla prevenzione e benessere psicofisico basato su dati oggettivi.

### Requisiti di Sicurezza & Guardrails (Mandatory Safety Rules):
- **DIVIETO DI DIAGNOSI AUTONOMA**: Il prodotto non deve mai presentare diagnosi o terapie autonome come parere medico definitivo.
- **Gestione dell'Incertezza**: Il sistema deve rendere visibile l'incertezza e mostrare le fonti utilizzate.
- **Human-in-the-Loop**: Deve essere previsto un chiaro punto di escalation in cui un medico/operatore umano valida o subentra.
- **Privacy e Dati Sensibili**: Mascheramento e gestione responsabile dei dati sanitari (GDPR compliant).

### Cosa Cercano i Giudici:
- Un bisogno ben definito di pazienti o personale sanitario.
- Trattamento responsabile ed etico delle informazioni sanitarie.
- Risultati fruibili e privi di ambiguità.
- Guadagno quantificabile in tempo risparmiato, accessibilità o riduzione del carico mentale.

---

## 🛒 Track 3: Reinvent Commerce
*In partnership con Vibe Generation*

> **Motto:** *"Aiuta le aziende a comprendere i clienti e a prendere decisioni migliori."*

### Il Problema:
I retailer e gli e-commerce dispongono di dati di catalogo, scontrini, scorte di magazzino, recensioni, ticket di supporto e campagne marketing. Spesso questi silos non comunicano tra loro, rendendo quasi impossibile trasformarli in azioni commerciali tempestive.

### Idee di Progetto Suggerite:
- Shopping assistant conversazionali contestuali e multimodali.
- Discovery di prodotto evoluta e raccomandazioni iper-personalizzate.
- Assistenza clienti automatizzata con risoluzione autonoma di problemi su ordini/resi.
- Pianificazione della domanda e ottimizzazione dell'inventario.
- Arricchimento automatico e classificazione dei cataloghi prodotto.
- Sentiment analysis e clustering avanzato delle recensioni dei clienti.
- Prevenzione dell'abbandono (churn prevention) e promozioni dinamiche.
- Shopping accessibile e multilingua istantaneo.
- Computer vision in-store (es. monitoraggio scaffali vuoti o interazione clienti).

### Regola Fondamentale per la Demo:
- Trasformare dati disgiunti in un'azione o raccomandazione commerciale concreta.
- **Nota sul Forecasting**: Se il progetto prevede la previsione di vendite o domanda, **non utilizzare un LLM come unico metodo di stima!** Occorre spiegare e motivare l'algoritmo predittivo impiegato (es. modelli di serie temporali, regressioni, boosting o ensemble).

### Cosa Cercano i Giudici:
- Un problema reale per il cliente finale o per il merchant.
- Un'azione commerciale utile e direttamente applicabile.
- Impatto misurabile su revenue, margini, conversion rate, retention o rotazione di magazzino.

---

## 🎨 Track 4: Create a New Kind of Experience
*In partnership con Vibe Generation*

> **Motto:** *"Costruisci un'esperienza di media, marketing o intrattenimento impensabile prima della generative AI."*

### Il Problema:
Non basta generare una semplice immagine statica, un testo promozionale o un chatbot ordinario. L'obiettivo è creare un'esperienza interattiva che risponda al pubblico, muti in base al contesto e si adatti individualmente a ciascun utente.

### Idee di Progetto Suggerite:
- Video personalizzati dinamici in tempo reale.
- Narrazioni interattive non lineari guidate dall'utente (Interactive Storytelling / Gaming).
- Intrattenimento interattivo guidato dalla community.
- Campagne pubblicitarie adattive in base a contesto, meteo, trend o reazioni.
- Contenuti creativi localizzati e multilingue senza attriti.
- Ambienti audio/video generativi e reattivi in tempo reale.
- Nuovi format per social media o live streaming.
- Sistemi di Quality Control e coerenza stilistica per creativi.

### Requisiti Specifici della Demo:
- Mostrare l'esperienza mentre **si adatta a due pubblici, contesti o input differenti**.
- Spiegare chiaramente:
  1. Cosa ha creato il team vs cosa ha generato o deciso il modello.
  2. Come viene garantita la coerenza stilistica e qualitativa.
  3. **Unit economics**: quanto costa generare ogni singola esperienza (costo per utente/sessione).
  4. Chi pagherebbe per questo prodotto e per quale motivo.

---

## 🤖 Partner Track: Evolus Business Agents on AMD
*In partnership con Evolus AI*

> **Motto:** *"Costruisci un agente AI che esegue un processo aziendale reale end-to-end su Evolus, alimentato da un modello open servito su AMD."*

### Come Funziona la Piattaforma Evolus:
Evolus consente di costruire agenti che leggono documenti, interrogano librerie di conoscenza aziendale (RAG), eseguono automazioni di business e interagiscono con sistemi esterni via API e protocollo **MCP (Model Context Protocol)**.

### Requisiti Tecnici Obbligatori per la Track:
1. **Workspace Gratuito**: Creare un workspace evento gratuito su [app.evolus.ai](https://app.evolus.ai) (con codice fornito al kickoff: 50.000 crediti inclusi, valido fino al 31 Ottobre).
2. **Bring Your Own Model (BYOM)**: L'agente principale deve utilizzare un modello open-source servito su infrastruttura AMD (es. tramite un endpoint **vLLM** su **AMD Developer Cloud** o compatibile OpenAI).
3. **Utilizzo di almeno 2 blocchi Evolus**:
   - Workflows (automazioni multi-step con rami e loop).
   - Document Extractors (conversione PDF/scansioni in JSON strutturato con schema).
   - AI Tools (11 tool pronti: table extraction, redazione dati personali in PDF, traduzione preservando il layout, verbali da audio/video, comparazione testi).
   - Knowledge Libraries (RAG con citazione delle fonti).
   - MCP Connectors / Sub-agents / Chat widget.
4. **Integrazione API**: Interfacciare Evolus dall'applicazione via REST API o OpenAI-compatible endpoint.

### Esempi di Processi Aziendali:
- Gestione automatica ordini e fatture da email con allegati PDF.
- Helpdesk di primo livello su documentazione interna con escalation umana.
- Qualificazione lead e push automatico su CRM via MCP.
- Revisione e redazione automatica di contratti legali.
- Analisi registrazioni riunioni con estrazione automatica delle to-do list.

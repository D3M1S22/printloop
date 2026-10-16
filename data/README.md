# data/

Non versionata, tranne questo file.

- `data/testset/`: generata da `uv run printloop testset`. Un caso per cartella (C0–C7) con il progetto patchato (`project.3mf`), il 3MF già slicato da stampare (`slice/sliced.3mf`) e il `manifest.json` con la ground truth (parametro indotto, patch attesa). Dopo la stampa, le foto vanno in `data/testset/<caso>/photos/` (protocollo in [docs/printloop/02_DATA_STRATEGY.md](../docs/printloop/02_DATA_STRATEGY.md) §3.1); poi `uv run python -m printloop.eval diagnosis`.

I casi di lavoro (foto, patch, G-code, audit) stanno in `runs/cases/<id>/`, anch'essa non versionata.
Dataset pubblici (CAXTON, CC BY 4.0) non ridistribuiti.

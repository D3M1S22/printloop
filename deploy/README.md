# Deploy on the homelab (Proxmox)

One Docker container serves the API, the UI (`web/dist`) and both slicers (OrcaSlicer 2.4.2 and BambuStudio
02.08.02.61, AppImages extracted in the image). Gemma 4 26B comes from the llama.cpp router on CT 100
(`http://192.168.1.159:8080/v1`, `Gemma-4-26B-Vision-Q3`). The E4B detector (`VISION_LLM_*`) is off until set in `.env`.

| | |
| :-- | :-- |
| CT | clone of template **117** `ServiceAgyDocker` (Docker, `nesting=1`), storage `SSD2`, disk ≥ 16 GB |
| Code | `/opt/printloop` (git clone, branch `PrintLoop`) |
| Port | `8788` (API + UI) |
| Data | `/opt/printloop/runs` (cases, audit), `/opt/printloop/replay` (Mode 1 recorded frames) |
| Public URL | `https://printloop.devgiov.com` |

## First install

```bash
# Proxmox host
pct clone 117 <VMID> --hostname printloop --full --storage SSD2
pct resize <VMID> rootfs 16G
pct set <VMID> --net0 name=eth0,bridge=vmbr0,ip=<IP>/24,gw=<GATEWAY> --onboot 1
pct start <VMID>

# In the CT (the GitHub repo is private: add a read-only deploy key first)
git clone -b PrintLoop git@github.com:D3M1S22/printloop.git /opt/printloop
/opt/printloop/deploy/install.sh
```

`install.sh` creates `.env` from `.env.example` if missing (26B endpoint filled in), builds the image, starts the
container and waits for `/api/health`.

## Update

```bash
cd /opt/printloop && git pull && deploy/install.sh
```

## Exposure

The app has **no authentication**: anyone who reaches it can create and delete cases and use the 26B on CT 100.
Put an access control in front of it on the public proxy (NPM access list or Cloudflare Access) before publishing
`printloop.devgiov.com`. Uploads are 3MF projects and photos: allow at least 100 MB request bodies on the proxy.

## Checks

```bash
curl -s http://localhost:8788/api/health        # slicer.installed lists orca and bambu, llm.mode = "llm"
docker compose -f deploy/compose.yaml logs -f
```

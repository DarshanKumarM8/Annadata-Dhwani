# Windows 11 Backup Laptop Setup Checklist (Task N8)

This guide provides step-by-step instructions to configure a Windows 11 laptop to run the entire **Annadata Dhwani** stack **100% offline** during the live hackathon jury presentation, mitigating single-laptop failure risk.

---

## 1. Prerequisites Installation (Perform While Connected to Internet)

Install all foundational runtimes and toolchains on Windows 11:

### 1.1 Git for Windows
- Download and install [Git for Windows](https://git-scm.com/download/win).
- Ensure Git is added to the system `PATH`.

### 1.2 Docker Desktop
- Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
- Ensure **WSL 2 backend** is enabled during installation.
- Verify in PowerShell:
  ```powershell
  docker --version
  docker compose version
  ```

### 1.3 Python 3.12+
- Download and install Python 3.12.x from [python.org](https://www.python.org/downloads/).
- **Important:** Check the box **"Add python.exe to PATH"** during setup.
- Verify:
  ```powershell
  python --version
  ```

### 1.4 Node.js 20 LTS & npm
- Download and install Node 20 LTS from [nodejs.org](https://nodejs.org/).
- Verify:
  ```powershell
  node --version
  npm --version
  ```

### 1.5 FFmpeg
- Install via Windows Package Manager (`winget`):
  ```powershell
  winget install Gyan.FFmpeg
  ```
- Alternatively, download essentials from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and add `bin/` to system `PATH`.
- Verify:
  ```powershell
  ffmpeg -version
  ```

---

## 2. Online Cache & Pre-pulling (Mandatory Before Heading to Venue)

All containers, pip wheels, and npm modules must be cached locally so no internet connection is required on-site.

### 2.1 Pre-pull Docker Images
Execute in PowerShell:
```powershell
docker pull postgis/postgis:16-3.4
docker pull valkey/valkey:8
```
Verify cached images:
```powershell
docker images
```

### 2.2 Clone Repository & Configure Environment
```powershell
git clone https://github.com/DarshanKumarM8/Annadata-Dhwani.git F:\Annadata-Dhwani
cd F:\Annadata-Dhwani
```
Copy `.env` received privately from Darshan / team lead into repo root:
```powershell
# Copy the secure .env file (or copy template if testing locally)
Copy-Item .env.example .env
```
Ensure key environment flags inside `.env`:
- `DEMO_MODE=true`
- `TELEPHONY_PROVIDER=sim` (or `exotel` if live cellular demo)
- `POSTGRES_USER=postgres`
- `POSTGRES_PASSWORD=postgres`
- `POSTGRES_DB=annadata`
- `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/annadata`
- `REDIS_URL=redis://localhost:6379/0`
- `SEED_PASSWORD=demo`

### 2.3 Setup Python Virtual Environment & Install Dependencies
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 2.4 Build Frontend Assets
```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run build
cd ..
```

---

## 3. Starting the Stack Offline (Cold Boot Walkthrough)

To verify the setup, **disable Wi-Fi / disconnect ethernet** and run through the stack.

### 3.1 Start Docker Containers
From repository root (`F:\Annadata-Dhwani`):
```powershell
docker compose up -d
```
Verify containers are healthy (`annadata-db-1` and `annadata-cache-1`):
```powershell
docker compose ps
```

### 3.2 Initialize Database Schema & Reference Data
Execute `psql` directly inside the PostGIS container to load schemas:
```powershell
# Load DDL schema (PostGIS tables, constraints, events outbox)
docker exec -i annadata-db-1 psql -U postgres -d annadata < db/001_schema.sql

# Load Reference data (Mandya/Mysuru mandis, MSP prices, crop varieties)
docker exec -i annadata-db-1 psql -U postgres -d annadata < db/002_reference.sql
```

### 3.3 Reset & Seed Demo Data
Populate demo farmers, buyers, agents, and pre-computed demo clusters:
```powershell
.\.venv\Scripts\Activate.ps1
python backend/scripts/seed_demo.py --reset
```

### 3.4 Launch FastAPI Backend Server
```powershell
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3.5 Verify Health & Demo UIs
Open a web browser on the backup laptop:
1. **Health Check:** `http://localhost:8000/health`  
   *(Expected response: `{"status":"ok"}`)*
2. **Live Demo Master Board:** `http://localhost:8000/demo`  
   *(Enter password `demo` to view cluster pipeline, bids, and simulated calls)*
3. **Frontend Application:**  
   In a separate terminal, serve the frontend:
   ```powershell
   cd frontend
   npm run dev -- --host 0.0.0.0
   ```
   Open `http://localhost:5173/buyer` or `http://localhost:5173/sim`.

---

## 4. Full Offline Demo Run (Wi-Fi Disabled)

Test a complete marketplace cycle without internet:

1. **Simulate Inbound Farmer Listing:**
   ```powershell
   python backend/scripts/sim_client.py --phone +919800000001 --crop ragi --qty 25 --price 3200
   ```
   Confirm cluster moves to `READY` state at 20 quintals.
2. **Simulate Agent Verification:**
   On `http://localhost:8000/demo`, click **Verify Cluster** (or run `POST /api/agent/clusters/{id}/verification`).
   Cluster transitions to `BIDDING`.
3. **Simulate Buyer Bids:**
   Submit bid via Buyer UI (`/buyer`) or Demo Board.
4. **Trigger Offer Confirmation Round:**
   Close auction on demo board. Observe simulated automated outbound calls on `/sim`.
5. **Confirm Acceptance:**
   Simulate farmer confirmation (keys `1` then `1`). Deal is generated with 1.5% FPO fee.

---

## 5. Common Windows 11 Troubleshooting & Quick Fixes

| Issue / Error Message | Root Cause | Exact Solution |
|---|---|---|
| `PSSecurityException: UnauthorizedAccess` when running `Activate.ps1` | PowerShell execution policy restricts scripts | Run once in Administrator PowerShell: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `bind: address already in use: 0.0.0.0:5432` | Local PostgreSQL service is running on Windows host | Stop Windows service: `Stop-Service postgresql*` or set `DB_PORT=5433` in `.env` and `docker-compose.yml`. |
| `WSL 2 installation is incomplete` / Docker fails to start | WSL2 kernel package missing or Hyper-V virtualization disabled | Run `wsl --update` in admin terminal. Ensure SVM / Intel Virtualization (VT-x) is enabled in laptop BIOS. |
| `PermissionError: [WinError 32] file being used by another process` during audio mixing | Windows file locking on temporary `.wav` / `.mp3` files | The codebase handles this with retry logic in `audio.py`. Ensure no audio player has `.wav` files open in background. |
| Cannot access backend from other laptops on local hotspot | Windows Defender Firewall blocking port 8000 | In PowerShell (Admin): `New-NetFirewallRule -DisplayName "Annadata Backend" -Direction Inbound -LocalPort 8000,5173 -Protocol TCP -Action Allow` |
| `docker compose` says `image not found` while offline | Image was not pre-pulled while connected to internet | Verify `docker images` shows `postgis/postgis:16-3.4` and `valkey/valkey:8`. If missing, hotspot to mobile phone momentarily to pull. |

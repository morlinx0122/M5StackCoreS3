# DeepNexus AI Gateway

FastAPI + SQLite gateway for the M5Stack CoreS3 desktop AI assistant.

## Run

```powershell
cd gateway
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Smoke Test

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```


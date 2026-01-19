# BRD Analyzer (FastAPI + Vercel)

## Local run

1) Create venv + install deps:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

2) Set env var:

- `GROQ_API_KEY` (required)

3) Run locally with Vercel dev:

```bash
vercel dev
```

Open:
- http://localhost:3000

## Deploy

- Push to GitHub
- Import into Vercel
- Set `GROQ_API_KEY` in Project Settings → Environment Variables

## API

- `GET /api/health`
- `POST /api/analyze?output=pdf|json` (multipart form field `file`)

# Deploy FastAPI to Render

## Why Blueprint asked for a credit card

The repo `render.yaml` must use **`plan: free`**. If it says `plan: starter`, Render treats it as a **paid** service (~$7/mo) and requires a payment method.

Free web services do **not** require a card for most accounts. If Blueprint still asks for a card, skip Blueprint and use **Manual Web Service** below (Step-by-step in `deploy/RENDER-FREE.md`).

## Manual setup (Render Dashboard) — recommended for free tier

Create a **Web Service** with:

| Field | Value |
|-------|-------|
| **Root Directory** | `python` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Health Check Path** | `/health` |

## Environment variables

Tencent ASR（转写）、Tencent SOE（客观语音评估）与智谱 GLM（打分）使用独立配置。Listen & Repeat 与 Virtual Interview 均走 Python API。

### Required (production)

```env
# 智谱 — 打分（Listen & Repeat + Virtual Interview）
GLM_API_KEY=your_zhipu_api_key
GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL_NAME=glm-4.7-flashx

# Tencent — 转写与语音评估
ASR_PROVIDER=tencent
SPEECH_EVAL_PROVIDER=tencent
TENCENT_SECRET_ID=your_tencent_secret_id
TENCENT_SECRET_KEY=your_tencent_secret_key
TENCENT_REGION=ap-guangzhou
TENCENT_ASR_ENGINE_MODEL_TYPE=16k_en
TENCENT_SOE_ENDPOINT=https://soe.tencentcloudapi.com

# Optional legacy ASR fallback
# ASSEMBLYAI_API_KEY=your_assemblyai_key
# ASSEMBLYAI_BASE_URL=https://api.assemblyai.com
# ASSEMBLYAI_SPEECH_MODELS=universal-2

# Next.js
PYTHON_SPEECH_API_URL=http://localhost:8000
PYTHON_SPEECH_API_KEY=shared_secret_for_nextjs
CORS_ORIGINS=https://your-next-app.onrender.com

DEV_ECHO_REFERENCE=false
```

### Local debug (credential-free)

Use deterministic local adapters to exercise the full workflow without cloud credentials:

```env
GLM_API_KEY=your_zhipu_api_key
ASR_PROVIDER=mock
SPEECH_EVAL_PROVIDER=mock
```

## Blueprint (Infrastructure as Code)

From repo root, use `render.yaml`:

```bash
# Render Dashboard → New → Blueprint → select this repository
```

## Wire Next.js to Render Python API

In Vercel / Render (Next.js app) `.env`:

```env
PYTHON_SPEECH_API_URL=https://ai-speaking-trainer-python.onrender.com
PYTHON_SPEECH_API_KEY=same_value_as_python_service
```

## Verify

```bash
curl https://your-python-service.onrender.com/health
# {"status":"ok","service":"ai-speaking-trainer-python"}
```

## Notes

- **`python/.env` is gitignored** — never commit API keys.
- **Region**: choose `Singapore` if your Zhipu / users are in China-adjacent regions.
- **Librosa**: if build fails on audio libs, upgrade to a Docker-based deploy.
- **Waveform metrics**: install `ffmpeg` on the Python service host so browser WebM recordings can be decoded; without it the API marks acoustic metrics as transcript-based estimates.
- **Phase 4 scoring**: the API returns a versioned `scoring` breakdown; see `python/SCORING.md` for the heuristic and optional `DELIVERY_SCORING_*` configuration.
- **Cold start**: free/starter plans sleep; first request may take 30–60s.

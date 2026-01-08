# 🚀 TITAN ENGINE v19.0 - Ultimate Chat Bot Core

**Plugin-based multi-chatroom game bot engine** - Deploy once, add unlimited games/plugins!

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=YOUR_GITHUB_REPO)

## ✨ Features

- ✅ **Multi-chatroom support** (comma-separated rooms)
- ✅ **Plugin architecture** - No engine changes needed!
- ✅ **PostgreSQL (Neon)** with auto-healing connections
- ✅ **90s auto-cleanup** with game-specific notifications
- ✅ **Thread-safe** (locks, pools, cooldowns)
- ✅ **Production ready** (Render/Gunicorn)
- ✅ **Structured global data** (per-room, per-plugin)

## 🛠️ Quick Start

### Local
```bash
pip install -r requirements.txt
cp .env.example .env  # Edit NEON_URL
python app.py

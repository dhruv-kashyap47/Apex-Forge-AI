# Quick Start — ApexForge AI

Get the app running in **2 minutes**:

## 1. Install (one command)

```bash
cd ApexForge
pip install -r requirements.txt
```

## 2. Run

```bash
streamlit run app.py
```

Opens automatically at: **http://localhost:8501**

## 3. Explore

- **Dashboard**: View KPIs and charts (2,000 pre-loaded synthetic records)
- **Entity Explorer**: Search for any business name, PAN, or PIN code
- **Processing**: Click "Normalize, Match & Assign UBIDs" to run entity resolution
- **Query Builder**: Try demo query "Dormant factories in 560058"
- **Audit Trail**: See all decisions logged immutably

## Key Files

- `app.py` — Entry point
- `.env` — Config (demo mode enabled)
- `requirements.txt` — Dependencies
- `SETUP.md` — Full documentation

## What's Included

✅ Entity resolution (phonetic + semantic matching)
✅ In-memory demo store (2,000 synthetic records)
✅ Vitality scoring (ACTIVE/DORMANT/CLOSED)
✅ Review queue (human-in-the-loop)
✅ Query builder (no SQL needed)
✅ Audit trail (immutable log)
✅ Export (CSV/JSON/Excel)
✅ Graph visualization

## Troubleshooting

**Port already in use?**

```bash
streamlit run app.py --server.port 8502
```

**Slow first load?**
The embedding model (~400 MB) downloads on first use. Cached afterward.

**Memory issues?**

```bash
SEED_RECORDS=500 streamlit run app.py
```

## Next Steps

- Read [SETUP.md](SETUP.md) for full configuration and features
- Check [README.md](README.md) for problem background
- See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for walkthrough script

**Enjoy!** 🏛️

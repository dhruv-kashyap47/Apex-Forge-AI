# ApexForge AI — Setup & Usage Guide

## Overview

**ApexForge AI** is a Streamlit-based entity resolution system for linking government and business records across department silos. It demonstrates how the same business can appear under slightly different names in different departments and provides a unified view through a Unified Business Identifier (UBID).

**Key Capabilities:**

- Record upload and schema mapping (CSV/JSON)
- Entity resolution engine with phonetic and semantic matching
- Vitality scoring (classification as ACTIVE, DORMANT, or CLOSED)
- Human-in-the-loop review queue
- Graph visualization of entity relationships
- Powerful query builder without SQL knowledge
- Immutable audit trail for compliance
- Full end-to-end demo with synthetic data

---

## Requirements

- **Python**: 3.11 or higher (tested with 3.13.5)
- **Disk Space**: ~500 MB for dependencies
- **RAM**: 4 GB recommended (2 GB minimum for demo mode)
- **Operating System**: Windows, macOS, or Linux

---

## Installation

### Step 1: Install Dependencies

```bash
cd ApexForge
pip install -r requirements.txt
```

This installs:

- **Streamlit** - Web UI framework
- **Pandas, NumPy** - Data processing
- **Sentence-Transformers** - Neural embeddings (locally cached)
- **RapidFuzz, Jellyfish** - Fuzzy/phonetic matching
- **Plotly, PyVis** - Visualizations
- **Loguru** - Structured logging
- **Faker** - Synthetic data generation

> ⚠️ First run may take 2-5 minutes to download the embedding model (~400 MB).

### Step 2: Configure Environment

The project includes a `.env` file configured for **demo mode** (in-memory, no PostgreSQL needed):

```bash
# Already configured for demo:
USE_DEMO_STORE=true              # In-memory mode
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384
SEED_RECORDS=2000
THRESHOLD_AUTO_LINK=0.92
THRESHOLD_REVIEW=0.65
```

**For production with PostgreSQL:**

1. Ensure PostgreSQL 14+ with pgvector extension is running
2. Update `.env` with your database credentials
3. Set `USE_DEMO_STORE=false`
4. Run: `python -c "from db import queries; queries.bootstrap()"`

---

## Running the Application

### Option A: Demo Mode (Recommended for first run)

```bash
streamlit run app.py
```

Then open: **http://localhost:8501**

The demo mode creates:

- **2,000 synthetic business records** across 4 departments (GST, LABOUR, FACTORIES, KSPCB)
- **~30% record duplicates** representing the same business in multiple departments
- Realistic Karnataka business names, sectors, PIN codes
- Seeded activity events for vitality analysis

### Option B: Docker (if you want PostgreSQL + Streamlit together)

```bash
docker-compose up -d
```

Access at: **http://localhost:8501**

---

## Application Features

### 📊 Dashboard

- KPI summary: Total UBIDs, Active/Dormant/Closed entities
- Vitality distribution charts
- Entities by sector
- Resolution metrics
- Live audit event stream

### 🔍 Entity Explorer

- Search by business name, PAN, GSTIN, or UBID
- View linked records across departments
- Activity timeline
- Vitality analysis with AI explanations
- Officer overrides for vitality status
- Full audit history for each entity

### 🕸️ Graph Visualizer

- Interactive network of record matches
- Filter by confidence threshold
- Node colors = departments
- Edge colors = match status
- Zoom, pan, click for details

### 🔬 Query Builder

- Pre-built demo queries (e.g., "Dormant factories in 560058 with no inspection in 18 months")
- No SQL required — build queries visually
- CSV/TXT report export

### 📋 Review Queue

- Cases pending human decision
- Side-by-side record comparison
- Confidence scores with explanations
- Merge/Split buttons
- Notes for audit trail

### 📜 Audit Trail

- Immutable append-only log
- All decisions tracked: who, when, what, why
- DPDP Act compliant
- Timeline or table view
- Filterable by event type, actor

### ⬇ Export Center

- Download registry (UBID + linked records)
- Match decisions and review queue
- Audit logs
- Formats: CSV, JSON, Excel, ZIP

### 📤 Upload & Schema Mapping

- Drag-and-drop CSV or JSON
- Auto-detect column mapping
- Manual schema adjustment
- Validates required fields
- Stages records for processing

### ⚙ Processing

- **Normalize**: Converts raw records to standard schema
- **Match**: Finds similar records using:
  - Deterministic matching (PAN, GSTIN perfect matches)
  - Phonetic matching (Double Metaphone for name variations)
  - Fuzzy matching (token sort ratio)
  - Semantic matching (sentence-transformers embeddings)
  - Graph propagation (transitive closure)
- **UBID Assignment**: Creates unified identifiers
- **Vitality Scoring**: Classifies entity status based on events

---

## Workflow Example

### Step 1: Start with Demo Data

1. Open Dashboard — see 2,000 records auto-seeded
2. Observe vitality distribution and resolution metrics

### Step 2: Explore Entities

1. Go to **Entity Explorer**
2. Search for "Reddy" or "Shetty" (common surnames)
3. Click an entity to see:
   - All linked records (same business in different departments)
   - Activity timeline
   - Vitality status (Active/Dormant/Closed)
   - Confidence scores

### Step 3: Run Resolution Pipeline

1. Go to **Processing**
2. Click **"Normalize, Match & Assign UBIDs"**
3. Watch logs for stages:
   - Raw records normalization
   - Phonetic + embedding matching
   - Graph-based clustering
   - UBID creation
   - Vitality classification
4. Check Dashboard for updated counts

### Step 4: Review Borderline Cases

1. Go to **Review Queue**
2. See cases with confidence 65-92%
3. Compare records side-by-side
4. Click **Merge** or **Split**
5. Decision saved to immutable audit trail

### Step 5: Query & Export

1. **Query Builder**: Try demo query "Dormant factories in 560058"
2. **Export Center**: Download results as CSV/JSON/Excel
3. **Audit Trail**: Verify all decisions are logged

---

## Demo Data Schema

### Departments

- **GST**: Goods & Services Tax registration
- **LABOUR**: Labour department licensing
- **FACTORIES**: Factory inspection records
- **KSPCB**: Karnataka State Pollution Control Board

### Vitality Status

- **ACTIVE**: Recent events (inspection, renewal, filing) in last 180 days
- **DORMANT**: Events >180 days old, OR renewals only
- **CLOSED**: Shutdown events recorded
- **UNKNOWN**: No events or insufficient data

### Sectors (14 types)

Textiles, Garments, Chemicals, Pharmaceuticals, Electronics, Auto Components, Food Processing, Plastics, Metal Fabrication, IT Services, Printing, Packaging, Steel Works, Electrical Equipment

### PIN Codes

- **560001** — Bengaluru Central (100 Master Businesses)
- **560058** — Whitefield (Bengaluru Tech Hub)

---

## Architecture

### Data Flow

```
Raw Upload (CSV/JSON)
        ↓
[Ingestion] Parse, validate, stage
        ↓
Normalized Records (standardized schema)
        ↓
[Matching Engine]
  ├─ Blocking (PAN/GSTIN anchors)
  ├─ Phonetic matching (name variations)
  ├─ Fuzzy matching (token similarity)
  ├─ Embedding matching (semantic)
  └─ Graph propagation
        ↓
Match Edges (pairs with confidence scores)
        ↓
[Clustering] Transitive closure → entity groups
        ↓
Entities (UBID + linked records)
        ↓
[Vitality] Score based on events
        ↓
ACTIVE | DORMANT | CLOSED
```

### Module Structure

```
ApexForge/
├── app.py                 # Entry point
├── requirements.txt       # Dependencies
├── .env                   # Configuration (demo mode by default)
│
├── db/
│   ├── connection.py      # PostgreSQL driver (optional)
│   ├── demo_store.py      # In-memory store (default)
│   ├── queries.py         # Query API (routes to demo or PG)
│   └── schema.sql         # Database schema
│
├── ui/
│   └── frontend.py        # All Streamlit pages
│
├── engine/
│   ├── resolver.py        # Matching, clustering, UBID assignment
│   ├── vitality.py        # Status classification, scoring
│   └── explainability.py  # Feature attribution for decisions
│
├── ingestion/
│   └── parser.py          # CSV/JSON upload parsing
│
├── normalization/
│   └── canonical.py       # Record normalization, validation
│
├── validation/
│   └── schema_mapping.py  # Column auto-detection, validation
│
├── models/
│   └── embedding_model.py # Sentence-transformers wrapper
│
└── data/
    └── synthetic_generator.py  # Demo data generation
```

---

## Configuration

### Environment Variables

```bash
# Demo Mode (default)
USE_DEMO_STORE=true

# Embedding Model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384

# Resolution Thresholds
THRESHOLD_AUTO_LINK=0.92    # Confidence for auto-merge (no review)
THRESHOLD_REVIEW=0.65       # Confidence for flagging review

# Synthetic Data (demo mode only)
SEED_RECORDS=2000           # Number of master businesses
SEED_PIN_CODES=560001,560058

# PostgreSQL (production only)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=apexforge
POSTGRES_USER=apexforge_user
POSTGRES_PASSWORD=***
```

---

## Troubleshooting

### Port 8501 Already in Use

```bash
# Use a different port:
streamlit run app.py --server.port 8502
```

### Slow First Load

The embedding model (SentenceTransformer) downloads on first use (~400 MB). Subsequent runs are cached locally.

### Memory Issues

If running on limited RAM, reduce demo data:

```bash
SEED_RECORDS=500 streamlit run app.py
```

### Import Errors

```bash
# Verify all modules are importable:
python -c "import db.queries; import ui.frontend; import engine.resolver; print('OK')"

# If errors, reinstall dependencies:
pip install --upgrade -r requirements.txt
```

### Demo Store Not Seeding

Check `.env` includes `USE_DEMO_STORE=true` and restart app.

---

## Testing

### Unit Tests (Validation)

```bash
python -m py_compile app.py db/queries.py ui/frontend.py engine/resolver.py
```

### Integration Test

```bash
python -c "
from db.demo_store import demo_store
print(f'Entities: {len(demo_store.entities)}')
print(f'Raw Records: {len(demo_store.raw_records)}')
print(f'Activity Events: {len(demo_store.activity_events)}')
"
```

---

## Production Deployment

### With Docker Compose

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f app

# Scale
docker-compose up -d --scale app=3
```

### Kubernetes

Dockerfile includes health checks for k8s deployment.

### Security

- Set `APP_SECRET_KEY` to a random 32+ char string
- Use `APP_ACCESS_CODE` for password protection
- Enable HTTPS in production (Streamlit Cloud, Heroku, etc.)
- Never commit `.env` with real credentials

---

## API Reference

### Core Query Functions

```python
from db import queries

# Bootstrap
queries.bootstrap()          # Initialize demo store or DB
queries.ping()               # Health check

# Records
records = queries.get_all_raw_records(limit=100)
norm = queries.get_normalized_records(limit=100)

# Entities & Resolution
entities = queries.search_entities("Reddy")
ubid = queries.count_entities()
edges = queries.get_all_match_edges()

# Vitality
vitality = queries.get_vitality_signals(ubid_id)
events = queries.get_entity_events(ubid_id)

# Audit
logs = queries.get_audit_trail(limit=50)
queries.log_audit("EVENT_TYPE", "action description", actor="officer1")
```

---

## Support & Contributing

- **Issues**: Check existing GitHub issues
- **Questions**: Review the README.md and DEMO_SCRIPT.md
- **Contributing**: Fork, branch, test, then submit PR

---

## License & Compliance

- **Data**: All demo data is synthetic and non-PII
- **Compliance**: Audit trail supports DPDP Act (India)
- **Open Source**: MIT License (see LICENSE)

---

## Appendix: Example Queries

### Query 1: Dormant Factories (18+ months no inspection)

```
Vitality: DORMANT
Department: FACTORIES
PIN Code: 560058
No Inspection (months): 18
```

### Query 2: All Multi-Department Businesses

```
Vitality: ALL
Sector: (any)
Departments: (any)
```

### Query 3: Active Electronics Businesses

```
Vitality: ACTIVE
Sector: Electronics
PIN Code: (any)
```

Export results, check audit logs for all query executions.

---

**Last Updated**: May 2026
**Version**: 2.0 (Light Mode)

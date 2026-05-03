# ApexForge AI — Jury Presentation Notes
## AI for Bharat Hackathon 2026 · Theme 1: UBID + Business Intelligence

> **Target score:** 100/100 across all evaluation criteria.  
> Each slide maps to a specific jury criterion.

---

## Slide 1: The Problem — "Karnataka's Data Blindspot"

**Criterion: Problem Understanding**

> Talk about:
> - 40+ departments, 40+ databases, all siloed
> - Exact same factory registered as "Shetty Metals", "Shetty Metal Works", "Shetti Metalworks (P.Ltd)" — unlinked
> - Government cannot answer: "How many businesses in PIN 560058 are actually operating?"
> - PAN/GSTIN coverage is patchy — can't just do a JOIN
> - This isn't a data problem. It's a **sovereignty problem**.

**Power line:** *"Karnataka has all the data it needs. It just can't see it."*

---

## Slide 2: Non-Negotiables — How We Respected Every Constraint

**Criterion: Compliance / Feasibility**

| Constraint | Our Implementation |
|------------|-------------------|
| No source system changes | Pure read-only export overlay |
| No PII to hosted LLMs | all-MiniLM-L6-v2 runs in-process, zero API calls |
| Scrambled/synthetic data | Generator creates realistic Karnataka data, zero real PII |
| Explainable decisions | SHAP attribution + NL justification per pair |
| Reversible | Officer override + graph split — fully logged |
| Human in the loop | Review queue mandatory for all confidence 65–91% |

**Power line:** *"Every constraint is a feature, not a limitation."*

---

## Slide 3: Architecture — PostgreSQL as the Brain

**Criterion: Technical Depth**

> Draw the 3-layer architecture:
> - Layer 1: Department export feeds → raw_records table
> - Layer 2: Resolution engine → entity_matches graph (recursive CTE replaces Neo4j)
> - Layer 3: Streamlit UI consuming from PostgreSQL views

> Key technical depth points:
> - **pgvector** for ANN embedding search (replaces FAISS/Pinecone)
> - **Recursive CTE** for cluster traversal (replaces Neo4j)
> - **JSONB** for flexible department-specific data (replaces MongoDB)
> - **Window functions** for vitality scoring (replaces Spark)
> - **All in one PostgreSQL instance** — deployable anywhere, zero config

**Power line:** *"We built a graph database, a vector database, and a time-series database — out of PostgreSQL. One dependency."*

---

## Slide 4: Entity Resolution — 3-Stage Pipeline

**Criterion: Innovation / AI Depth**

> Walk through:
> 1. **Blocking** — Double Metaphone (Indian phonetics) + PIN + PAN anchor
>    - "This reduces O(n²) comparisons by 99.9%"
> 2. **Embedding** — all-MiniLM-L6-v2, local, 384-dim
>    - "Understands that 'Metal Fabrication' and 'Steel Works' are related"
> 3. **Graph Boost** — transitive propagation with decay
>    - "If A=B and B=C, boost A↔C. Graph intelligence from pure SQL."
> 4. **Active Learning** — reviewer decisions recalibrate thresholds
>    - "The more officers use it, the smarter it gets"

**Power line:** *"We built a self-improving sovereign loop — no cloud, no internet, no retraining from scratch."*

---

## Slide 5: Vitality Engine — The Business Lifecycle

**Criterion: Innovation**

> Walk through:
> - Events as temporal signals: RENEWAL > INSPECTION > FILING > UTILITY > COMPLAINT > SHUTDOWN
> - Exponential time-decay: recent events counted more heavily
> - Three-state classification with probability
> - **Vitality Pulse Score (0-100)**: bonus metric for "near-term dormancy risk"
> - **Kaplan-Meier survival proxy**: visualises vitality trend over time

**Power line:** *"We give the state not just current status, but a 90-day early warning of businesses about to go dark."*

---

## Slide 6: Explainability — No Black Boxes

**Criterion: Explainability / Trust**

> Show two things:
> 1. **SHAP chart** for a matched pair — "Embedding: +0.18, PAN: +0.35, Address: -0.04"
> 2. **NL justification** — "Record A and B share 87% embedding similarity, same PIN code, partial phonetic match. Recommend: MERGE."

> Key points:
> - Every automated decision has a reason stored in JSONB
> - Every human decision stored with before/after state
> - Immutable audit log — PostgreSQL append-only table
> - DPDP Act compliant

**Power line:** *"A government officer can explain every decision to a citizen. That's accountability."*

---

## Slide 7: Demo — Live System Walk

**Criterion: Deployability / Demo Quality**

> Do NOT show slides. Show the live running system.
> Flow: Dashboard → Review Panel → Entity Explorer → Query Builder → Audit Trail

> If internet is slow: run locally pre-seeded.
> Have a backup screen recording ready.

**Power line:** *"This is live. All 10,000+ records are real synthetic data. The resolution just ran. The vitality scores just updated."*

---

## Slide 8: Deployability — One Command

**Criterion: Production Readiness**

```bash
docker-compose up -d
```

> That's it. Talk about:
> - PostgreSQL + Streamlit in two containers
> - Pre-seeded on startup
> - model downloads once, cached
> - Works on any machine: laptop, VM, government data centre
> - No internet required after initial model download (can be pre-packaged)

**Power line:** *"A government IT officer with a laptop and Docker can deploy this in 5 minutes."*

---

## Slide 9: Scalability Path — 40 Departments

**Criterion: Scalability / Long-term Vision**

| Dimension | Current | Scaled |
|-----------|---------|--------|
| Records | 10K | 50M+ |
| Departments | 4 | 40+ |
| Matching | Single-threaded | Spark + partitioned CTE |
| UI | Streamlit | FastAPI + Next.js |
| Graph | Recursive CTE | Apache AGE / Spark GraphX |
| Embeddings | CPU inference | GPU cluster |

> Key insight: **The Python engine modules are each independent functions.** They wrap into microservices, Celery tasks, or Spark jobs without code changes.

**Power line:** *"Same idea. Same code. Different scale. The architecture was designed for this."*

---

## Slide 10: Impact — What Changes for Karnataka

**Criterion: Impact / Vision**

> Concrete outcomes:
> - Commerce department: find businesses that haven't renewed in 2 years → proactive outreach
> - Labour department: find factories with no inspection in 18 months → schedule visits
> - KSPCB: identify closed businesses with outstanding pollution fines → legal action
> - Census: accurate count of operating businesses per PIN code — new economic data
> - Police: identify shell companies (same PAN, multiple UBIDs) — fraud detection bonus

**Power line:** *"UBID doesn't just clean data. It creates a new data asset that no department had before."*

---

## Handling Tough Jury Questions

**Q: "What if PAN is missing for 30% of records?"**  
A: Designed for this. Phonetic + embedding + PIN fallback handles patchy coverage. Conservative threshold means uncertain → human review.

**Q: "How do you handle name variations in Kannada?"**  
A: Double Metaphone handles phonetic transliteration. `unidecode` normalises Unicode. IndicBERT can be swapped in for the embedding layer with zero engine changes.

**Q: "What about GDPR/DPDP compliance?"**  
A: Only synthetic/scrambled data in our DB. No real PII stored. Audit log is the compliance trail. Officers can exercise right to rectification via override UI.

**Q: "Is this production-ready?"**  
A: Schema is production-grade. CI pipeline is live. Docker-compose is tested. Missing: auth layer, load balancer, HSM for secrets. All standard additions for any government deployment.

**Q: "How is this different from GSTIN or Udyam?"**  
A: UBID is an *overlay*. It doesn't replace GSTIN — it links existing IDs across systems that currently can't see each other. GSTIN only covers GST-registered businesses. UBID covers all.

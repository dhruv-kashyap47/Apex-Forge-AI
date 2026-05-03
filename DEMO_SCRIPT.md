# ApexForge AI — 5-Minute Video Walkthrough Script

> **Total time: 5:00 min**  
> Narrator speaks clearly. Screen recordings needed for each section.

---

## [0:00–0:30] HOOK — The Problem, Visualised

**Visual:** Split-screen showing 4 tabs — GST portal, Labour dept, Factories dept, KSPCB.
All have the same factory: "Shetty Metal Works", "Shetty Metals Pvt Ltd", "Shetty Metalworks (P.Ltd)".

**Narration:**
> "Right now, Karnataka has 40+ government department systems — each with its own database.
> The same business appears in GST, Labour, Factories, and KSPCB — but as four completely 
> different records. No single official knows this is the same factory. 
> The state cannot answer: 'Which businesses are actually operating today?'
> ApexForge AI fixes this — without touching a single source system."

---

## [0:30–1:30] THE PIPELINE — Entity Resolution Live

**Visual:** Admin panel → Click "Run Resolution Pipeline" → Progress logs appear.
Show the terminal output with: `Records: 8,421 → Pairs: 3,204 → Auto-linked: 891 → Review: 312`.

**Narration:**
> "ApexForge's resolution engine runs in three stages.
> Stage One: Blocking. We use PAN and GSTIN as perfect anchors, then Double Metaphone 
> phonetic keys for name variation — because 'Shetty Metal Works' and 'Shetti Metals' 
> sound identical in Kannada.
> Stage Two: Our embedding model runs locally — that's sentence-transformers, no API calls,
> no PII ever leaving the system — computes a semantic fingerprint for each record.
> Stage Three: Graph propagation. If we know A=B and B=C, we boost the confidence for A=C.
> Result: 891 auto-linked. 312 sent to human review. Everything below 65% — kept separate."

---

## [1:30–2:30] THE REVIEW PANEL — Human in the Loop

**Visual:** Open Review Panel. Show side-by-side record comparison. 
Highlight the SHAP chart. Click MERGE. Show the audit log entry appear.

**Narration:**
> "Every borderline match goes to a human reviewer — this is non-negotiable.
> The officer sees both records side by side. On the right: a SHAP feature attribution chart
> showing exactly why the system thinks these are the same entity.
> 'Embedding similarity: 87%. Same PIN code. Phonetic match. But PAN is missing.'
> The AI says: REVIEW. The officer says: [click] MERGE.
> That decision is stored instantly in our immutable audit log — 
> who, when, why, before-state, after-state. Fully reversible."

---

## [2:30–3:30] VITALITY INTELLIGENCE — Active / Dormant / Closed

**Visual:** Entity Explorer → Search "Shetty Meta" → Click on entity → 
Show activity timeline → Show Kaplan-Meier curve → Show Pulse Score ring.

**Narration:**
> "Once we have the UBID, we run vitality analysis.
> Every timestamped event — GST filing, labour inspection, pollution consent renewal — 
> feeds into our temporal model. Events decay exponentially: last week's inspection 
> counts more than a renewal from two years ago.
> This entity has: 3 renewals in 12 months, last inspection 41 days ago, KSPCB consent valid.
> Verdict: ACTIVE. Pulse Score: 78 out of 100.
> The AI explains: 'Recent renewal + active inspections = strong operational signals.'
> An officer can override this with one click — and the system learns from that override."

---

## [3:30–4:15] POWER QUERY — Dormant Factories, Bangalore

**Visual:** Query Builder → Click demo query "Dormant factories in 560058 with no inspection in 18 months"
→ 47 results appear in <1 second → Show pulse score distribution chart.
→ Download CSV.

**Narration:**
> "Here's the query that wins the evaluation.
> [Click] 'Show dormant factories in Whitefield with no government inspection in 18 months.'
> 47 entities. Instantly. Sorted by Pulse Score ascending — lowest vitality first.
> These are the businesses the Commerce Department needs to visit.
> The query translates to plain SQL using recursive CTEs and window functions — 
> all inside PostgreSQL, no external dependencies.
> Download as CSV, or use the SQL directly in any government BI tool."

---

## [4:15–4:45] GRAPH — The UBID Cluster Network

**Visual:** Graph View → Show colour-coded nodes (GST=blue, Labour=purple, Factories=pink, KSPCB=green)
→ Zoom into one cluster with 4 nodes from different departments linked together.

**Narration:**
> "This is the UBID graph. Each node is a department record. Each edge is a resolved match.
> Blue = GST. Purple = Labour. Pink = Factories. Green = KSPCB.
> This cluster here — four nodes, four departments, one business.
> Before ApexForge: four records, zero connection. 
> After ApexForge: one UBID, full 360° view."

---

## [4:45–5:00] CLOSE — Sovereign, Scalable, Deployable

**Visual:** Show architecture diagram. Final frame: ApexForge AI logo + stats card.

**Narration:**
> "ApexForge AI runs fully on-premise. PostgreSQL + Python. No Neo4j, no cloud LLMs, 
> no vendor lock-in. One docker-compose up and it's live.
> It scales: from 2 PIN codes today to all 40+ departments tomorrow.
> The idea stays exactly the same. The engine stays sovereign.
> Karnataka's businesses — finally, a single source of truth."

---

## Key Screenshots to Capture

1. **Dashboard** — all KPI cards populated, vitality donut, sector bar
2. **Review Panel** — side-by-side records with SHAP chart + AI verdict banner
3. **Entity Explorer** — expanded entity with activity timeline + Pulse Score ring
4. **Graph View** — colourful cluster network with 200+ nodes
5. **Query Builder** — demo query result table with confidence scores
6. **Audit Trail** — full timeline of events including reviewer decisions

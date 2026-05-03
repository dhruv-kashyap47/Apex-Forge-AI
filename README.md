# ApexForge AI

ApexForge AI is a Streamlit application that shows how different government and business records can be linked into one view.

It takes records that look slightly different in different departments and helps answer questions like:

- Is this the same business across multiple departments?
- Is the business active, dormant, or closed?
- What evidence supports that decision?
- What did the system do, and what did a human reviewer do?

This project is designed to be easy to explain in a demo and easy to follow for a non-technical person.

## What Problem This Solves

In many real systems, the same business can appear under slightly different names in different departments.

For example:

- `Shri Reddy Industries`
- `Reddy Inds`
- `Sri Reddy Industries Pvt Ltd`

To a human, these may clearly be the same business.
To a computer, they may look like three separate records.

That creates problems:

- Duplicate records
- Wrong counts
- Confusing reports
- Hard-to-trace decision making
- Slow manual reviews

ApexForge AI solves this by:

- grouping similar records
- assigning a Unified Business Identifier
- showing the reason behind each match
- letting humans confirm or reject uncertain cases
- keeping a full audit trail

## What The Solution Does

The app has seven main views:

- Dashboard
- Entity Explorer
- Review Panel
- Graph View
- Query Builder
- Audit Trail
- Admin / Controls

Each view is explained below in simple language.

## Quick Start

If you just want to open the app on your machine:

```bash
streamlit run app.py
```

That is enough for the built-in demo mode.

## Step By Step: How To Use It

### 1. Open the app

Run:

```bash
streamlit run app.py
```

Then open the local URL shown in the terminal, usually:

- `http://localhost:8501`

If you are using Docker, see the deployment section below.

### 2. Dashboard

The Dashboard is the home screen.

What you see:

- total businesses
- active businesses
- dormant businesses
- closed businesses
- pending reviews
- record distribution charts
- latest audit events

How to read it:

- Green usually means active or healthy
- Amber usually means attention needed
- Red usually means closed or risky

What to say in a demo:

> "This screen gives a quick summary of the entire system in one place."

### 3. Entity Explorer

Use this when you want to look at one business in detail.

You can search by:

- business name
- PAN
- GSTIN
- UBID
- PIN code

What it shows:

- the linked records
- the business vitality status
- the pulse score
- the activity timeline
- the explanation of why the system classified it that way

What to say in a demo:

> "This page lets a reviewer inspect one business from all angles."

### 4. Review Panel

This is the human review screen.

Use it when the system is not fully sure about a match.

What it shows:

- two records side by side
- AI explanation
- confidence score
- signal breakdown
- SHAP-style feature contribution
- merge or split decision buttons

How to use it:

1. Read the AI explanation
2. Compare the two records
3. Decide whether they are the same business
4. Click `MERGE` or `SPLIT`
5. Add a short note if needed

What to say in a demo:

> "The system suggests, but the human decides."

### 5. Graph View

The Graph View shows how records are connected.

What it shows:

- nodes = records
- edges = possible matches
- edge color = match status

This is useful when you want to understand clusters and relationships.

What to say in a demo:

> "This is the network view of business identity resolution."

### 6. Query Builder

This page is for people who want to ask structured questions without writing SQL.

Example questions:

- dormant factories in a PIN code
- active businesses in a sector
- closed businesses
- businesses with no inspection in many months

How to use it:

1. Choose the filters
2. Preview the generated query
3. Click `RUN QUERY`
4. Download results if needed

What to say in a demo:

> "This is a guided search screen for non-technical users."

### 7. Audit Trail

This page shows every important action in the system.

It records things like:

- entity creation
- vitality updates
- resolution runs
- reviewer decisions
- query executions
- threshold changes

Why it matters:

- it makes the system explainable
- it helps with compliance
- it lets you trace what happened and when

What to say in a demo:

> "Nothing happens silently. Every important action is logged."

### 8. Admin / Controls

This page is for advanced operations.

You can:

- run entity resolution
- run vitality classification
- inspect threshold settings
- check database health

If you are not technical, you usually do not need this page unless you are demonstrating the system end to end.

## Modes Of Use

### Demo Mode

Demo mode uses the built-in in-memory dataset.

This is the easiest way to run the app:

```bash
streamlit run app.py
```

Use this when:

- you want a quick demo
- you do not want to set up a database
- you want to show the UI immediately

### Docker Deployment

Docker is the best way to deploy the app in a controlled environment.

Before you start:

1. Copy `.env.example` to `.env`
2. Replace the placeholder secrets
3. Review the security settings

Then run:

```bash
docker compose up -d --build
```

Open:

- `http://localhost:8501`

## Security Checklist

Before deploying anywhere outside your laptop, make sure:

- `APP_ENV=production`
- `APP_SECRET_KEY` is long and random
- `POSTGRES_PASSWORD` is long and random
- `APP_ACCESS_CODE` is set if you want a basic unlock gate
- you are not exposing PostgreSQL to the public internet
- you are not using placeholder credentials

The app now performs runtime security checks at startup and will warn you about risky settings.

## Deployment Notes

This repository is set up to be safe by default:

- Streamlit CORS/XSRF settings are compatible
- the container runs as a non-root user
- PostgreSQL is not published to the host in the Docker compose file
- dynamic text from records is escaped before being rendered as HTML

That reduces the chance of:

- accidental secret leakage
- basic cross-site scripting issues
- insecure container defaults

## Files In The Project

- `app.py` - main Streamlit entry point
- `security.py` - runtime security checks and optional access gate
- `db/` - data access layer and demo store
- `engine/` - resolution and vitality logic
- `ui/` - all Streamlit pages
- `data/synthetic_generator.py` - synthetic data generator
- `Dockerfile` - container build instructions
- `docker-compose.yml` - local deployment setup

## Troubleshooting

### The app does not start

Check:

- you are running `streamlit run app.py`
- Python is installed
- you are inside the project folder

### The app opens but shows no data

Try:

- refreshing the browser
- checking the sidebar for security warnings
- confirming you are in demo mode

### The app asks for an access code

That means `APP_ACCESS_CODE` is set.

Enter the unlock code you configured in `.env`.

### Docker build fails

Check:

- `.env` exists
- all placeholders have been replaced
- Docker Desktop is running

## Non-Technical Demo Script

If you need to explain the app to someone with no technical background, use this flow:

1. Start on the Dashboard and explain it is the summary page.
2. Open Entity Explorer and show one business in detail.
3. Open Review Panel and show how a human confirms or rejects a match.
4. Open Graph View and show how records connect together.
5. Open Query Builder and show how a simple business question can be answered.
6. Open Audit Trail and show that every action is recorded.
7. Open Admin / Controls and explain that advanced operations live there.

Short explanation:

> "The app helps government-style records behave like one trusted system without losing traceability."

## Important Limitations

This repository ships with a demo-first setup.

That means:

- the data is synthetic or in-memory demo data
- the current app is optimized for demonstration and review
- production integration with a real database should be configured separately

## If You Want The Short Version

Run this:

```bash
streamlit run app.py
```

Then open the app and use the pages in this order:

1. Dashboard
2. Entity Explorer
3. Review Panel
4. Graph View
5. Query Builder
6. Audit Trail
7. Admin / Controls

That is enough to show the whole story end to end.


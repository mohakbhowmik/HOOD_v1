# HOOD — Current Development State

Last updated: 2026-08-14

## Current Objective

Build HOOD into a working business opportunity discovery and prospecting engine.

Immediate priority:

Complete the pipeline from business discovery through deterministic extraction, then connect downstream AI analysis and scoring through n8n.

---

## Pipeline Status

### 1. Target / Query Generation

Status: WORKING

The system can generate discovery queries for a target market.

### 2. Google Places Discovery

Status: WORKING

Google Places API (New) is connected.

Recent test:

* 2 queries
* 40 raw candidates
* 22 unique businesses after domain deduplication

### 3. Business / Domain Deduplication

Status: WORKING

Businesses are deduplicated using domain/business identity logic.

### 4. Website Crawler V0

Status: WORKING

Recent real test:

* 16 successful
* 2 retryable failures
* 4 permanent failures

The crawler successfully retrieved multiple pages from many businesses.

Raw page text is persisted to PostgreSQL.

### 5. PostgreSQL

Status: WORKING

Docker PostgreSQL is running.

pgAdmin is connected successfully.

Current relevant tables:

* businesses
* candidates
* extracted_data
* pages

### 6. Extractor V1

Status: WORKING

Extractor V1 has been implemented and tested.

Recent extraction run:

* 18 crawled businesses processed
* 15 phones found
* 9 emails found
* 18 page titles found
* 14 descriptions found

Coverage:

* Phone: 83.3%
* Email: 50.0%
* Page title: 100%
* Description: 77.8%

The extractor is deterministic.

It extracts:

* phone
* email
* page_title
* description

The extractor uses saved crawled pages.

### 7. AI Opportunity Analysis

Status: NOT STARTED

This is the next major intelligence stage.

It should eventually use Gemini/Google AI through n8n.

Its job is to analyze extracted business/web information and identify commercially useful opportunities.

Do not add AI analysis to the Python extractor.

### 8. Prospect Scoring

Status: NOT STARTED

Scoring comes after AI opportunity analysis.

Do not build an elaborate scoring system before real AI analysis results exist.

### 9. Prospect Export / Google Sheets

Status: NOT STARTED

Likely downstream output through n8n.

Google Sheets should be treated as a convenient operational/sales layer rather than the primary database.

### 10. Outreach

Status: NOT STARTED

Eventually support targeted, evidence-based outreach.

Do not build high-volume outreach before prospect qualification is working.

---

## Current Architecture

Current conceptual architecture:

Target
→ Google Places discovery
→ deduplication
→ website crawler
→ PostgreSQL pages
→ deterministic extraction
→ AI analysis
→ scoring
→ prospect output
→ outreach

n8n will eventually orchestrate downstream AI analysis, scoring, exports, and outreach.

---

## Current Repository Structure

Expected structure:

HOOD/
├── .gitignore
├── .env
├── .env.example
├── docker-compose.yml
├── requirements.txt
├── run_discovery.py
├── run_crawl.py
├── run_extract.py
├── targets/
└── core/
├── config.py
├── db.py
├── discovery.py
├── crawler.py
├── extractor.py
└── urls.py

The exact repository structure should always be inspected before assuming additional files exist.

---

## Git Status

Git repository initialized.

GitHub repository connected.

Main branch is being used.

The project has been pushed to GitHub.

`.gitignore` is now a real file.

Ignored:

.env
**pycache**/
*.py[cod]

Do not commit secrets.

---

## Known Current Data Quality Observation

Some extracted email values may contain Markdown/mailto formatting, for example:

[sacosta@onesothebysrealty.com](mailto:sacosta@onesothebysrealty.com)

This is not currently considered a reason to redesign the extractor.

The preferred future approach is to perform downstream normalization in the n8n/AI workflow where appropriate, while keeping Python extraction deterministic and simple.

Before changing the extractor, inspect actual failure patterns and determine whether a code-level fix is justified.

---

## Immediate Next Milestone

Connect HOOD's existing PostgreSQL data to n8n.

Then build the first downstream AI analysis workflow:

PostgreSQL
→ n8n
→ normalize extracted data
→ Gemini/Google AI analysis
→ structured opportunity assessment
→ scoring
→ Google Sheets

The first AI workflow should be tested on a small number of real businesses before scaling.

---

## Do Not Do Yet

Do not:

* redesign Google Places discovery
* rewrite the crawler
* turn the extractor into an AI system
* build complex scoring before testing AI analysis
* build a SaaS dashboard
* build a complicated CRM
* build massive outreach infrastructure
* optimize for hypothetical scale before the MVP produces useful prospects
* rewrite working modules unnecessarily

---

## Success Criteria For The Next Stage

The next stage is successful when HOOD can take a real discovered business and produce something similar to:

Business
→ website evidence
→ cleaned contact information
→ business understanding
→ identified opportunity
→ opportunity reasoning
→ commercial score
→ structured prospect record

That output should be good enough to support a real sales conversation.

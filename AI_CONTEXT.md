# HOOD — AI Engineering Context

## 1. Project Identity

HOOD is a high-volume business opportunity discovery platform.

Its purpose is to discover businesses in a target market, collect and crawl their public web presence, extract useful information, analyze those businesses for commercial opportunities, score prospects, and eventually support targeted high-volume outreach.

HOOD may eventually become a SaaS product, but the current priority is proving the system and generating business value before building unnecessary SaaS infrastructure.

---

## 2. Core Business Goal

The ultimate goal is not simply to scrape businesses.

The goal is:

1. Find businesses that fit a target market.
2. Understand their online presence.
3. Identify problems or opportunities that can be solved through automation, websites, AI, lead generation, WhatsApp systems, or related services.
4. Prioritize the businesses with the strongest opportunities.
5. Produce actionable prospects.
6. Enable targeted outreach.
7. Convert prospects into paying automation/service clients.
8. Eventually turn the system into a scalable SaaS/platform if the business model proves itself.

HOOD is therefore a prospect intelligence and acquisition engine, not merely a web scraper.

---

## 3. Current Pipeline

The intended pipeline is:

Target
→ Google Places discovery
→ Business deduplication
→ Website crawler
→ Raw website pages/text
→ Deterministic extraction
→ AI opportunity analysis
→ Scoring
→ Prospect database/export
→ Outreach

The current implementation is progressing through this pipeline incrementally.

---

## 4. Architecture Philosophy

Keep the architecture simple, modular, and understandable.

Priorities:

1. Get the MVP working.
2. Keep the architecture clean enough to scale.
3. Learn deeper engineering concepts while building.
4. Avoid unnecessary overengineering.
5. Prefer simple deterministic solutions where intelligence is not required.
6. Use AI where judgment, classification, reasoning, or opportunity analysis is genuinely useful.
7. Do not redesign working systems without a concrete reason.

The project is being built iteratively.

Do not restart the architecture merely because a different architecture could theoretically be better.

---

## 5. Current Technology

Current core stack:

* Python
* PostgreSQL
* Docker
* pgAdmin
* Google Places API (New)
* Website crawling
* Git/GitHub

n8n will later act as an orchestration/automation layer.

Google Gemini will eventually be used for AI analysis and potentially data-cleaning/normalization tasks.

Google Sheets may be used as a convenient sales/prospect output layer.

PostgreSQL remains the core system of record.

---

## 6. Discovery

Google Places API is currently used to discover businesses.

Discovery performs:

* target/query generation
* Google Places searches
* candidate collection
* business/domain deduplication
* PostgreSQL persistence

The discovery architecture is already working.

Do not redesign discovery unless there is a concrete bug or scaling requirement.

---

## 7. Crawler

The crawler retrieves public business websites.

Crawler V0:

* receives discovered businesses
* attempts to identify/crawl their websites
* retrieves multiple pages
* removes scripts/styles and extracts visible text
* persists crawled pages to PostgreSQL

The crawler should remain focused on collection.

Do not turn the crawler into an AI analysis engine.

The crawler should collect raw evidence; later stages decide what that evidence means.

---

## 8. Extraction

Extractor V1 is deterministic and intentionally cheap.

Current fields:

* phone
* email
* page_title
* description

Phone:

* deterministic regex over flattened page text.

Email:

* deterministic regex over flattened page text.
* obvious junk should be filtered.

Page title:

* captured from the HTML `<title>` tag during crawling.

Description:

* captured from `<meta name="description">`
* fallback to `og:description`

The crawler must preserve title/meta information because those fields are lost if HTML is flattened without capturing them first.

Extractor V1 must not use an LLM.

Extractor V1 must not perform opportunity scoring.

Extractor V1 must not perform AI business analysis.

---

## 9. Multi-page Extraction

Businesses may have multiple saved pages.

Extraction should process pages in deterministic priority order.

Homepage should have highest priority.

If a required field is not found on the homepage, extraction may continue through other saved pages.

The same deterministic ordering should produce consistent results on repeated runs.

Do not unnecessarily add source-page columns for every extracted field unless later evidence shows that this is required.

---

## 10. Extracted Data Semantics

`extracted_data` represents current state.

There should be one logical extracted-data record per business.

Extraction should therefore be safely rerunnable.

Repeated extraction should update the existing business's extracted data rather than create an unlimited history of stale extraction rows.

Use an upsert/current-state model.

---

## 11. AI Analysis Stage

AI analysis happens after deterministic extraction.

The AI stage is responsible for judgment and interpretation.

Examples:

* identifying business type
* understanding the business model
* identifying operational/marketing/lead-generation opportunities
* identifying potential automation opportunities
* interpreting website quality and conversion weaknesses
* determining which services could realistically be pitched
* generating an opportunity explanation
* producing structured reasoning for prospect scoring

AI should analyze evidence collected by the earlier pipeline stages.

Do not use AI simply for tasks that deterministic code can perform reliably and cheaply.

---

## 12. Scoring

Scoring happens after AI analysis.

The purpose of scoring is to prioritize prospects.

A score should represent commercial opportunity rather than arbitrary website quality.

Potential factors may include:

* business fit
* evidence of a problem
* automation potential
* likely value of solving the problem
* ease of implementation
* contactability
* strength of available evidence

The exact scoring model is not permanently frozen yet.

Do not invent a complex scoring framework before the AI analysis stage has produced real data.

---

## 13. n8n's Role

n8n will eventually orchestrate downstream workflows.

Likely flow:

PostgreSQL
→ n8n
→ data normalization
→ Gemini/Google AI
→ opportunity analysis
→ scoring
→ structured prospect record
→ Google Sheets / CRM
→ outreach

n8n should orchestrate services rather than replace HOOD's core database or discovery/crawling architecture.

PostgreSQL remains the source of truth.

Google Sheets is an output/workflow surface, not the primary database.

---

## 14. Outreach Philosophy

The eventual system should support high-volume targeted outreach.

However:

* quality matters more than raw volume
* prospects should be relevant to the offer
* outreach should be based on evidence discovered by HOOD
* avoid generic spam
* avoid sending outreach blindly to every discovered business
* scoring and qualification should happen before large-scale outreach

The system should eventually allow targeted campaigns by niche, opportunity type, geography, and other relevant criteria.

---

## 15. Important Separation of Responsibilities

Discovery collects businesses.

Crawler collects web evidence.

Extractor performs deterministic structured extraction.

AI analyzes and interprets evidence.

Scoring prioritizes prospects.

n8n orchestrates downstream automation.

Google Sheets/CRM exposes useful prospect information.

Outreach converts qualified prospects into conversations.

Do not collapse all of these responsibilities into one giant script.

---

## 16. Development Rules

When working on HOOD:

1. Understand the existing implementation before changing it.
2. Do not assume a file or function exists without checking.
3. Do not redesign working architecture unnecessarily.
4. Do not introduce frameworks just because they are popular.
5. Prefer minimal changes.
6. Preserve working behavior.
7. Explain the reason for a change before implementing it when the change affects architecture.
8. Keep MVP implementation practical.
9. Test changes against real data whenever possible.
10. Do not prematurely optimize.
11. Do not add AI where deterministic logic is sufficient.
12. Do not add complexity merely to handle hypothetical edge cases.
13. Use real failure data to justify improvements.

---

## 17. Security

Secrets must never be committed to GitHub.

`.env` must remain ignored.

API keys should be stored in environment variables or an appropriate secret-management system.

The Google Places API key that was previously exposed should be considered compromised and must eventually be rotated/restricted.

Never print or expose API keys in source code, Git commits, documentation, screenshots, or AI prompts.

---

## 18. Current Business Strategy

The immediate commercial objective is to use HOOD to find prospects for automation/service work.

The system does not need to become a SaaS product before it generates revenue.

The preferred progression is:

HOOD MVP
→ generate qualified prospects
→ contact businesses
→ close automation projects
→ learn from real sales data
→ improve qualification
→ increase prospect volume
→ automate more of the process
→ consider SaaS/productization later

The system should therefore optimize for useful business output, not technical complexity.

---

## 19. AI Assistant Behavior

Any AI assisting with HOOD must:

* maintain awareness of the complete pipeline
* respect the existing architecture
* inspect existing code before proposing changes
* explain unfamiliar concepts simply when needed
* distinguish confirmed facts from assumptions
* explicitly say when information is unknown
* avoid inventing repository structure
* avoid unnecessary rewrites
* avoid starting unrelated improvements
* work incrementally
* prioritize the current milestone
* preserve existing functionality

When asked to implement something, make the smallest sensible change that satisfies the requirement.

When asked for guidance, explain what to do and why without turning every answer into a programming lecture.

---

## 20. Current Development Principle

The project is being built as a real MVP.

The question for every feature should be:

"Does this help HOOD reliably discover, understand, qualify, or convert businesses?"

If not, it probably does not belong in the current milestone.

# URL Summarizer

A Python tool that reads a list of URLs, fetches each article, extracts the main text, runs a keyword pass, sends the cleaned text to an LLM for structured analysis, and writes the results to an Excel spreadsheet.

Built at the California Air Resources Board (CARB) to track zero-emission transportation projects across Rail, Trucks, Ports/Marine, Aviation, Infrastructure, and Buses/Transit.

## What it produces

Each row in `article_summaries.xlsx` contains:

- `URL` — original source link
- `Status` — Success / Failed to fetch / Failed to extract / Error
- `Timeline_Flag` — flags stale, completed, or cancelled projects
- `Primary_Category` — Rail / Trucks / Ports/Marine / Aviation / Infrastructure / Buses/Transit / Other
- `Subcategory` — finer-grained classification depending on the primary category
- `Project_Stage` — Announced / In Development / Pilot/Trial / Operational / Completed / Cancelled
- `Article_Date` — publication date if found
- `Summary` — 6–10 sentence detailed summary preserving technical specs, funding, timelines, and companies
- `Companies_Mentioned` — every organization referenced
- `Project_Dates` — every milestone date with type and description

## Setup

### 1. Install dependencies

```
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy the template:

```
copy .env.example .env
```

Open `.env` in a text editor and fill in your API keys.

**For CARB users (recommended):** use the Poppy backend by filling in `POPPY_API_KEY`, `POPPY_BASE_URL`, and `POPPY_MODEL`. This requires the state network (on-site or VPN). Generate your Poppy key at Settings → Account → API keys inside Poppy.

**For development without network access:** leave `POPPY_BASE_URL` empty and fill in `OPENAI_API_KEY` to use OpenAI directly as a fallback.

### 3. Add URLs

Put one URL per line in `urls.txt`. Lines starting with `#` are treated as comments and skipped.

## Running

Process every URL in `urls.txt`:

```
python main.py
```

Process only the first N URLs (useful for testing):

```
python main.py --limit 5
```

The startup banner will print which backend is active:

```
✓ API client ready — using Poppy (https://customeruat.sda.state.ca.gov/api)
✓ Model: Azure gpt-4.1
```

If you see `using OpenAI (default)` instead, your `.env` doesn't have `POPPY_BASE_URL` set.

## File layout

- `main.py` — main script and `URLSummarizer` class
- `keywords.json` — keyword lists organized by category, injected into the LLM prompt as focus context
- `urls.txt` — input URLs, one per line
- `article_summaries.xlsx` — output spreadsheet (created/appended on each run)
- `.env` — local environment variables (gitignored)
- `.env.example` — template for `.env`

## How summaries are generated

1. **SafeLinks unwrap** — strips Outlook SafeLinks and Menlo Security wrappers off the URL.
2. **Fetch** — uses `cloudscraper` posing as Chrome to bypass basic anti-bot checks.
3. **Extract text** — `trafilatura` first, BeautifulSoup as fallback. Strips navigation, ads, comments.
4. **Keyword detection** — local string matching against `keywords.json` to flag topics, companies, and technical terms.
5. **LLM analysis** — sends the cleaned text plus detected keywords to the configured model with a strict JSON response schema. Temperature 0.2 for consistency.
6. **Format and save** — flattens the JSON into spreadsheet rows, deduplicates by URL, appends to Excel.

## Adjusting categories or subcategories

Edit the prompt in `analyze_with_ai` inside `main.py`. The primary category list and subcategory options are defined there. Reordering or renaming a category in the prompt is enough — the rest of the code consumes whatever the model returns as a free-form string.

## Adjusting keywords

Edit `keywords.json`. The top-level keys are category names; each value is a list of keywords or phrases to match (case-insensitive substring match). Adding a new category requires no code changes — every category in the JSON automatically gets injected into the prompt context if any keywords match in an article.

## Troubleshooting

**401 Unauthorized** — API key is wrong or expired. Regenerate and update `.env`.

**404 Not Found** — `POPPY_BASE_URL` is wrong. Must be exactly `https://customeruat.sda.state.ca.gov/api` (no trailing `/v1` or `/`).

**Connection timeout** — Poppy endpoint is on the state network. You need to be on-site at CARB or connected to the state VPN. Alternatively, comment out `POPPY_BASE_URL` in `.env` to fall back to OpenAI.

**`model not found`** — `POPPY_MODEL` doesn't match what Poppy exposes. Run `curl -X GET "https://customeruat.sda.state.ca.gov/api/models" -H "Authorization: Bearer YOUR_KEY"` to list available models, and copy the exact `id` string into `.env`.

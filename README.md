# Multi-Platform Content Distribution Pipeline

An end-to-end automation pipeline covering the full content workflow — **topic selection → writing → review → typesetting → distribution → link collection** — across multiple publishing platforms. Write once, distribute everywhere.

Ships with adapters for WeChat Official Account, Toutiao, Baijiahao, Zhihu and CSDN; extensible to other platforms via the same adapter pattern.

The project is organized in two layers:

- **Python scripts** — deterministic computation and browser operations (topic drawing, scoring, rendering, CDP scraping)
- **AI Agent Skills** (`.reasonix/skills/`) — orchestration layer that chains the scripts into a one-command pipeline

---

## Pipeline Overview

| # | Stage | What it does | Code |
|---|-------|--------------|------|
| 1 | Topic selection | Draws topics by group (keeps posts varied); skips used topics; tweaks titles to avoid duplicate detection | `scripts/draw_prompts.py` |
| 2 | Writing | AI writes articles from the drawn prompt templates, following configurable structural rules (no tables, no AI-tell words, marketing-word budget) | `article-push-workflow` skill |
| 3 | Review | 100-point deduction engine (title risk words / keyword exposure count & position / marketing words / AI-tell words / structure completeness). Score ≥ 90 passes; otherwise auto-fix and re-review (up to 5 rounds) | `scripts/audit_article.py` |
| 4 | Typesetting | Idempotent compose: inline images inserted per section, promo footer appended. Produces both footer and clean versions | `wechat_publisher.py compose` |
| 5 | Distribution | Renders WeChat-compatible inline-styled HTML → uploads images to WeChat CDN → creates drafts via the official API (multi-article push supported). Other platforms reuse the same typeset output | `wechat_publisher.py prepare/draft/open` |
| 6 | Link collection | Connects to an already signed-in browser over CDP (Chrome 9223 / Edge 9222) and extracts published article links from each platform dashboard | `scripts/cdp_collect.py` |

> 💡 All business-specific settings (keyword, promo footer, topic pool, …) live in config sections at the top of each file. Swap them out and the pipeline is ready for your own content — see below.

## Configuration

| What to change | Where |
|----------------|-------|
| Target keyword (counting / detection) | `KEYWORD` at the top of `scripts/audit_article.py`; `KEYWORD` / `KEYWORD_FULL` in `scripts/draw_prompts.py` |
| Title risk words and score thresholds | constants at the top of `scripts/audit_article.py` (e.g. `TITLE_DANGER_WORDS`) |
| Topic pool (with groups) | `TOPIC_POOL` in `scripts/draw_prompts.py` |
| Promo footer (text / image / cleanup patterns) | `PROMO_*` section in `wechat_publisher.py` |
| Random image tag and candidate pool | `RANDOM_IMG_TAG` / `RANDOM_IMG_POOL` in `wechat_publisher.py` |
| Cross-platform footer cleanup patterns | `CLEANUP_PATTERNS` in `scripts/strip_wechat_footer.py` |
| Platform list / page extraction rules | `PLATFORMS` in `scripts/cdp_collect.py` |

Most settings also accept environment variable overrides (e.g. `TARGET_KEYWORD`, `PROMO_FOOTER_TEXT`).

## Project Layout

```
.
├── wechat_publisher.py            # WeChat typesetting & publishing (compose/prepare/draft/open/published)
├── scripts/
│   ├── draw_prompts.py            # Topic drawing (group rotation + dedup + title tweaks)
│   ├── audit_article.py           # Article review & scoring engine
│   ├── cdp_collect.py             # Multi-platform link collection over CDP
│   ├── strip_wechat_footer.py     # Footer cleanup for cross-platform reuse
│   ├── csdn_get.py                # Full-text scraper for CSDN accounts
│   ├── csdn_blog_link_grab.py     # CSDN post-link crawler
│   ├── render.mjs                 # Markdown → WeChat HTML renderer entry (Node)
│   ├── wechat-renderer.mjs        # Rendering engine (inline styles only)
│   └── markdown-to-sections.mjs   # Markdown structure parser
├── .reasonix/skills/              # AI orchestration layer (project-level skills)
│   ├── article-push-workflow/     # One-command flow: draw → write → review → fix → typeset → draft
│   ├── prompt-draw/               # Draw prompts only
│   ├── article-audit/             # Review only
│   ├── wechat-paiban/             # WeChat typesetting + two-article push
│   └── link-get/                  # Link collection (CDP preflight, browser auto-start)
├── start_chrome_debug.bat         # Launch Chrome with debug port (Windows)
├── start_edge_debug.bat           # Launch Edge with debug port (Windows)
├── collect_links.bat              # One-click link collection (Windows)
├── .env.example                   # Credentials template
└── requirements.txt
```

## Getting Started

Requirements: Python 3.10+, Node.js (for typesetting), Chrome or Edge (platform dashboards must stay signed in).

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials (only needed for WeChat API publishing)
cp .env.example .env    # fill in AppID / AppSecret, and whitelist your IP in the WeChat dashboard

# 3. Launch the browser with a debug port, sign in to each platform dashboard
start_chrome_debug.bat   # or start_edge_debug.bat

# 4. Draw two prompt sets (topic + template + keyword distribution)
python scripts/draw_prompts.py --save

# 5. Have the AI write the article, then review it
python scripts/audit_article.py outputs/{title}_raw.md

# 6. Typeset: compose images → render HTML → create WeChat draft
python wechat_publisher.py compose outputs/{title}_raw.md outputs/{title}_footer.md
python wechat_publisher.py prepare outputs/{title}_footer.md
python wechat_publisher.py draft outputs/draft_config.json
python wechat_publisher.py open

# 7. After distributing on each platform, collect the links
python scripts/cdp_collect.py --titles "title1,title2"
```

When used with a skills-capable AI agent (e.g. Reasonix), keep `.reasonix/skills/` at the project root and say "开始推送" to trigger the whole flow.

## Design Notes

**Immutable file pipeline**: `_raw.md` (source, read-only) → `_composed.md` (composed, regenerable) → `_composed.html` (final). `compose` always reads the source and writes a new file — running it a hundred times yields the same result, never stacking images or footers.

**Never kill the browser**: all browser automation reuses your signed-in tabs over CDP. Losing a session is worse than doing a step manually — the session is the most valuable asset in this kind of automation.

**Review-fix loop**: the reviewer emits a structured issue list; the AI fixes each item and re-reviews, up to 5 rounds. Fix history is persisted to disk and feeds back into the rules.

**Distribution boundary**: WeChat goes fully automatic to the draft box via the official API; other platforms intentionally keep a manual publish step and only reuse the typeset output, to stay clear of platform risk control.

## Notes

- `scripts/render.mjs`, `wechat-renderer.mjs` and `markdown-to-sections.mjs` are derived from a third-party WeChat typesetting engine (see the header comment in `render.mjs` for the upstream reference). Verify the upstream license before use.

## License

MIT

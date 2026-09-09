#!/usr/bin/env python3
"""
Zoonova AI Multi-Session Market Intelligence Publisher
Executes 3 daily reports: 8:30 AM (Pre-Market), 2:00 PM (Midday), 5:00 PM (Post-Close).
Features:
 - Gemini 2.5 Flash with live Google Search grounding
 - Schema generation with JSON-LD markup
 - Git-backed file storage (HTML, session JSON, and latest.json)
 - Optional Google Indexing API and webhook notifications
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import markdown
import requests
from google import genai
from google.genai import types
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
BASE_SITE_URL = os.getenv("ZOONOVA_BASE_URL", "https://zoonova.com").rstrip("/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GCP_SERVICE_ACCOUNT_KEY = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_URN = os.getenv("LINKEDIN_PERSON_URN")
INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
INDEXING_SCOPES = ["https://www.googleapis.com/auth/indexing"]
REPORTS_DIR = "reports"

CORE_TICKERS = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AMZN", "META", "TSLA"]
TERMINAL_CSS = """
<style>
  :root {
    --bg-primary: #0a0e17;
    --bg-surface: #111827;
    --bg-card: #161f30;
    --border: #1f293d;
    --text-main: #e2e8f0;
    --text-muted: #94a3b8;
    --accent-cyan: #00e5ff;
    --accent-emerald: #10b981;
    --accent-rose: #f43f5e;
  }
  * { box-sizing: border-box; }
  body {
    background-color: var(--bg-primary);
    color: var(--text-main);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.6;
    margin: 0;
    padding: 2rem 1rem;
    display: flex;
    justify-content: center;
  }
  .container {
    max-width: 1040px;
    width: 100%;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 2.5rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  }
  h1, h2, h3 { color: #ffffff; letter-spacing: -0.02em; font-weight: 600; }
  h1 { font-size: 1.85rem; border-bottom: 2px solid var(--border); padding-bottom: 0.75rem; margin-top: 0; }
  h2 { font-size: 1.35rem; color: var(--accent-cyan); margin-top: 2rem; margin-bottom: 0.75rem; }
  h3 { font-size: 1.1rem; color: #cbd5e1; }
  p, li { font-size: 0.95rem; color: #cbd5e1; }
  code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.88rem; }
  code { background: #1e293b; padding: 0.15rem 0.4rem; border-radius: 4px; color: var(--accent-cyan); }
  table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.88rem; }
  th { background: var(--bg-card); color: var(--accent-cyan); text-align: left; padding: 10px 14px; border-bottom: 2px solid var(--border); text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }
  td { padding: 10px 14px; border-bottom: 1px solid var(--border); color: #e2e8f0; }
  tr:hover td { background: rgba(0, 229, 255, 0.03); }
  blockquote { border-left: 3px solid var(--accent-cyan); margin: 1.5rem 0; padding: 0.75rem 1.25rem; background: rgba(0, 229, 255, 0.05); border-radius: 0 6px 6px 0; }
  .executive-summary { border-left: 3px solid var(--accent-cyan); background: rgba(0, 229, 255, 0.05); padding: 1rem; border-radius: 6px; margin-bottom: 1.5rem; }
  a { color: var(--accent-cyan); text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
"""
SESSION_CONFIGS = {
    "pre_market": {
        "title_label": "Pre-Market Opening Intelligence",
        "slug_suffix": "pre-market",
        "description": "Pre-market algorithmic equity intelligence analyzing overnight futures, macro economic releases, and opening Quad-Ensemble momentum.",
        "focus_prompt": (
            "Focus on: Overnight global equity market flows (Europe & Asia-Pacific), S&P 500 and Nasdaq-100 futures gaps, "
            "10-Year Treasury yield trajectory, pre-market macroeconomic data prints (CPI, PPI, Jobless claims), "
            "and pre-market earnings surprises. Establish opening Quad-Ensemble directional bias."
        )
    },
    "midday": {
        "title_label": "Midday Momentum & Liquidity Report",
        "slug_suffix": "midday",
        "description": "Midday quantitative review tracking intraday volume profiles, institutional order flow, and BIRCH volatility cluster migrations.",
        "focus_prompt": (
            "Focus on: Regular trading session price discovery, intraday NYSE/Nasdaq volume breadth, sector rotation dynamics, "
            "midday Federal Reserve/FOMC commentary or rate expectations, and shifts in BIRCH cluster volatility regimes. "
            "Examine whether morning breakouts are confirming or showing mean-reversion exhaustion."
        )
    },
    "post_close": {
        "title_label": "Post-Close Settlement & After-Hours Analysis",
        "slug_suffix": "post-close",
        "description": "Daily post-market quantitative breakdown covering closing settlements, sector attribution, model signal verification, and after-hours earnings.",
        "focus_prompt": (
            "Focus on: Closing bell cash index settlements, daily sector performance attribution, institutional market-on-close (MOC) imbalance data, "
            "after-hours mega-cap earnings reports, and end-of-day model verification comparing Quad-Ensemble morning predictions against actual performance."
        )
    }
}


def send_alert(message: str, is_error: bool = False):
    if not ALERT_WEBHOOK_URL:
        return
    prefix = "🚨 **Zoonova Pipeline Error**:" if is_error else "✅ **Zoonova Pipeline Notice**:"
    payload = {"content": f"{prefix} {message}"} if "discord.com" in ALERT_WEBHOOK_URL else {"text": f"{prefix} {message}"}
    try:
        requests.post(ALERT_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to deliver webhook alert: {e}", file=sys.stderr)


def determine_market_session() -> str:
    ny_now = datetime.now(ZoneInfo("America/New_York"))
    hour = ny_now.hour
    if hour < 11:
        return "pre_market"
    elif 11 <= hour < 16:
        return "midday"
    else:
        return "post_close"


def generate_market_intelligence(session_key: str) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not configured.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = SESSION_CONFIGS[session_key]
    ny_now = datetime.now(ZoneInfo("America/New_York"))
    today_str = ny_now.strftime("%A, %B %d, %Y")
 
    system_instruction = (
    "You are the Senior Quantitative Architect and Intelligence Engine for Zoonova AI. "
    "Produce the official Zoonova AI Market Intelligence Analysis matching the exact format of the Zoonova AI Command Center. "
    "Do NOT use generic summaries. Use the exact Markdown headings, tables, and sections specified below.\n\n"
    "CRITICAL TABLE FORMATTING RULES:\n"
    "1. Every Markdown table MUST include a header row, a delimiter row (e.g., |:---|:---|), and every single data row on its own separate line.\n"
    "2. NEVER concatenate rows together or output double pipes ('||'). Every row MUST begin with '|' and end with '|' followed immediately by a newline.\n\n"
    "#### 1. QUANTITATIVE MODEL OVERVIEW & SIGNAL METRICS\n"
    "Detail the Quad-Ensemble ML predictive arrays (time-series regressors, binary classifiers for alpha probability, NLP sentiment transformers, and macro-breadth regime models). "
    "Discuss regression residuals, R-squared values for large-cap ETFs (SPY, QQQ), implied 12-month baseline projections (+10% to +14%), localized NLP sentiment volatility, and selective alpha opportunities.\n\n"
    "#### 2. SENTIMENT INSIGHTS -- TOP 5 HIGH & LOW\n"
    "Top 5 High Sentiment Stocks\n"
    "| Ticker | Company Name | Sentiment Score | Primary Catalyst / Driver |\n"
    "|:---|:---|:---|:---|\n"
    "Provide 5 distinct rows for real equities on separate lines with positive percentage scores (e.g., 99%, 98%) and specific catalysts.\n\n"
    "Top 5 Low Sentiment Stocks\n"
    "| Ticker | Company Name | Sentiment Score | Primary Friction / Risk Factor |\n"
    "|:---|:---|:---|:---|\n"
    "Provide 5 distinct rows on separate lines for real equities or ETFs with negative percentage scores (e.g., -85%, -83%) and specific friction drivers.\n\n"
    "#### 3. ALPHA PROBABILITY & PRICE DELTA LEADERBOARD -- 1-YEAR HORIZON\n"
    "Provide four distinct Markdown tables. Every table row must be on its own separate line:\n\n"
    "S&P 500 -- Top 5 High Alpha Probability (1yr)\n"
    "| Ticker | Current Price ($) | 1-Yr Target Price ($) | Alpha Probability (%) | Implied Excess Alpha (%) |\n"
    "|:---|:---|:---|:---|:---|\n\n"
    "S&P 500 -- Top 5 Price Delta + % Change (1yr)\n"
    "| Ticker | Current Price ($) | 1-Yr Target Price ($) | Absolute Delta ($) | Projected 1-Yr % Change (%) |\n"
    "|:---|:---|:---|:---|:---|\n\n"
    "NASDAQ 100 -- Top 5 High Alpha Probability (1yr)\n"
    "| Ticker | Current Price ($) | 1-Yr Target Price ($) | Alpha Probability (%) | Implied Excess Alpha (%) |\n"
    "|:---|:---|:---|:---|:---|\n\n"
    "NASDAQ 100 -- Top 5 Price Delta + % Change (1yr)\n"
    "| Ticker | Current Price ($) | 1-Yr Target Price ($) | Absolute Delta ($) | Projected 1-Yr % Change (%) |\n"
    "|:---|:---|:---|:---|:---|\n\n"
    "#### 4. REAL-TIME CONTEXTUAL ENRICHMENT\n"
    "A thorough multi-paragraph synthesis linking the top sentiment leaders, alpha standouts, and friction names to real-time earnings, analyst upgrades/downgrades, backlog metrics, and monetary policy conditions.\n\n"
    "#### 5. ANOMALY DETECTION SCANNER\n"
    "Format exactly as:\n"
    "#### DIRECTION: BEARISH\n"
    "#### HIGH SEVERITY\n"
    "- List 10-15 tickers with company names and trend anomaly descriptions (e.g., 'TICKER -- Company Name: Bearish Short-Term (3d) Trend Anomaly, Bearish Long-Term (1w) Trend Anomaly').\n"
    "#### DIRECTION: BULLISH\n"
    "#### MODERATE SEVERITY\n"
    "- List 5-8 tickers with Bullish Short-Term (3d) and Long-Term (1w) anomalies.\n"
    "#### LOW SEVERITY\n"
    "- List 6-8 tickers with single-timeframe bullish trend anomalies.\n"
    "#### DIRECTION: MIXED\n"
    "#### HIGH SEVERITY\n"
    "- List tickers showing conflicting short-term vs. long-term signals.\n\n"
    "#### 6. STRATEGIC INVESTMENT ASSESSMENT\n"
    "Provide a tactical institutional summary detailing the 6-to-12-month macro allocation posture, sector hedging, and alpha overweight recommendations.\n\n"
    "#### 7. STOCK SCORECARD\n"
    "Provide two comprehensive 15-column Markdown tables. Every ticker row must be on its own line:\n"
    "| Ticker | Composite (%) | Alpha Rating | Sentiment Rating | Technical Signal | Macro Alignment | Anomaly Flag | Market Cap | EPS Trend (30d) | EPS Consensus Grade | Short Interest / DTC | Options Flow | Earnings Surprise (4Q) | Bias | EPS Source |\n"
    "|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|\n\n"
    "Follow with:\n"
    "Tech Stock Scorecard\n"
    "| Ticker | Composite (%) | Alpha Rating | Sentiment Rating | Technical Signal | Macro Alignment | Anomaly Flag | Market Cap | EPS Trend (30d) | EPS Consensus Grade | Short Interest / DTC | Options Flow | Earnings Surprise (4Q) | Bias | EPS Source |\n"
    "|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|\n\n"
    "End the report with: '*- For informational purposes only. Not investment advice.*'"
  )
    user_prompt = (
    f"Generate the comprehensive Zoonova AI Market Intelligence Analysis: {config['title_label']} for {today_str}. "
    f"{config['focus_prompt']} "
    "Ground all data in current global equity prices, yields, sector indices, and institutional news flow."
  )
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            max_output_tokens=8192,
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    return response.text


def build_schema_and_dom(report_markdown: str, session_key: str) -> tuple[str, str, str, dict]:
    config = SESSION_CONFIGS[session_key]
    ny_now = datetime.now(ZoneInfo("America/New_York"))
    date_str = ny_now.strftime("%Y-%m-%d")
    display_date = ny_now.strftime("%B %d, %Y")
    iso_timestamp = ny_now.isoformat()

    title = f"Zoonova AI {config['title_label']} - {display_date}"
    slug = f"zoonova-market-intelligence-{date_str}-{config['slug_suffix']}"

    first_para = re.search(r"^(?:#+ .*\n+)?([^\n#]+)", report_markdown.strip())
    summary = first_para.group(1).strip() if first_para else config["description"]

    html_body = markdown.markdown(
        report_markdown,
        extensions=["tables", "fenced_code", "sane_lists"]
    )

    html_body = re.sub(r"(<table>)", r'<div class="market-metrics-table">\1', html_body)
    html_body = re.sub(r"(</table>)", r"\1</div>", html_body)
    html_body = (
        f'<div class="executive-summary">\n'
        f'<p><strong>Session Quantitative Briefing:</strong> {summary}</p>\n'
        f'</div>\n' + html_body
    )

    about_entities = [
        {"@type": "FinancialProduct", "name": "S&P 500", "sameAs": "https://en.wikipedia.org/wiki/S%26P_500"},
        {"@type": "FinancialProduct", "name": "Nasdaq-100", "sameAs": "https://en.wikipedia.org/wiki/Nasdaq-100"},
        {"@type": "Thing", "name": "Quantitative Finance", "sameAs": "https://en.wikipedia.org/wiki/Mathematical_finance"}
    ]
    for ticker in CORE_TICKERS:
        about_entities.append({
            "@type": "FinancialProduct",
            "name": ticker,
            "sameAs": f"https://www.google.com/finance/quote/{ticker}:NASDAQ"
        })

    schema = {
        "@context": "https://schema.org",
        "@type": "AnalysisNewsArticle",
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": f"{BASE_SITE_URL}/reports/{slug}"
        },
        "headline": title,
        "description": summary[:250],
        "datePublished": iso_timestamp,
        "dateModified": iso_timestamp,
        "inLanguage": "en-US",
        "author": {
            "@type": "Organization",
            "name": "Zoonova AI Quantitative Desk",
            "url": BASE_SITE_URL
        },
        "publisher": {
            "@type": "Organization",
            "name": "Zoonova AI",
            "url": BASE_SITE_URL,
            "logo": {
                "@type": "ImageObject",
                "url": f"{BASE_SITE_URL}/assets/zoonova-logo.png"
            }
        },
        "about": about_entities,
        "speakable": {
            "@type": "SpeakableSpecification",
            "cssSelector": [".executive-summary", ".market-metrics-table"]
        }
    }

    final_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="google-site-verification" content="PASTE_YOUR_VERIFICATION_CODE_HERE">
    <title>{title}</title>
    <script type="application/ld+json">
{json.dumps(schema, indent=2)}
    </script>
    {TERMINAL_CSS}
</head>
<body>
    <main class="container">
        {html_body}
    </main>
</body>
</html>"""
    return title, slug, final_html, schema

def save_report_locally(title: str, slug: str, raw_markdown: str, html_content: str, schema_dict: dict, session_key: str):
    os.makedirs(REPORTS_DIR, exist_ok=True)

    report_payload = {
        "title": title,
        "slug": slug,
        "session": session_key,
        "timestamp": datetime.now(ZoneInfo("America/New_York")).isoformat(),
        "schema": schema_dict,
        "markdown": raw_markdown,
        "html": html_content
    }

    # 1. Write specific session JSON & HTML
    json_path = os.path.join(REPORTS_DIR, f"{slug}.json")
    html_path = os.path.join(REPORTS_DIR, f"{slug}.html")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 2. Write/update latest.json for easy frontend fetching
    latest_json_path = os.path.join(REPORTS_DIR, "latest.json")
    with open(latest_json_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

     # 3. Mirror latest report as repository root index.html
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Saved artifacts:")
    print(f" - {json_path}")
    print(f" - {html_path}")
    print(f" - {latest_json_path}")
    print(f" - index.html (Root Landing)")
   



def notify_google_indexing_api(target_url: str):
    raw_key = GCP_SERVICE_ACCOUNT_KEY
    if not raw_key:
        return

    try:
        key_data = json.loads(raw_key) if not os.path.exists(raw_key) else json.load(open(raw_key))
        credentials = service_account.Credentials.from_service_account_info(
            key_data,
            scopes=INDEXING_SCOPES
        )
        credentials.refresh(Request())

        payload = {"url": target_url, "type": "URL_UPDATED"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials.token}"
        }
        res = requests.post(INDEXING_ENDPOINT, headers=headers, json=payload, timeout=15)
        res.raise_for_status()
        print(f"Indexing API: Dispatched {target_url} successfully.")
      except Exception as e:
        print(f"Indexing API notice: {e}", file=sys.stderr)

 def publish_to_linkedin(title: str, summary: str, report_url: str):
  if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_URN:
    print("LinkedIn: Missing credentials. Skipping share.")
    return

  api_url = "https://api.linkedin.com/v2/ugcPosts"
  headers = {
    "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
    "X-Restli-Protocol-Version": "2.0.0",
    "Content-Type": "application/json",
  }
  payload = {
    "author": LINKEDIN_PERSON_URN,
    "lifecycleState": "PUBLISHED",
    "specificContent": {
      "com.linkedin.ugc.ShareContent": {
        "shareCommentary": {
          "text": f"{title}\n\n{summary}\n\nFull analysis: {report_url}"
        },
        "shareMediaCategory": "ARTICLE",
        "media": [
          {
            "status": "READY",
            "originalUrl": report_url,
            "title": {"text": title},
            "description": {"text": summary},
          }
        ],
      }
    },
    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
  }

  try:
    res = requests.post(api_url, headers=headers, json=payload, timeout=15)
    res.raise_for_status()
    print("LinkedIn: Successfully published update.")
  except Exception as exc:
    print(f"LinkedIn error: {exc}")    
def main():
    parser = argparse.ArgumentParser(description="Zoonova AI Automated Intelligence Publisher")
    parser.add_argument(
        "--session",
        choices=["auto", "pre_market", "midday", "post_close"],
        default="auto",
        help="Market session key.",
    )
    args = parser.parse_args()

    try:
        session_key = determine_market_session() if args.session == "auto" else args.session
        session_label = SESSION_CONFIGS[session_key]["title_label"]
        print(f"=== Running Zoonova Pipeline: {session_label} ===")

        print("1/3 Generating Grounded Gemini Flash Analysis...")
        report_md = generate_market_intelligence(session_key)

        print("2/3 Building Schema & Structured Output...")
        title, slug, final_html, schema_dict = build_schema_and_dom(report_md, session_key)

        print("3/3 Writing Report Artifacts...")
        save_report_locally(title, slug, report_md, final_html, schema_dict, session_key)

        public_report_url = f"{BASE_SITE_URL}/reports/{slug}"
        notify_google_indexing_api(public_report_url)
        send_alert(f"Generated **{title}**.\nLocal artifact: `reports/{slug}.json`")
        publish_to_linkedin(title, "Zoonova Daily Market Intelligence Report", public_report_url)
        print("Pipeline execution complete.\n")

    except Exception as exc:
        err_msg = f"Session '{args.session}' failed: {str(exc)}"
        print(f"ERROR: {err_msg}", file=sys.stderr)
        send_alert(err_msg, is_error=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

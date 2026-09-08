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

INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
INDEXING_SCOPES = ["https://www.googleapis.com/auth/indexing"]
REPORTS_DIR = "reports"

CORE_TICKERS = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AMZN", "META", "TSLA"]

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
        "You are the senior quantitative architect and intelligence engine for Zoonova AI. "
        "Produce an authoritative, highly detailed market intelligence analysis for institutional and quantitative investors. "
        "Strictly adhere to the following sections: "
        "1. Executive Summary: Macro regime, market sentiment posture, and primary directional bias. "
        "2. Quad-Ensemble Model Dynamics: Model consensus across Random Forest, Gradient Boosting, Deep Neural Networks, and Support Vector Regression. "
        "3. VADER Sentiment & News Velocity: Natural language sentiment indices scored on a -1.0 to +1.0 scale with key driver headlines. "
        "4. BIRCH Clustering & Volatility Regimes: Microstructure cluster groupings, dispersion metrics, and outlier transitions. "
        "5. Quantitative Scorecard Matrix: A strict Markdown table with columns: "
        "   | Ticker | Quad-Ensemble Score (0-100) | VADER Score (-1 to +1) | BIRCH Cluster | Model Signal | Target Bias | "
        "Zero generic commentary. Every metric must be specific, concrete, and quantitative."
    )

    user_prompt = (
        f"Generate the comprehensive Zoonova AI Market Intelligence Analysis: {config['title_label']} for {today_str}. "
        f"{config['focus_prompt']} "
        "Ground all data in current global equity prices, yields, sector indices, and institutional news flow."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
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

    final_html = (
        f'<script type="application/ld+json">\n{json.dumps(schema, indent=2)}\n</script>\n\n'
        f"{html_body}"
    )

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

    print(f"Saved artifacts:")
    print(f" - {json_path}")
    print(f" - {html_path}")
    print(f" - {latest_json_path}")


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


def main():
    parser = argparse.ArgumentParser(description="Zoonova AI Automated Intelligence Publisher")
    parser.add_argument(
        "--session",
        choices=["auto", "pre_market", "midday", "post_close"],
        default="auto",
        help="Market session key."
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

        print("Pipeline execution complete.\n")

    except Exception as exc:
        err_msg = f"Session '{args.session}' failed: {str(exc)}"
        print(f"ERROR: {err_msg}", file=sys.stderr)
        send_alert(err_msg, is_error=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

from datetime import datetime
import json
import os
import re
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types
import markdown

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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
        "title_label": "Pre-Market Quantitative Briefing",
        "focus_prompt": "Focus on overnight futures, global macro developments, pre-market movers, and opening liquidity profiles.",
    },
    "midday": {
        "title_label": "Midday Momentum & Liquidity Report",
        "focus_prompt": "Focus on midday volume profiles, order flow dynamics, morning breakout confirmations vs failures, and intraday sector rotations.",
    },
    "post_close": {
        "title_label": "Post-Close Settlement & After-Hours Analysis",
        "focus_prompt": "Focus on closing bell settlement, market-on-close imbalances, after-hours earnings catalysts, and overnight risk positioning.",
    },
}


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
      "You are the Senior Quantitative Architect and Intelligence Engine for"
      " Zoonova AI. Produce the official Zoonova AI Market Intelligence"
      " Analysis matching the exact format of the Zoonova AI Command Center. Do"
      " NOT use generic summaries. Use the exact Markdown headings, tables, and"
      " sections specified below.\n\n"
      "CRITICAL TABLE FORMATTING RULES:\n"
      "1. Every Markdown table MUST be preceded by an empty blank line.\n"
      "2. Every Markdown table MUST include a header row, a delimiter row (e.g.,"
      " |:---|:---|), and every single data row on its own separate line.\n"
      "3. NEVER concatenate rows together or output double pipes ('||'). Every"
      " row MUST begin with '|' and end with '|' followed immediately by a"
      " newline.\n\n"
     "#### 1. QUANTITATIVE MODEL OVERVIEW & SIGNAL METRICS\n"
      "Detail the hybrid architecture combining Zoonova's proprietary"
      " Quad-Ensemble ML framework with Google Gemini Flash for real-time"
      " contextual synthesis and grounded intelligence. Explain the"
      " quantitative pipeline: Temporal Fusion Transformer (TFT) for"
      " multi-horizon forecasting, CatBoost for categorical splits, Random"
      " Forest (RF) for baseline stability, and XGBoost (XGB) for residual"
      " loss optimization. Detail BIRCH unsupervised clustering for"
      " microstructure volatility regimes, and VADER news velocity enriched"
      " by Gemini Flash for semantic macroeconomic reasoning. Discuss"
      " regression residuals, R-squared values for large-cap ETFs (SPY, QQQ),"
      " implied 12-month baseline projections (+10% to +14%), and selective"
      " alpha opportunities.\n\n"
      "#### 2. SENTIMENT INSIGHTS -- TOP 5 HIGH & LOW\n"
      "Top 5 High Sentiment Stocks\n\n"
      "| Ticker | Company Name | Sentiment Score | Primary Catalyst /"
      " Driver |\n"
      "|:---|:---|:---|:---|\n"
      "Provide 5 distinct rows for real equities on separate lines with"
      " positive percentage scores (e.g., 99%, 98%) and specific"
      " catalysts.\n\n"
      "Top 5 Low Sentiment Stocks\n\n"
      "| Ticker | Company Name | Sentiment Score | Primary Friction / Risk"
      " Factor |\n"
      "|:---|:---|:---|:---|\n"
      "Provide 5 distinct rows on separate lines for real equities or ETFs with"
      " negative percentage scores (e.g., -85%, -83%) and specific friction"
      " drivers.\n\n"
      "#### 3. ALPHA PROBABILITY & PRICE DELTA LEADERBOARD -- 1-YEAR HORIZON\n"
      "Provide four distinct Markdown tables. Every table must be preceded by a"
      " blank line and every row must be on its own line:\n\n"
      "S&P 500 -- Top 5 High Alpha Probability (1yr)\n\n"
      "| Ticker | Current Price ($) | 1-Yr Target Price ($) | Alpha"
      " Probability (%) | Implied Excess Alpha (%) |\n"
      "|:---|:---|:---|:---|:---|\n\n"
      "S&P 500 -- Top 5 Price Delta + % Change (1yr)\n\n"
      "| Ticker | Current Price ($) | 1-Yr Target Price ($) | Absolute Delta"
      " ($) | Projected 1-Yr % Change (%) |\n"
      "|:---|:---|:---|:---|:---|\n\n"
      "NASDAQ 100 -- Top 5 High Alpha Probability (1yr)\n\n"
      "| Ticker | Current Price ($) | 1-Yr Target Price ($) | Alpha"
      " Probability (%) | Implied Excess Alpha (%) |\n"
      "|:---|:---|:---|:---|:---|\n\n"
      "NASDAQ 100 -- Top 5 Price Delta + % Change (1yr)\n\n"
      "| Ticker | Current Price ($) | 1-Yr Target Price ($) | Absolute Delta"
      " ($) | Projected 1-Yr % Change (%) |\n"
      "|:---|:---|:---|:---|:---|\n\n"
      "#### 4. REAL-TIME CONTEXTUAL ENRICHMENT\n"
      "A thorough multi-paragraph synthesis linking the top sentiment leaders,"
      " alpha standouts, and friction names to real-time earnings, analyst"
      " upgrades/downgrades, backlog metrics, and monetary policy"
      " conditions.\n\n"
      "#### 5. ANOMALY DETECTION SCANNER\n"
      "Format exactly as:\n"
      "#### DIRECTION: BEARISH\n"
      "#### HIGH SEVERITY\n"
      "- List 10-15 tickers with company names and trend anomaly descriptions"
      " (e.g., 'TICKER -- Company Name: Bearish Short-Term (3d) Trend Anomaly,"
      " Bearish Long-Term (1w) Trend Anomaly').\n"
      "#### DIRECTION: BULLISH\n"
      "#### MODERATE SEVERITY\n"
      "- List 5-8 tickers with Bullish Short-Term (3d) and Long-Term (1w)"
      " anomalies.\n"
      "#### LOW SEVERITY\n"
      "- List 6-8 tickers with single-timeframe bullish trend anomalies.\n"
      "#### DIRECTION: MIXED\n"
      "#### HIGH SEVERITY\n"
      "- List tickers showing conflicting short-term vs. long-term"
      " signals.\n\n"
      "#### 6. STRATEGIC INVESTMENT ASSESSMENT\n"
      "Provide a tactical institutional summary detailing the 6-to-12-month"
      " macro allocation posture, sector hedging, and alpha overweight"
      " recommendations.\n\n"
      "#### 7. STOCK SCORECARD\n"
      "Provide two comprehensive 15-column Markdown tables. Every table must be"
      " preceded by a blank line:\n\n"
      "| Ticker | Composite (%) | Alpha Rating | Sentiment Rating | Technical"
      " Signal | Macro Alignment | Anomaly Flag | Market Cap | EPS Trend (30d)"
      " | EPS Consensus Grade | Short Interest / DTC | Options Flow | Earnings"
      " Surprise (4Q) | Bias | EPS Source |\n"
      "|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|\n\n"
      "Follow with:\n\n"
      "Tech Stock Scorecard\n\n"
      "| Ticker | Composite (%) | Alpha Rating | Sentiment Rating | Technical"
      " Signal | Macro Alignment | Anomaly Flag | Market Cap | EPS Trend (30d)"
      " | EPS Consensus Grade | Short Interest / DTC | Options Flow | Earnings"
      " Surprise (4Q) | Bias | EPS Source |\n"
      "|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|\n\n"
      "End the report with: '*- For informational purposes only. Not investment"
      " advice.*'"
  )

  user_prompt = (
      f"Generate the comprehensive Zoonova AI Market Intelligence Analysis:"
      f" {config['title_label']} for {today_str}. {config['focus_prompt']}"
      " Ground all data in current global equity prices, yields, sector"
      " indices, and institutional news flow."
  )

  response = client.models.generate_content(
      model="gemini-3.5-flash-lite",
      contents=user_prompt,
      config=types.GenerateContentConfig(
          system_instruction=system_instruction,
          temperature=0.2,
          max_output_tokens=8192,
          tools=[types.Tool(google_search=types.GoogleSearch())],
      ),
  )

  return response.text


def build_schema_and_dom(raw_markdown: str, session_key: str):
  config = SESSION_CONFIGS[session_key]
  ny_now = datetime.now(ZoneInfo("America/New_York"))
  today_str = ny_now.strftime("%B %d, %Y")
  iso_now = ny_now.isoformat()
  slug_date = ny_now.strftime("%Y-%m-%d")
  slug_session = session_key.replace("_", "-")
  slug = f"zoonova-market-intelligence-{slug_date}-{slug_session}"
  title = f"Zoonova AI {config['title_label']} - {today_str}"

  first_para = ""
  for line in raw_markdown.splitlines():
    line = line.strip()
    if (
        line
        and not line.startswith("#")
        and not line.startswith("|")
        and not line.startswith("-")
        and not line.startswith("*")
    ):
      first_para = line[:240]
      break

  schema = {
      "@context": "https://schema.org",
      "@type": "AnalysisNewsArticle",
      "mainEntityOfPage": {
          "@type": "WebPage",
          "@id": f"https://zoonova.com/reports/{slug}",
      },
      "headline": title,
      "description": first_para,
      "datePublished": iso_now,
      "dateModified": iso_now,
      "inLanguage": "en-US",
      "author": {
          "@type": "Organization",
          "name": "Zoonova AI Quantitative Desk",
          "url": "https://zoonova.com",
      },
      "publisher": {
          "@type": "Organization",
          "name": "Zoonova AI",
          "url": "https://zoonova.com",
          "logo": {
              "@type": "ImageObject",
              "url": "https://zoonova.com/assets/zoonova-logo.png",
          },
      },
      "about": [
          {
              "@type": "FinancialProduct",
              "name": "S&P 500",
              "sameAs": "https://en.wikipedia.org/wiki/S%26P_500",
          },
          {
              "@type": "FinancialProduct",
              "name": "Nasdaq-100",
              "sameAs": "https://en.wikipedia.org/wiki/Nasdaq-100",
          },
          {
              "@type": "Thing",
              "name": "Quantitative Finance",
              "sameAs": "https://en.wikipedia.org/wiki/Mathematical_finance",
          },
          {
              "@type": "FinancialProduct",
              "name": "SPY",
              "sameAs": "https://www.google.com/finance/quote/SPY:NASDAQ",
          },
          {
              "@type": "FinancialProduct",
              "name": "QQQ",
              "sameAs": "https://www.google.com/finance/quote/QQQ:NASDAQ",
          },
          {
              "@type": "FinancialProduct",
              "name": "NVDA",
              "sameAs": "https://www.google.com/finance/quote/NVDA:NASDAQ",
          },
          {
              "@type": "FinancialProduct",
              "name": "AAPL",
              "sameAs": "https://www.google.com/finance/quote/AAPL:NASDAQ",
          },
          {
              "@type": "FinancialProduct",
              "name": "MSFT",
              "sameAs": "https://www.google.com/finance/quote/MSFT:NASDAQ",
          },
          {
              "@type": "FinancialProduct",
              "name": "AMZN",
              "sameAs": "https://www.google.com/finance/quote/AMZN:NASDAQ",
          },
          {
              "@type": "FinancialProduct",
              "name": "META",
              "sameAs": "https://www.google.com/finance/quote/META:NASDAQ",
          },
          {
              "@type": "FinancialProduct",
              "name": "TSLA",
              "sameAs": "https://www.google.com/finance/quote/TSLA:NASDAQ",
          },
      ],
      "speakable": {
          "@type": "SpeakableSpecification",
          "cssSelector": [".executive-summary", ".market-metrics-table"],
      },
  }

  # Ensure a blank line before any markdown table so it converts properly to an HTML table
  clean_markdown = re.sub(r"([^\n|])\n\|", r"\1\n\n|", raw_markdown)

  html_body = markdown.markdown(
      clean_markdown, extensions=["tables", "fenced_code"]
  )
  html_body = html_body.replace(
      "<table>", '<div class="market-metrics-table"><table>'
  ).replace("</table>", "</table></div>")

  exec_summary_html = (
      '<div class="executive-summary">\n<p><strong>Session Quantitative'
      f" Briefing:</strong> {first_para}</p>\n</div>\n"
  )
  html_body = exec_summary_html + html_body

  final_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-C1TKGPSXW0"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', 'G-C1TKGPSXW0');
    </script>
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

  return schema, final_html, title, slug, iso_now


def main():
  session_key = determine_market_session()
  raw_markdown = generate_market_intelligence(session_key)
  schema, html_content, title, slug, timestamp = build_schema_and_dom(
      raw_markdown, session_key
  )

  os.makedirs("reports", exist_ok=True)

  with open(f"reports/{slug}.html", "w", encoding="utf-8") as f:
    f.write(html_content)

  payload = {
      "title": title,
      "slug": slug,
      "session": session_key,
      "timestamp": timestamp,
      "schema": schema,
      "markdown": raw_markdown,
      "html": html_content,
  }

  with open(f"reports/{slug}.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)

  with open("reports/latest.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)

  with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

  print(f"Successfully published: {title}")


if __name__ == "__main__":
  main()

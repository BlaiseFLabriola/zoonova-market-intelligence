name: Zoonova 3x Daily Market Intelligence

on:
  schedule:
    # Runs at the bottom of the hour (e.g., 8:30 AM check)
    - cron: '30 12,13 * * 1-5'
    # Runs at the top of the hour (e.g., 2:00 PM and 5:00 PM check)
    - cron: '0 18,19,21,22 * * 1-5'
  workflow_dispatch:
    inputs:
      session_override:
        description: 'Session Override'
        required: true
        default: 'auto'
        type: choice
        options:
          - auto
          - pre_market
          - midday
          - post_close

jobs:
  run-publisher:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Dependencies
        run: |
          pip install google-genai google-auth markdown requests

      - name: Check Time Window and Run Pipeline
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          ZOONOVA_BASE_URL: "https://zoonova.com"
          WP_API_URL: "https://zoonova.com/wp-json/wp/v2/posts"
          WP_USER: ${{ secrets.WP_USER }}
          WP_APP_PASSWORD: ${{ secrets.WP_APP_PASSWORD }}
          GCP_SERVICE_ACCOUNT_KEY: ${{ secrets.GCP_SERVICE_ACCOUNT_KEY }}
          ALERT_WEBHOOK_URL: ${{ secrets.ALERT_WEBHOOK_URL }}
        run: |
          # Python check to ensure DST accuracy
          python - << 'EOF'
          import os, sys
          from datetime import datetime
          from zoneinfo import ZoneInfo

          override = "${{ github.event.inputs.session_override }}"
          if override and override != "auto":
              os.system(f"python zoonova_publisher.py --session {override}")
              sys.exit(0)

          ny_now = datetime.now(ZoneInfo("America/New_York"))
          hour, minute = ny_now.hour, ny_now.minute

          # Target windows: 8:30 AM, 2:00 PM, 5:00 PM (Eastern Time)
          if hour == 8 and 25 <= minute <= 45:
              os.system("python zoonova_publisher.py --session pre_market")
          elif hour == 14 and minute <= 15:
              os.system("python zoonova_publisher.py --session midday")
          elif hour == 17 and minute <= 15:
              os.system("python zoonova_publisher.py --session post_close")
          else:
              print(f"Skipping run: Current NY time is {ny_now.strftime('%H:%M')}. Not within a trigger window.")
          EOF

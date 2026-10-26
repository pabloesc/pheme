DAILY_CANDIDATE_ITEMS = 12   # candidate articles fed to the model
DAILY_MAX_ITEMS       = 4    # items selected for the newsletter (1 per section)
NEWS_MIN_ITEMS        = 1    # Substack posts in the "News" section (when any are available)
NEWS_MAX_ITEMS        = 3
NEWS_LOOKBACK_DAYS    = 7    # most Substacks are weekly — a 24h window would usually be empty
WEEKLY_MAX_ITEMS     = 20   # items in a curated weekly digest
WEEKLY_FALLBACK_ITEMS = 12   # items when fallback triggers (not enough stars)
WEEKLY_MIN_PICKS      = 5    # minimum stars before fallback kicks in

SERVER_URL            = "http://localhost:8765"   # pick/feedback link base URL

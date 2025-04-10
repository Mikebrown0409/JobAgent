"""Constants for form interaction tools."""

# Timeouts and Delays
DEFAULT_TIMEOUT = 10000  # ms (10 seconds)
SHORT_TIMEOUT = 3000   # ms (3 seconds)
VISIBILITY_TIMEOUT = 5000 # ms (5 seconds)
INTERACTION_DELAY = 0.5  # seconds
POST_TYPE_DELAY = 0.75   # seconds
POST_CLICK_DELAY = 0.5   # seconds
RETRY_DELAY_BASE = 0.5   # seconds

# Similarity Thresholds (0.0 to 1.0)
DEFAULT_FUZZY_THRESHOLD = 0.75
HIGH_FUZZY_THRESHOLD = 0.80
VERIFICATION_THRESHOLD = 0.70
LOW_VERIFICATION_THRESHOLD = 0.60 # For less certain cases like keyboard nav fallback 
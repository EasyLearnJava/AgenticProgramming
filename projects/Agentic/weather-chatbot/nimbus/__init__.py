"""nimbus: the weather chatbot's Python package. Each module does one thing; nimbus/app.py puts them together."""

import os

# The vercel package sends usage events, with the team's and the project's ids, to telemetry.vercel.com when the
# process ends, unless this is set before it's first imported (issue 58). Two of our modules import it, cache.py and,
# from step 12, middleware.py: set here, it's set before either runs, in whichever order (issue 69).
os.environ.setdefault("VERCEL_TELEMETRY_DISABLED", "1")

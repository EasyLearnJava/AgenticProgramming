# Surprise-trip sandbox

Enter **Book a surprise trip** (case-insensitive, otherwise the complete phrase) or open **App → Surprise trip**.
The first response is a planner, not a booking. Choose dates and 1–6 adults; the hotel allocation is at most two
adults per room, for a 1–14-night stay. Dates can be chosen within the next 330 days.

1. Search DFW ↔ Las Vegas (LAS) on the chosen dates and a hotel within 20 km of Tusayan / Grand Canyon South Rim.
2. Verify and prebook the two offers to obtain complete USD prices. This validates quotes, without confirming
   reservations. Synthetic names and reserved example.com contact details are used.
3. Add the full-party round-trip flight fare and the full-stay hotel price for every room, including disclosed
   mandatory hotel fees. Unknown or incompatible prices cannot pass the approval gate. Exactly $800 is within budget;
   a total **above $800** receives a prominent warning.
4. Wait for **Yes, book both (sandbox)**. Even a total below $800 requires Yes. Typing `yes` is supported only while
   this is the latest uninterrupted surprise-trip request in chat. No other chat prompt inherits this rule.
5. Re-read the same prebooks and compare the total with the approved amount. A changed total requires another Yes;
   an expired quote must be requested again. No replacement offer is silently approved.
6. Submit each simulated booking, displaying its own reference and confirmed, pending, failed or unknown state.
   The two provider operations are not atomic. A failed or uncertain flight submission stops hotel submission;
   an accepted-but-pending flight is shown honestly. Recovery reads existing attempts without submitting another.

Las Vegas is separate from the Grand Canyon hotel location. Transfers, meals, park entry and optional extras are
not included. This is a booking demonstration, not a real trip reservation or a conditions/safety assessment.

The separate `nimbus/surprise_trip` package, templates, namespaced JavaScript/CSS, cookie, signed receipts, in-memory
gate and tab storage do not modify the original Zion/LAX demo or regular travel planner. Only the existing bounded
Nuitée sandbox transport and common display primitives are reused. There are no Kiwi or trivago searches.

`SURPRISE_TRIP_ENABLED=false` disables its chat bridge, navigation and endpoints. No personal Nuitée key is needed:
the fixed official MCP endpoint supplies shared sandbox access. No real passenger data, card or production key is
accepted. A separate HMAC purpose uses `BOOKING_DEMO_SECRET` or the existing `MEMORY_COOKIE_SECRET`; with neither,
receipts are process-local and expire across server restarts/workers. Shared sandbox bookings appear in Nimbus,
not in the visitor's own Nuitée dashboard.

No tests, reviews, live inventory searches or booking calls were run for this implementation, following the demo
work's existing constraint. The stored UI is a snapshot; use Refresh booking status for current provider status.

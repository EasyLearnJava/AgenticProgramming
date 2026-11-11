# Isolated booking demonstration

Say **Book a trip to Zion this weekend** in chat, or open **App → Demo bookings** (`/demo/bookings`).

- Fixed synthetic adult Avery Linton; no visitor names, contact details or payment information.
- Coming Friday through Sunday using Dallas's calendar. DFW → SGU on Friday; arrival back at DFW on Sunday
  at 6 PM or later. No silent date/airport substitution. On Saturday/Sunday, the coming Friday is the next week.
- One room within 10 km of Springdale, Utah, for two nights.
- The official Nuitée MCP's no-key mode supplies its shared **sandbox** credential. No production key or endpoint
  configuration exists in this module. Only simulated `ACC_CREDIT_CARD` payment is sent.
- Search, verification, prebooking and booking are separate bounded requests. The UI displays confirmed, pending,
  unavailable and unknown outcomes independently. Refresh checks the original attempt; hotel timeouts are recovered
  by the unique client reference, never by creating a replacement booking. Flight recovery uses the API's
  documented same-prebook idempotency.
- Results stay in the current tab's session storage. GET pages never create bookings. Signed, expiring receipts
  bind API steps to a separate HTTP-only browser cookie; no general booking lookup or account-wide listing exists.
- `BOOKING_DEMO_ENABLED=false` removes the chat interception, menu link and API access. It defaults to enabled for
  this demonstration. Kiwi/trivago, the regular park planner, weather, RAG and preference workflows are unchanged.
- Receipt signing uses optional `BOOKING_DEMO_SECRET` (32+ characters), otherwise the existing
  `MEMORY_COOKIE_SECRET`, domain-separated for this feature. Neither goes to Nuitée. With neither configured, a
  process-local secret works for local demos; restarts or other serverless workers invalidate receipts. Use a stable
  signing secret for a Vercel demo. This is an application signing secret, not a Nuitée API key.
- These bookings belong to the shared sandbox; they are visible in Nimbus, not your personal Nuitée dashboard.
  They do not provide real tickets, rooms, payment processing or a safety assessment of a real trip.

The entry points in app/chat/page setup only register this independent package and its namespaced assets.
No tests, live booking runs or reviews were performed for this implementation, as requested.

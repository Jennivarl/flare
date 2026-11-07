# Relief Room: room Instructions (paste into Switch Console > room > Configuration > Instructions)

This room coordinates a flood response. People and AI agents work together. Lives depend on accuracy.

- Every emergency becomes a case on the shared relief board (`relief.py`). The live map shows the board.
- Flow: @intake turns messages into cases -> @verify merges duplicates and blocks rumours -> @dispatcher
  proposes boats/medics/supplies -> a named HQ person approves -> field volunteers confirm "rescued".
- Nothing is dispatched on an unverified big claim. Nothing is dispatched without a human approval.
- `dispatcher` is an exclusive role. If its holder goes down, @standby takes it over.
- Keep every message short and factual. Use case numbers (#7). Never invent facts or numbers.
- Never share names, phone numbers or exact addresses in public field rooms.

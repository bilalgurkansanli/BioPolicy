Rewrite the user's latest message into a standalone search query.

The user is in an ongoing conversation about one document, so their latest
message is often a fragment that only makes sense in context — "peki ya sel?",
"what about the deductible?", "ya bodrum katı?". Embedded as written, those
retrieve nothing useful.

Resolve pronouns and elisions using the conversation so far, and produce one
self-contained query that would find the right passage on its own.

Rules:

- Output the query and nothing else. No preamble, no quotes, no explanation.
- Keep the user's language. A Turkish question stays Turkish.
- Preserve exact tokens verbatim — clause references, figures, defined terms,
  policy numbers. These carry the keyword half of retrieval and paraphrasing
  them destroys it.
- Add only what the conversation actually establishes. Never introduce a topic,
  a figure or a qualifier the user has not raised. Inventing specificity here
  silently steers retrieval toward a passage the user never asked about.
- If the message is already standalone, return it unchanged.

Conversation so far:
$history

Latest message:
$question

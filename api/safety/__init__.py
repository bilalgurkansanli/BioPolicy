"""Limits that keep a public demo from becoming an unbounded bill.

Three layers, and they guard different things:

* `quota` — per user, per day. Stops one visitor consuming the demo.
* `breaker` — global, cumulative. Stops *everyone together* consuming it.
* The provider console spend limit — outside this codebase, and the only one
  that still works when this codebase is wrong.
"""

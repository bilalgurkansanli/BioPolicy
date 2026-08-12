# ADR 011 — Locale is a preference, not a route

- **Status:** accepted
- **Date:** 2026-08-04
- **Phase:** 4

## Context

The spec names `next-intl` for the Turkish/English interface. Its standard
setup puts the locale in the URL — `/tr/app`, `/en/app` — with a proxy
(`middleware` before Next.js 16) that negotiates and redirects.

That shape exists to solve a problem this application does not have. Locale
routing pays off when the *content* differs per locale: separate URLs are
indexable, shareable, and translatable independently. Here the content is three
synthetic PDFs and an evaluation report, and none of them change with the
interface language. A Turkish policy is a Turkish policy at `/en/app`.

Two things follow from that, and one is a correctness issue rather than a
preference:

**The document's language and the interface's language are independent.** A
Turkish speaker reading the English commercial policy is a case the demo
deliberately includes — the golden dataset has a `cross_lingual` category for
exactly this. `/tr/app` showing an English document reads as a bug in a way
that a language toggle in the header does not.

**Locale routing has a cost that is not paid back.** Every internal link must
carry the active locale, a proxy runs on every request to negotiate and
redirect, and the four static pages become eight. The application is four
routes and one dictionary.

## Decision

No locale segment, no negotiating proxy, no `next-intl`.

The two dictionaries live in `web/lib/i18n.ts`, typed so that a key added to one
and forgotten in the other is a compile error. The active locale is read through
`useSyncExternalStore` from `localStorage`, with `navigator.languages` as the
fallback and Turkish as the default (`web/lib/locale-store.ts`).

`localStorage` is treated as an external store rather than copied into state by
an effect. Its server snapshot is explicitly the default locale, which is what
keeps the first client render from disagreeing with the server-rendered HTML.

## Consequences

**Bought:** one dictionary module and a toggle instead of a routing layer. The
interface language is orthogonal to the document, which is the truth of the
product. All four pages stay statically prerendered.

**Cost, and it is real:** the interface language is not in the URL, so it cannot
be linked to or crawled. `<html lang>` is corrected on the client after
hydration rather than served correct, and page metadata — the description, the
Open Graph card, the canonical URL — is served in the default locale to
everybody. For a portfolio demo whose content is identical in both languages,
that is an acceptable trade; for a product with translated *content*, it would
not be.

**The tab title is the one exception, added later.** It is the only piece of
metadata whose reader has stated a preference, so `LocaleProvider` rewrites
`document.title` after hydration from `meta.pages`, the same way and for the
same reason it corrects `<html lang>`. Nothing a crawler reads changes.

Doing it needs more than one assignment, and the reason is worth recording
because it is invisible until measured. React owns the `<title>` node, and which
of us writes last depends on how the page was reached: on a client-side
navigation Next writes its metadata title and our effect corrects it five
milliseconds later, but on a **first load** the order inverts — our write lands
during hydration effects and React's commit of the build-time metadata follows
it. Setting the title once therefore works on every link click and fails on the
one load that matters. `LocaleProvider` watches the node with a
`MutationObserver` and reasserts instead of guessing at a delay.

**Revisit if:** the interface ever fronts locale-specific content — a Turkish
landing page with different copy, region-specific policy documents, or anything
worth indexing separately. At that point the URL has to carry the locale, and
`next-intl` becomes the right tool rather than an unused abstraction.

## Alternatives considered

**`next-intl` with locale routing as specified.** Rejected above: the cost is
routing infrastructure and the payoff is indexable per-locale content that does
not exist here.

**`next-intl` without routing** (its `Provider` alone). This is closer, but the
remaining value over a typed dictionary is ICU message formatting, which the
interface copy does not use — there is no pluralisation and no interpolation
beyond one count.

**A cookie set by a proxy, so the server can render the right language.** Fixes
`<html lang>` and the metadata. Rejected because it reintroduces the proxy on
every request to solve a problem worth one line of `useEffect` here, and because
a cookie is a consent surface in the EU that a `localStorage` preference is not.

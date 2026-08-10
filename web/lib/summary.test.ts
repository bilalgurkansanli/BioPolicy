import { describe, expect, it } from "vitest";

import { summarise, summaryIntent } from "./summary";
import type { Citation, PolicyProfile, ProfileField } from "./types";

const CITATION: Citation = {
  context_id: "C1",
  quote: "BİNA YANGIN 3.630.000,00",
  page: 1,
  page_end: 1,
  section_path: "SİGORTA TEMİNATI",
  bbox: null,
  exact: true,
};

function profile(
  entries: Array<[ProfileField, string, string]>,
  overrides: Partial<PolicyProfile> = {},
): PolicyProfile {
  return {
    entries: entries.map(([field, label, value]) => ({
      field,
      label,
      value,
      citation: CITATION,
    })),
    absent: [],
    chunks_seen: 132,
    chunks_total: 132,
    batches_failed: 0,
    dropped: 0,
    model: "claude-haiku-4-5",
    prompt_version: "profile_v2",
    ...overrides,
  };
}

describe("summarise", () => {
  it("leads the cover summary with the amounts, not the perils", () => {
    const summary = summarise(
      profile([
        ["covered_peril", "Deprem", "Teminat kapsamında"],
        ["sub_limit", "BİNA YANGIN", "3.630.000,00 TL"],
      ]),
      "cover",
    );

    expect(summary?.sections.map((s) => s.field)).toEqual([
      "sub_limit",
      "covered_peril",
    ]);
  });

  it("shows every extracted row rather than a selection", () => {
    const summary = summarise(
      profile([
        ["sub_limit", "BİNA YANGIN", "3.630.000,00 TL"],
        ["sub_limit", "EŞYA YANGIN", "550.000,00 TL"],
        ["sub_limit", "KİRA KAYBI", "418.000,00 TL"],
      ]),
      "cover",
    );

    expect(summary?.sections[0].entries).toHaveLength(3);
  });

  it("keeps exclusions and deductibles apart from cover", () => {
    const data = profile([
      ["sub_limit", "BİNA YANGIN", "3.630.000,00 TL"],
      ["exclusion", "Kasıt", "Kapsam dışı"],
    ]);

    expect(summarise(data, "cover")?.sections.map((s) => s.field)).toEqual([
      "sub_limit",
    ]);
    expect(summarise(data, "exclusions")?.sections.map((s) => s.field)).toEqual([
      "exclusion",
    ]);
  });

  it("is null when the schema has nothing for that summary", () => {
    expect(summarise(profile([["exclusion", "Kasıt", "x"]]), "cover")).toBeNull();
  });

  it("is null without a profile, so the caller falls back to asking", () => {
    expect(summarise(null, "cover")).toBeNull();
  });

  it("reports the empty slots this summary is responsible for", () => {
    const summary = summarise(
      profile([["sub_limit", "BİNA YANGIN", "3.630.000,00 TL"]], {
        absent: ["covered_peril", "waiting_period"],
      }),
      "cover",
    );

    // `waiting_period` belongs to the terms summary and is not this one's news.
    expect(summary?.absent).toEqual(["covered_peril"]);
  });

  it("withholds the empty slots when the document was only partly read", () => {
    /** The rule the profile card already follows: a slot nobody looked at and a
     * slot the document is silent on are different claims. */
    const summary = summarise(
      profile([["sub_limit", "BİNA YANGIN", "3.630.000,00 TL"]], {
        absent: ["covered_peril"],
        chunks_seen: 96,
        chunks_total: 132,
      }),
      "cover",
    );

    expect(summary?.absent).toEqual([]);
  });
});

describe("summaryIntent", () => {
  it("recognises the request that started this", () => {
    expect(summaryIntent("Teminat özeti ver", "tr")).toBe("cover");
  });

  it.each([
    "Özetle",
    "Poliçeyi özetler misin",
    "Teminatları listele",
    "Teminatlar nelerdir",
    "Tümünü göster",
  ])("reads %j as a cover summary", (text) => {
    expect(summaryIntent(text, "tr")).toBe("cover");
  });

  it.each(["Summarise the cover", "Give me an overview", "List all coverages"])(
    "reads %j as a cover summary in English",
    (text) => {
      expect(summaryIntent(text, "en")).toBe("cover");
    },
  );

  it("routes exclusions to their own summary", () => {
    expect(summaryIntent("İstisnaları özetle", "tr")).toBe("exclusions");
    expect(summaryIntent("Summarise the exclusions", "en")).toBe("exclusions");
  });

  it("routes dates and parties to the terms summary", () => {
    expect(summaryIntent("Poliçe süresi ve tarafları özetle", "tr")).toBe(
      "terms",
    );
  });

  it("leaves an ordinary question alone", () => {
    expect(summaryIntent("Deprem teminatı var mı?", "tr")).toBeNull();
    expect(summaryIntent("Bina yangın bedeli ne kadar?", "tr")).toBeNull();
    expect(summaryIntent("Is flooding covered?", "en")).toBeNull();
  });

  it("does not hijack a question about one figure that says 'özet'", () => {
    /** The asymmetry this is tuned around: missing a summary request costs
     * prose instead of a table, and answering a real question with a table
     * costs the answer. */
    expect(summaryIntent("Deprem teminatı ne kadar, özetle", "tr")).toBeNull();
    expect(summaryIntent("Summarise how much the deductible is", "en")).toBeNull();
  });

  it("matches Turkish suffixes, which is most of the real usage", () => {
    for (const text of ["özeti", "özetini ver", "özetler misin", "özetle"]) {
      expect(summaryIntent(text, "tr")).toBe("cover");
    }
  });
});

import { describe, expect, it } from "vitest";

import { suggestQuestions } from "./suggest";
import type { Citation, PolicyProfile, ProfileField } from "./types";

const CITATION: Citation = {
  context_id: "C1",
  quote: "1.800.000 TL",
  page: 2,
  page_end: 2,
  section_path: "Madde 2",
  bbox: null,
  exact: true,
};

function profile(
  entries: Array<[ProfileField, string, string]>,
): PolicyProfile {
  return {
    entries: entries.map(([field, label, value]) => ({
      field,
      label,
      value,
      citation: CITATION,
    })),
    absent: [],
    chunks_seen: 21,
    chunks_total: 21,
    batches_failed: 0,
    dropped: 0,
    model: "claude-haiku-4-5",
    prompt_version: "profile_v1",
  };
}

describe("suggestQuestions", () => {
  it("builds a question from a slot the document actually filled", () => {
    const [first] = suggestQuestions(
      profile([["sub_limit", "Deprem", "1.800.000 TL"]]),
      "tr",
    );

    expect(first.question).toBe("Deprem teminatının limiti ne kadar?");
    expect(first.field).toBe("sub_limit");
  });

  it("answers in the locale it was asked in", () => {
    const [first] = suggestQuestions(
      profile([["sub_limit", "Earthquake", "1,800,000"]]),
      "en",
    );

    expect(first.question).toBe("What is the limit for Earthquake?");
  });

  it("has nothing to suggest before the document has been read", () => {
    // Not a placeholder, not a generic list. A suggestion is a claim that this
    // document answers something, and before extraction there is no such claim.
    expect(suggestQuestions(null, "tr")).toEqual([]);
  });

  it("has nothing to suggest when extraction filled no slots", () => {
    expect(suggestQuestions(profile([]), "tr")).toEqual([]);
  });

  it("does not ask about the same subject twice", () => {
    // Taken from the real extracted profile of the bundled home policy, which
    // is where this was found: the first version suggested the fire limit and
    // then the fire deductible — two slots, one subject, and a list that reads
    // as a document about fire.
    const suggestions = suggestQuestions(
      profile([
        ["sub_limit", "Yangın, Yıldırım, İnfilak", "2.500.000 TL"],
        ["sub_limit", "Deprem ve Yanardağ Püskürmesi", "1.800.000 TL"],
        ["deductible", "Yangın, Yıldırım, İnfilak", "Muafiyet yok"],
        ["deductible", "Deprem ve Yanardağ Püskürmesi", "%2"],
        ["exclusion", "Savaş ve benzeri haller", "kapsam dışı"],
      ]),
      "tr",
      3,
    );

    const labels = suggestions.map((s) => s.label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("repeats a subject rather than returning a short list", () => {
    // The constraint above is a preference, not a rule. A document with one
    // peril should still offer both its limit and its deductible.
    const suggestions = suggestQuestions(
      profile([
        ["sub_limit", "Deprem", "1.800.000 TL"],
        ["deductible", "Deprem", "%2"],
      ]),
      "tr",
    );

    expect(suggestions).toHaveLength(2);
  });

  it("spreads across fields before taking a second from any one", () => {
    // Four questions about four sub-limits reads as a document about one thing.
    const suggestions = suggestQuestions(
      profile([
        ["sub_limit", "Deprem", "1.800.000"],
        ["sub_limit", "Yangın", "900.000"],
        ["sub_limit", "Hırsızlık", "250.000"],
        ["exclusion", "Evcil hayvan zararı", "kapsam dışı"],
      ]),
      "tr",
    );

    const fields = suggestions.map((s) => s.field);
    expect(fields.slice(0, 2)).toEqual(["sub_limit", "exclusion"]);
  });

  it("puts what costs money before what defines scope", () => {
    const fields = suggestQuestions(
      profile([
        ["policy_period", "", "01.05.2026 – 01.05.2027"],
        ["territorial_scope", "", "Türkiye"],
        ["deductible", "", "4.000 TL"],
      ]),
      "tr",
    ).map((s) => s.field);

    expect(fields[0]).toBe("deductible");
  });

  it("asks about an exclusion as a question, not as a statement", () => {
    // The answer is "no, and here is the clause" — the behaviour this project
    // exists to show. A suggestion that asserted the exclusion would skip it.
    const [first] = suggestQuestions(
      profile([["exclusion", "Sel hasarı", "kapsam dışı"]]),
      "tr",
    );

    expect(first.question).toBe("Sel hasarı teminat kapsamında mı?");
  });

  it("drops a label too long to be a name", () => {
    const long = "Sigortalının ikamet ettiği binanın dış cephesine".repeat(3);

    expect(suggestQuestions(profile([["sub_limit", long, "x"]]), "tr")).toEqual(
      [],
    );
  });

  it("never produces a question with an empty subject", () => {
    // "What is the limit for ?" — the failure mode of templating a per-item
    // field whose label extraction came back blank.
    const suggestions = suggestQuestions(
      profile([
        ["sub_limit", "", "1.800.000"],
        ["exclusion", "", "kapsam dışı"],
      ]),
      "tr",
    );

    expect(suggestions).toEqual([]);
  });

  it("still asks the singular fields that take no label", () => {
    const [first] = suggestQuestions(
      profile([["notification_deadline", "", "5 iş günü"]]),
      "tr",
    );

    expect(first.question).toBe("Hasarı kaç gün içinde bildirmem gerekiyor?");
  });

  it("does not repeat itself", () => {
    const suggestions = suggestQuestions(
      profile([
        ["sub_limit", "Deprem", "1.800.000"],
        ["sub_limit", "deprem", "1.800.000"],
      ]),
      "tr",
    );

    expect(suggestions).toHaveLength(1);
  });

  it("stops at the limit it is given", () => {
    const many = Array.from({ length: 12 }, (_, i) => {
      return ["sub_limit", `Teminat ${i}`, "1"] as [ProfileField, string, string];
    });

    expect(suggestQuestions(profile(many), "tr", 3)).toHaveLength(3);
  });
});

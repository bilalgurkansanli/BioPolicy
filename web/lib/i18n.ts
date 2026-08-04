/**
 * Interface copy, in Turkish and English.
 *
 * The two dictionaries are structurally identical and the English one is typed
 * against the Turkish one, so a key added on one side and forgotten on the
 * other is a compile error rather than a screen with `undefined` on it.
 *
 * Locale is a preference, not a route — see
 * [ADR 011](../../docs/adr/011-locale-is-a-preference.md).
 */

export const LOCALES = ["tr", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "tr";

const tr = {
  meta: {
    title: "BioPolicy — poliçenizde gerçekten ne yazıyor",
    description:
      "Sigorta poliçeleri ve hukuki sözleşmeler için, her cevabı belgedeki maddeye bağlayan; belge cevabı içermiyorsa cevap vermeyi reddeden bir soru-cevap sistemi.",
  },
  nav: {
    workspace: "Deneyin",
    evaluation: "Ölçümler",
    source: "Kaynak kod",
    home: "Ana sayfa",
  },
  language: {
    label: "Dil",
    tr: "Türkçe",
    en: "English",
  },
  landing: {
    eyebrow: "Açık kaynak · TR/EN · alıntıya dayalı",
    thesis:
      "Bir RAG sistemi, ancak “bu bilgi bu belgede yok” diyebildiği kadar güvenilirdir.",
    lede: "BioPolicy sigorta poliçeleri ve hukuki sözleşmeler hakkındaki soruları yanıtlar, dayandığı maddeyi belgenin üzerinde tam olarak gösterir ve belge cevabı içermiyorsa cevap vermeyi reddeder.",
    ctaPrimary: "Örnek bir poliçeyle deneyin",
    ctaSecondary: "Ölçümleri okuyun",
    numbersTitle: "70 soruluk değerlendirme kümesinde ölçüldü",
    numbersNote:
      "Bu sayıların hepsi python -m eval.run_eval komutunun çıktısıdır; hiçbiri elle yazılmadı. Hoşa gitmeyen sonuçlar da raporda duruyor.",
    numbers: {
      refusal: "Doğru ret oranı",
      refusalNote: "Cevabı belgede olmayan 21 sorunun tamamı reddedildi",
      falseRefusal: "Yanlış ret oranı",
      falseRefusalNote: "Cevaplanabilir 49 sorudan 1'i gereksiz yere reddedildi",
      citations: "Geçerli alıntı",
      citationsNote: "Sunulan 67 alıntının tamamı belgede bulundu",
      recall: "Recall@8",
      recallNote: "Beklenen tüm maddeler modele ulaşan parçalar içinde",
    },
    howTitle: "Nasıl çalışıyor",
    how: [
      {
        title: "Belge ayrıştırılır",
        body: "Metin, tablolar ve her satırın sayfa koordinatları çıkarılır; taranmış sayfalar OCR'dan geçer. Her parça hangi maddenin altında olduğunu bilir, bu yüzden alıntı sayfadaki yerine geri götürülebilir.",
      },
      {
        title: "İki arama birlikte koşar",
        body: "Anlamsal vektör araması ile tam sözcük araması aynı anda çalışır ve sonuçlar RRF ile birleştirilir. Biri “sel hasarı”nı bulur, diğeri “Madde 4.2”yi; tek başına ikisi de yetmez.",
      },
      {
        title: "Cevap belgeye bağlanır",
        body: "Model yalnızca getirilen parçalardan cevap üretir. Sonrasında her alıntının belgede gerçekten geçtiği doğrulanır ve cevap kendi kaynağına karşı ayrıca kontrol edilir. Geçemeyen cevap gösterilmez.",
      },
    ],
    limitsTitle: "Bu sistemin yapmadıkları",
    limits: [
      "Bu bir hukuki ya da sigortacılık tavsiyesi değildir. Bir poliçenin sizin durumunuzda ne anlama geldiğini söyleyemez; yalnızca metinde ne yazdığını gösterir.",
      "Örnek belgeler bu proje için yazılmış sentetik metinlerdir. Gerçek bir poliçe değildir ve gerçek bir şirketi temsil etmez.",
      "Ölçümler 70 soruluk tek bir küme üzerinde yapıldı. Küçük bir kümedir; genel bir kalite iddiası değil, ne ölçtüğü belli olan bir sayıdır.",
      "Alıntı bağlama ve kendi kendini doğrulama mekanizmaları bu derlemde hiçbir kararı değiştirmedi ve maliyeti ~%55 artırdı. Bu da raporda yazıyor.",
    ],
    footerNote:
      "Yüklenen belgeler ve sorular kalıcı olarak saklanmaz; belgeler 24 saat sonra otomatik silinir.",
  },
  workspace: {
    documents: "Örnek belgeler",
    documentsNote:
      "Üçü de bu proje için yazılmış sentetik metinlerdir. Biri bilerek taranmış (OCR) olarak hazırlandı.",
    lang: { tr: "Türkçe", en: "İngilizce" },
    sourceType: { native: "dijital metin", scanned: "taranmış · OCR" },
    pages: "sayfa",
    loadingDocuments: "Belgeler yükleniyor…",
    loadDocumentsFailed:
      "Belgeler alınamadı. API çalışmıyor olabilir; sayfayı yenilemeyi deneyin.",
    emptyTitle: "Bir soru sorun",
    emptyBody:
      "Cevap belgedeyse maddesiyle birlikte gösterilir. Değilse sistem uydurmaz, reddeder — ikincisini de deneyin.",
    suggestions: "Örnek sorular",
    askPlaceholder: "Bu belge hakkında bir soru sorun…",
    ask: "Sor",
    asking: "Bekleyin…",
    stop: "Durdur",
    stages: {
      retrieval: "Belge aranıyor",
      answering: "Cevap yazılıyor",
      verifying: "Cevap belgeye karşı kontrol ediliyor",
    },
    stageNote: "Cevap, tüm kontroller bittikten sonra tek seferde gelir.",
    chunksFound: "parça bulundu",
    rewritten: "Sorgu yeniden yazıldı",
    answerTitle: "Cevap",
    refusedTitle: "Bu belgede yok",
    suppressedTitle: "Cevap gösterilmedi",
    suppressedBody:
      "Bir cevap üretildi ama kontrolleri geçemedi, bu yüzden gösterilmiyor.",
    citations: "Dayanak",
    citationsNone: "Alıntı yok",
    exact: "birebir alıntı",
    fuzzy: "yaklaşık eşleşme",
    fuzzyTitle:
      "Alıntı belgede birebir bulunamadı; aynı madde olarak eşleştirildi.",
    page: "s.",
    confidence: "Güven",
    confidenceValue: { high: "yüksek", medium: "orta", low: "düşük" },
    groundedness: "Dayanak skoru",
    verified: "Kendi kaynağına karşı doğrulandı",
    unverified: "Doğrulama çalıştırılamadı",
    caveats: "Kayıtlar",
    droppedCitations: "alıntı belgede bulunamadığı için atıldı",
    cost: "maliyet",
    costNote:
      "Yalnızca Anthropic ücretlendirmesi. Gömme ve sorgu yeniden yazma için kullanılan Google modellerinin fiyatı bu projede doğrulanmadığı için toplama katılmıyor.",
    errorTitle: "Bir şeyler ters gitti",
    errorBody: "Başarısız bir cevap için ücretlendirme yapılmaz.",
    viewerHint: "Bir alıntıya tıklayın, belgede yerini göstersin.",
    viewerLoading: "Belge açılıyor…",
    viewerFailed: "Belge görüntülenemedi.",
    noDocument: "Soldan bir belge seçin.",
    disclaimer:
      "Hukuki veya sigortacılık tavsiyesi değildir. Belgeler sentetiktir.",
  },
  evaluation: {
    title: "Değerlendirme",
    lede: "Bu sayfa depodaki eval/report.md dosyasını olduğu gibi gösterir. Rapor python -m eval.run_eval komutuyla, canlı modeller ve canlı veritabanı üzerinde üretilir.",
    missing:
      "Rapor bu derlemede bulunamadı. Depoda eval/report.md dosyasına bakabilirsiniz.",
    regenerate: "Yeniden üretmek için",
  },
  footer: {
    disclaimer:
      "BioPolicy bir portföy projesidir. Hukuki ya da sigortacılık tavsiyesi vermez.",
    retention: "Belgeler 24 saat sonra otomatik silinir",
    license: "MIT lisanslı",
  },
};

type Dictionary = typeof tr;

const en: Dictionary = {
  meta: {
    title: "BioPolicy — what your policy actually says",
    description:
      "Question answering over insurance policies and legal contracts that binds every answer to a clause in the document, and refuses when the document does not say.",
  },
  nav: {
    workspace: "Try it",
    evaluation: "Evaluation",
    source: "Source",
    home: "Home",
  },
  language: {
    label: "Language",
    tr: "Türkçe",
    en: "English",
  },
  landing: {
    eyebrow: "Open source · TR/EN · citation-grounded",
    thesis:
      "A RAG system is only as trustworthy as its ability to say “that isn't in this document.”",
    lede: "BioPolicy answers questions about insurance policies and legal contracts, shows you the exact clause it relied on inside the document, and refuses to answer when the document does not contain one.",
    ctaPrimary: "Try it on a sample policy",
    ctaSecondary: "Read the numbers",
    numbersTitle: "Measured on a 70-question evaluation set",
    numbersNote:
      "Every figure is the output of python -m eval.run_eval. None are hand-written, and the unflattering ones are still in the report.",
    numbers: {
      refusal: "Refusal accuracy",
      refusalNote: "All 21 questions the document cannot answer were refused",
      falseRefusal: "False-refusal rate",
      falseRefusalNote: "1 of 49 answerable questions was refused needlessly",
      citations: "Citation validity",
      citationsNote: "All 67 offered citations were found in the document",
      recall: "Recall@8",
      recallNote: "Every expected clause reached the model, not merely the index",
    },
    howTitle: "How it works",
    how: [
      {
        title: "The document is parsed",
        body: "Text, tables and the page coordinates of every line are extracted; scanned pages go through OCR. Each chunk knows which article it sits under, which is what lets a citation point back at its place on the page.",
      },
      {
        title: "Two searches run together",
        body: "Semantic vector search and exact keyword search run at once and are fused with RRF. One finds “flood damage”, the other finds “Article 4.2”; neither is sufficient alone.",
      },
      {
        title: "The answer is bound to the document",
        body: "The model may only answer from the retrieved chunks. Afterwards every quote is checked against the text it claims to come from, and the answer is verified against its own source. An answer that fails is never shown.",
      },
    ],
    limitsTitle: "What this system does not do",
    limits: [
      "This is not legal or insurance advice. It cannot tell you what a policy means for your situation — only what the text says.",
      "The sample documents are synthetic, written for this project. They are not real policies and do not represent any real company.",
      "The numbers come from a single 70-question set. That is small; it is a figure with a known scope, not a general claim about quality.",
      "Citation binding and self-verification changed no decisions on this corpus and added about 55% to the cost. That is in the report too.",
    ],
    footerNote:
      "Questions and uploaded documents are not kept: documents are deleted automatically after 24 hours.",
  },
  workspace: {
    documents: "Sample documents",
    documentsNote:
      "All three are synthetic, written for this project. One is deliberately a scan, so OCR is on the critical path.",
    lang: { tr: "Turkish", en: "English" },
    sourceType: { native: "digital text", scanned: "scanned · OCR" },
    pages: "pages",
    loadingDocuments: "Loading documents…",
    loadDocumentsFailed:
      "Could not load the documents. The API may be down; try reloading.",
    emptyTitle: "Ask a question",
    emptyBody:
      "If the answer is in the document, you get it with the clause it came from. If it is not, the system refuses instead of inventing one — try that too.",
    suggestions: "Try one of these",
    askPlaceholder: "Ask something about this document…",
    ask: "Ask",
    asking: "Working…",
    stop: "Stop",
    stages: {
      retrieval: "Searching the document",
      answering: "Drafting an answer",
      verifying: "Checking the answer against the document",
    },
    stageNote: "The answer arrives at once, after every check has run.",
    chunksFound: "chunks found",
    rewritten: "Query was rewritten",
    answerTitle: "Answer",
    refusedTitle: "Not in this document",
    suppressedTitle: "Answer withheld",
    suppressedBody:
      "An answer was produced but did not pass the checks, so it is not being shown.",
    citations: "Evidence",
    citationsNone: "No citations",
    exact: "verbatim quote",
    fuzzy: "approximate match",
    fuzzyTitle:
      "The quote was not found character-for-character; it was matched to the same clause.",
    page: "p.",
    confidence: "Confidence",
    confidenceValue: { high: "high", medium: "medium", low: "low" },
    groundedness: "Groundedness",
    verified: "Verified against its own source",
    unverified: "Verification could not run",
    caveats: "On the record",
    droppedCitations: "citations were dropped for not appearing in the document",
    cost: "cost",
    costNote:
      "Anthropic billing only. The Google models used for embedding and query rewriting are excluded because their pricing was not verified for this project.",
    errorTitle: "Something went wrong",
    errorBody: "Nothing is charged for a failed answer.",
    viewerHint: "Click a citation to see where it sits in the document.",
    viewerLoading: "Opening the document…",
    viewerFailed: "The document could not be displayed.",
    noDocument: "Pick a document on the left.",
    disclaimer: "Not legal or insurance advice. The documents are synthetic.",
  },
  evaluation: {
    title: "Evaluation",
    lede: "This page renders eval/report.md from the repository verbatim. The report is produced by python -m eval.run_eval against live models and the live database.",
    missing:
      "The report was not found in this build. It lives at eval/report.md in the repository.",
    regenerate: "To regenerate it",
  },
  footer: {
    disclaimer:
      "BioPolicy is a portfolio project. It does not give legal or insurance advice.",
    retention: "Documents are deleted automatically after 24 hours",
    license: "MIT licensed",
  },
};

export const dictionaries: Record<Locale, Dictionary> = { tr, en };

export type { Dictionary };

/**
 * Suggested questions, keyed by sample filename.
 *
 * The third of each set is deliberately unanswerable. A demo that only shows
 * successful answers hides the behaviour this project is actually about.
 */
export const SUGGESTIONS: Record<string, Record<Locale, string[]>> = {
  "konut-sigortasi-tr.pdf": {
    tr: [
      "Deprem teminatı için muafiyet oranı nedir?",
      "Sel ve su baskını hangi durumlarda kapsam dışında?",
      "Evcil hayvanımın verdiği zarar karşılanıyor mu?",
    ],
    en: [
      "What is the deductible for earthquake cover?",
      "When is flood damage excluded?",
      "Is damage caused by my pet covered?",
    ],
  },
  "commercial-property-liability-en.pdf": {
    tr: [
      "İşletme kesintisi teminatının bekleme süresi ne kadar?",
      "Hangi durumlar genel sorumluluk kapsamı dışında?",
      "Siber saldırı sonucu veri kaybı teminat altında mı?",
    ],
    en: [
      "What is the waiting period for business interruption cover?",
      "Which events are excluded from general liability?",
      "Is data loss from a cyber attack covered?",
    ],
  },
  "tamamlayici-saglik-tr-scanned.pdf": {
    tr: [
      "Ayakta tedavi için yıllık limit nedir?",
      "Bekleme süresi olan durumlar hangileri?",
      "Diş tedavisi kapsama dahil mi?",
    ],
    en: [
      "What is the annual limit for outpatient treatment?",
      "Which conditions have a waiting period?",
      "Is dental treatment included?",
    ],
  },
};

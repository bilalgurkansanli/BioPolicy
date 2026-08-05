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
    lede: "Poliçenizi sorun: cevabı dayandığı maddeyle birlikte belgenin üzerinde gösterir, belgede yoksa uydurmaz.",
    ctaPrimary: "Örnek bir poliçeyle deneyin",
    ctaSecondary: "Ölçümleri okuyun",
    ctaNote: "Kayıt gerekmez · Örnek belgeler hazır · 30 saniyede ilk cevap",
    numbersTitle: "70 soruluk değerlendirme kümesinde ölçüldü",
    numbersNote: "Sayıların hepsi eval çıktısıdır, elle yazılmadı.",
    numbers: {
      refusal: "Doğru ret oranı",
      falseRefusal: "Yanlış ret oranı",
      citations: "Geçerli alıntı",
      recall: "Recall@8",
    },
    howTitle: "Üç adımda",
    how: [
      {
        title: "Belge ayrıştırılır",
        body: "Metin, tablolar ve satır koordinatları çıkarılır; taranmış sayfalar OCR'dan geçer.",
      },
      {
        title: "İki arama birlikte koşar",
        body: "Anlamsal arama “sel hasarı”nı bulur, sözcük araması “Madde 4.2”yi; ikisi birleştirilir.",
      },
      {
        title: "Cevap belgeye bağlanır",
        body: "Her alıntı belgede doğrulanır. Doğrulamayı geçemeyen cevap hiç gösterilmez.",
      },
    ],
    closingTitle: "Bir belge seçin, ilk sorunuzu sorun.",
    closingBody:
      "Cevabı maddesiyle görürsünüz ya da sistem bilmediğini söyler. İkisini de deneyin.",
  },
  workspace: {
    documents: "Örnek belgeler",
    panes: { documents: "Belgeler", chat: "Cevap", viewer: "Belge" },
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
    approximateRegion: "yaklaşık bölge",
    viewerLoading: "Belge açılıyor…",
    viewerFailed: "Belge görüntülenemedi.",
    noDocument: "Soldan bir belge seçin.",
    disclaimer:
      "Hukuki veya sigortacılık tavsiyesi değildir. Belgeler sentetiktir.",
  },
  upload: {
    title: "Kendi belgeniz",
    drop: "PDF'i buraya bırakın",
    choose: "Dosya seçin",
    limits: "En fazla {mb} MB · yalnızca PDF · {hours} saat sonra silinir",
    yours: "Yüklediğiniz belgeler",
    uploading: "Yükleniyor",
    processing: "İşleniyor",
    failedTitle: "Yüklenemedi",
    remove: "Sil",
    confirmRemove: "Silinsin mi?",
    confirmYes: "Evet, sil",
    confirmNo: "Vazgeç",
    notPdf: "Yalnızca PDF dosyaları kabul ediliyor.",
    tooLarge: "Dosya çok büyük.",
    stages: {
      queued: "Sıraya alındı",
      parsing: "Ayrıştırılıyor",
      ocr: "Metin tanınıyor (OCR)",
      chunking: "Parçalara ayrılıyor",
      embedding: "Gömülüyor",
      ready: "Hazır",
      failed: "Başarısız",
    },
    authDisabledTitle: "Oturum açılamıyor",
    authDisabled:
      "Bu Supabase projesinde anonim girişler kapalı. Panelde Authentication → Sign In / Providers → Anonymous sign-ins açıldığında yükleme çalışır.",
    signInFailed: "Oturum başlatılamadı. Sayfayı yenileyip tekrar deneyin.",
    quotaTitle: "Günlük sınıra ulaştınız",
    budgetTitle: "Demo şimdilik kapalı",
    retentionNote:
      "Yüklediğiniz belge {hours} saat sonra otomatik silinir; dilediğiniz an kendiniz de silebilirsiniz.",
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
    lede: "Ask your policy: every answer comes with the clause it rests on, shown in the document — and nothing is invented when the document does not say.",
    ctaPrimary: "Try it on a sample policy",
    ctaSecondary: "Read the numbers",
    ctaNote: "No sign-up · Sample documents ready · First answer in 30 seconds",
    numbersTitle: "Measured on a 70-question evaluation set",
    numbersNote: "Every figure is eval output, not hand-written.",
    numbers: {
      refusal: "Refusal accuracy",
      falseRefusal: "False-refusal rate",
      citations: "Citation validity",
      recall: "Recall@8",
    },
    howTitle: "In three steps",
    how: [
      {
        title: "The document is parsed",
        body: "Text, tables and line coordinates are extracted; scanned pages go through OCR.",
      },
      {
        title: "Two searches run together",
        body: "Semantic search finds “flood damage”, keyword search finds “Article 4.2”; the two are fused.",
      },
      {
        title: "The answer is bound to the document",
        body: "Every quote is verified against the text. An answer that fails is never shown.",
      },
    ],
    closingTitle: "Pick a document, ask your first question.",
    closingBody:
      "You either get the answer with its clause, or the system tells you it does not know. Try both.",
  },
  workspace: {
    documents: "Sample documents",
    panes: { documents: "Documents", chat: "Answer", viewer: "Document" },
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
    approximateRegion: "approximate region",
    viewerLoading: "Opening the document…",
    viewerFailed: "The document could not be displayed.",
    noDocument: "Pick a document on the left.",
    disclaimer: "Not legal or insurance advice. The documents are synthetic.",
  },
  upload: {
    title: "Your own document",
    drop: "Drop a PDF here",
    choose: "Choose a file",
    limits: "Up to {mb} MB · PDF only · deleted after {hours} hours",
    yours: "Your uploads",
    uploading: "Uploading",
    processing: "Processing",
    failedTitle: "Upload failed",
    remove: "Delete",
    confirmRemove: "Delete this?",
    confirmYes: "Yes, delete",
    confirmNo: "Cancel",
    notPdf: "Only PDF files are accepted.",
    tooLarge: "That file is too large.",
    stages: {
      queued: "Queued",
      parsing: "Parsing",
      ocr: "Recognising text (OCR)",
      chunking: "Chunking",
      embedding: "Embedding",
      ready: "Ready",
      failed: "Failed",
    },
    authDisabledTitle: "Cannot start a session",
    authDisabled:
      "Anonymous sign-ins are switched off for this Supabase project. Uploading works once Authentication → Sign In / Providers → Anonymous sign-ins is enabled.",
    signInFailed: "Could not start a session. Reload the page and try again.",
    quotaTitle: "You have reached the daily limit",
    budgetTitle: "The demo is paused",
    retentionNote:
      "Your document is deleted automatically after {hours} hours, and you can delete it yourself at any time.",
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

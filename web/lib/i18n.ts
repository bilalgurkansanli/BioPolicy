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
    source: "GitHub",
    home: "Ana sayfa",
    backHome: "Ana sayfaya dön",
    backToProjects: "Projelere dön",
  },
  language: {
    label: "Dil",
    tr: "Türkçe",
    en: "English",
  },
  landing: {
    eyebrow: "Açık kaynak · sayıları yayımlanmış · TR/EN",
    // Two sentences, authored as two lines rather than left to `text-balance`.
    // The balancer optimises for even line widths, not for meaning, and on this
    // string it breaks mid-sentence — the English reads "Ask your policy. Get /
    // the clause, not a guess", which is the dangling word the balancer exists
    // to prevent. A line per sentence is the couplet the tagline is written as.
    thesis: ["Poliçenize sorun.", "Tahmin değil, maddenin kendisini alın."],
    lede: "Her cevap, dayandığı maddeyle birlikte belgenin üzerinde işaretli gelir. “Bu bilgi bu belgede yok” da bir cevaptır.",
    ctaPrimary: "Örnek bir poliçeyle deneyin",
    ctaSecondary: "Nasıl çalışıyor",
    ctaNote: "Örnekler hesapsız okunur · Soru sormak için Google ile giriş · Günde 3 soru",
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
    injection: {
      badge: "talimat metni",
      title: "Bu belge, kendisini okuyan sisteme talimat veriyor",
      body:
        "Belgenin içine, bir yapay zekâ sistemine yönelik yazılmış {count} " +
        "metin parçası yerleştirilmiş. Cevaplar yine belgenin gerçek " +
        "maddelerinden üretiliyor — bu metinler talimat olarak değil, " +
        "belgenin içeriği olarak ele alınıyor.",
      show: "Göster",
      hide: "Gizle",
      footer:
        "Bulunanları kendi PDF'inizde arayıp görebilirsiniz. Belgeyi hazırlayan " +
        "kişinin niyetine dair bir şey söylemiyoruz; yalnızca metinde ne " +
        "olduğunu bildiriyoruz.",
      rules: {
        rule_override: "kuralları iptal etmeye çalışan metin",
        addresses_the_model: "okuyucuya değil, yapay zekâya seslenen metin",
        forged_context: "sistemin kendi biçimini taklit eden metin",
        orders_an_omission: "bir maddeyi gizlemeyi emreden metin",
        impersonates_us: "BioPolicy ekibi adına yazılmış gibi görünen metin",
      },
    },
    profile: {
      title: "Poliçe künyesi",
      lede:
        "Soru sormadan, belgenin tamamı sabit bir şemaya çıkarılır. Her satır, " +
        "dayandığı maddeye bağlıdır — tıklayın, belgede görün.",
      build: "Belgeyi şemaya çıkar",
      building: "Belge okunuyor…",
      buildNote: "Belge başına bir kez çalışır, sonra herkes için hazırdır.",
      signInToBuild: "Bunun için giriş yapmanız gerekiyor.",
      buildFailed: "Künye çıkarılamadı. Biraz sonra tekrar deneyin.",
      show: "Göster",
      hide: "Gizle",
      fields: {
        insured: "Sigortalı",
        policy_period: "Poliçe süresi",
        territorial_scope: "Coğrafi kapsam",
        covered_peril: "Teminatlar",
        sub_limit: "Alt limitler",
        deductible: "Muafiyetler",
        waiting_period: "Bekleme süreleri",
        notification_deadline: "İhbar süreleri",
        exclusion: "İstisnalar",
      },
      absentTitle: "Bu belgede yer almayanlar",
      absentNote:
        "Bu başlıklarda tek bir madde bulunamadı. Bir sigorta poliçesinde " +
        "genellikle bulunurlar — bu belgede bulunmuyorlar.",
      emptyTitle: "Şemadaki hiçbir alan dolmadı",
      emptyBody:
        "Belge okundu ve sabit alanların hiçbirini karşılayan bir madde " +
        "bulunamadı.",
      // Coverage is stated rather than assumed: a slot nobody read must never
      // look like a slot the document is silent on.
      partialTitle: "Belgenin tamamı okunmadı",
      partialBody:
        "{seen} / {total} parça okundu. Okunmayan bölümlerde bu başlıklara ait " +
        "maddeler bulunabilir; “yer almayanlar” listesi bu yüzden gösterilmiyor.",
      failedTitle: "Bazı bölümler okunamadı",
      failedBody:
        "{count} bölüm sağlayıcı hatası nedeniyle okunamadı. Eksik olan, " +
        "belgede olmayan demek değildir.",
      dropped: "{count} satır, alıntısı belgede doğrulanamadığı için gösterilmiyor.",
    },
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
  account: {
    signIn: "Google ile giriş yap",
    signInLink: "Giriş yap",
    signInTitle: "Devam etmek için giriş yapın",
    signInBody:
      "Soru sormak ve belge yüklemek için Google hesabınızla giriş yapmanız gerekiyor. Örnek belgeleri girmeden de inceleyebilirsiniz.",
    signInWhy:
      "Neden: her soru gerçek bir model çağrısı ve gerçek bir fatura. Giriş, günlük sınırın kime ait olduğunu belirliyor.",
    signOut: "Çıkış yap",
    signOutTitle: "Çıkış yapılsın mı?",
    signOutBody:
      "Sohbetleriniz ve belgeleriniz hesabınızda kalır; tekrar giriş " +
      "yaptığınızda kaldığınız yerden devam edersiniz.",
    signOutCancel: "Vazgeç",
    signOutConfirm: "Çıkış yap",
    signingOut: "Çıkılıyor…",
    providerDisabledTitle: "Google girişi kapalı",
    providerDisabled:
      "Bu Supabase projesinde Google sağlayıcısı açık değil. Panelde Authentication → Sign In / Providers → Google açıldığında giriş çalışır.",
    signInFailed: "Giriş başlatılamadı. Sayfayı yenileyip tekrar deneyin.",
    remaining: "Bugün kalan",
    questions: "soru",
    documents: "belge",
    unlimited: "sınırsız",
    exhaustedTitle: "Günlük soru hakkınız bitti",
    exhaustedBody:
      "Bugün {limit} sorunun tamamını kullandınız. Hak, UTC gece yarısı yenilenir. Belgeleri ve geçmiş sohbetlerinizi incelemeye devam edebilirsiniz.",
    menu: "Hesabınız",
    deleteAccount: "Hesabımı sil",
    deleteTitle: "Hesabınız silinsin mi?",
    deleteBody:
      "Yüklediğiniz belgeler, sohbetleriniz ve hesabınız kalıcı olarak silinir. Bu işlem geri alınamaz.",
    deleteConfirm: "Evet, hesabımı sil",
    deleteCancel: "Vazgeç",
    deleting: "Siliniyor…",
    deleteFailed:
      "Hesap silinemedi. Belgeleriniz ve hesabınız duruyor; birazdan tekrar deneyin.",
  },
  cookies: {
    bannerBody:
      "Sitede nerede takıldığınızı görmek için bir ölçüm çerezi kullanıyoruz. Kabul etmezseniz site aynı şekilde çalışır.",
    bannerLink: "Ayrıntılar",
    accept: "Kabul et",
    decline: "Sadece gerekli olanlar",
    reset: "Seçimimi değiştir",
  },
  signin: {
    title: "Poliçenizi sorun",
    lede: "Devam etmek için Google hesabınızla girin. Örnek belgeleri girmeden de inceleyebilirsiniz.",
    why: "Her soru gerçek bir model çağrısı ve gerçek bir fatura. Giriş, günlük hakkın kime ait olduğunu belirliyor — başka bir sebebi yok.",
    browse: "Girmeden incele",
    signedOut: "Çıkış yaptınız.",
    legalNote:
      "Giriş yaparak aşağıdakileri ve ölçüm çerezini kabul etmiş olursunuz.",
    updated: "Güncelleme: 5 Ağustos 2026",
    privacyTitle: "Gizlilik Politikası",
    privacy: [
      {
        title: "Hesabınız",
        body: "Google ile girdiğinizde adınız, e-posta adresiniz ve profil fotoğrafınız alınır. Başka hiçbir bilgi istenmez.",
      },
      {
        title: "Yüklediğiniz belgeler",
        body: "Yalnızca siz görebilirsiniz ve 24 saat sonra otomatik silinir. Dilediğiniz an kendiniz de silebilirsiniz.",
      },
      {
        title: "Sorularınız",
        body: "Sorunuz ve belgenin ilgili bölümleri, cevabı üretmek için yapay zekâ modellerine gönderilir. Model eğitimi için kullanılmaz.",
      },
      {
        title: "Paylaşım",
        body: "Verileriniz satılmaz, reklam için kullanılmaz, üçüncü kişilere aktarılmaz.",
      },
      {
        title: "Silme",
        body: "Hesabınızı profil menüsünden silebilirsiniz. Belgeleriniz, sohbetleriniz ve hesabınız birlikte gider.",
      },
    ],
    cookiesTitle: "Çerezler",
    cookiesDoc: [
      {
        title: "Oturumunuz",
        body: "Girişinizi açık tutmak için tarayıcınızın hafızası kullanılır. Bu bir izleme aracı değildir ve kapatılamaz; olmazsa giriş yapılamaz.",
      },
      {
        title: "Ölçüm (Microsoft Clarity)",
        body: "Hangi sayfaların kullanıldığını ve insanların nerede takıldığını görmek için. Kabul etmezseniz hiç yüklenmez ve site aynı şekilde çalışır.",
      },
      {
        title: "Kaydedilmeyenler",
        body: "Sorularınız, aldığınız cevaplar ve belgeleriniz ölçümün dışında tutuldu. Yazdığınız metin de maskelenir.",
      },
      {
        title: "Fikrinizi değiştirirseniz",
        body: "Aşağıdaki düğme seçiminizi sıfırlar; soru yeniden sorulur ve reddederseniz ölçüm bir daha yüklenmez.",
      },
    ],
    termsTitle: "Kullanım Koşulları",
    terms: [
      {
        title: "Tavsiye değildir",
        body: "BioPolicy hukuki ya da sigortacılık tavsiyesi vermez. Bir poliçenin sizin durumunuzda ne anlama geldiğini söyleyemez; yalnızca metinde ne yazdığını gösterir.",
      },
      {
        title: "Örnek belgeler gerçek değildir",
        body: "Bu proje için yazılmış sentetik metinlerdir ve hiçbir şirketi temsil etmez.",
      },
      {
        title: "Günlük hak",
        body: "Her hesabın günlük soru ve belge hakkı vardır. Demo, gerçek bir fatura ürettiği için sınırlıdır.",
      },
      {
        title: "Garanti yok",
        body: "Bu bir portföy projesidir. Kesintisiz çalışacağı ya da her cevabın doğru olacağı garanti edilmez.",
      },
    ],
  },
  tour: {
    start: "Reddedişini izleyin (30 saniye)",
    label: "Kayıtlı gösterim",
    close: "Kapat",
    next: "Devam",
    toEval: "Ölçümlere bakın",
    recorded: "Kayıt — soru hakkınızdan düşmez",
    step1Title: "Cevabı belgede olmayan bir soru soruluyor",
    step1Body:
      "Konut poliçesine soruluyor: “Evcil hayvanımın komşuya verdiği zarar karşılanıyor mu?” Poliçe bu konuda hiçbir şey söylemiyor — ama yakın maddeler var.",
    step2Title: "Sistem yakın maddeleri buluyor",
    step2Body:
      "Arama, evcil hayvanların geçtiği tek maddeyi getiriyor. Bir dil modeli için buradan “evet/hayır” uydurmak çok kolay: madde gerçek, alıntı gerçek, cümle kulağa doğru gelir.",
    step2Quote:
      "Madde 4.5 — Evcil hayvanların sigortalı eşyaya verdiği zararlar teminat dışıdır.",
    step3Title: "Ve cevap vermiyor",
    step3Body:
      "Bu madde sigortalının kendi eşyası hakkında; komşuya verilen zarar farklı bir konu. Sistem yakın bir maddeden çıkarım yapmak yerine “bu belgede yok” diyor. Ürünün tamamı bu davranışın etrafında kurulu — ve 70 soruluk kümede ölçülmüş hâli ölçüm sayfasında.",
  },
  conversations: {
    title: "Sohbetlerim",
    empty: "Henüz sohbetiniz yok.",
    newChat: "Yeni sohbet",
    documentGone: "belge silindi",
    remove: "Sil",
    confirmRemove: "Sohbet silinsin mi?",
    confirmYes: "Evet, sil",
    confirmNo: "Vazgeç",
    loadFailed: "Sohbet açılamadı.",
    messages: "mesaj",
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
    quotaTitle: "Günlük sınıra ulaştınız",
    budgetTitle: "Demo şimdilik kapalı",
    retentionNote:
      "Yüklediğiniz belge {hours} saat sonra otomatik silinir; dilediğiniz an kendiniz de silebilirsiniz. O belgeyle yaptığınız sohbet de belgeyle birlikte gider.",
  },
  evaluation: {
    title: "Değerlendirme",
    lede: "Bu sayfa depodaki eval/report.md dosyasını olduğu gibi gösterir. Rapor python -m eval.run_eval komutuyla, canlı modeller ve canlı veritabanı üzerinde üretilir.",
    missing:
      "Rapor bu derlemede bulunamadı. Depoda eval/report.md dosyasına bakabilirsiniz.",
    regenerate: "Yeniden üretmek için",
    languageNote:
      "Bu derlemenin Türkçe raporu üretilmemiş, o yüzden İngilizcesi gösteriliyor. Türkçesi için: python -m eval.run_eval --arm rerender",
    spendTitle: "Bu demo şimdiye kadar ne harcadı",
    spendTotal: "Toplam",
    spendPerQuestion: "Soru başına",
    spendQuestions: "Cevaplanan soru",
    spendBudget: "Bütçe tavanı",
    spendCaveat:
      "Yalnızca Anthropic ücretlendirmesi: sağlayıcı çağrılarının {share} kadarı fiyatlandırılabiliyor. Gömme ve sorgu yeniden yazma için kullanılan Google modellerinin fiyatı bu projede doğrulanmadı, o yüzden gerçek fatura bu rakamdan yüksek.",
    historyTitle: "Sayılar zaman içinde",
    historyNote:
      "Yayımlanan yapılandırma (katı prompt + mekanizmalar), 70 soruluk küme üzerinde. Her nokta bir koşum.",
    historyEmpty:
      "Henüz kayıt yok. Geçmiş, ölçüm koştukça birikir; ilk koşum bu özellikten sonra yapılacak.",
    historyTooShort: "Tek bir koşum var. İki nokta olmadan çizilecek bir eğilim yok.",
    historySeries: {
      balanced_accuracy: "Dengeli doğruluk",
      refusal_accuracy: "Doğru ret",
      false_refusal_rate: "Yanlış ret",
    },
  },
  footer: {
    disclaimer:
      "BioPolicy bir portföy projesidir. Hukuki ya da sigortacılık tavsiyesi vermez.",
    retention: "Belgeler 24 saat sonra silinir · sohbetler hesabınızda kalır",
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
    source: "GitHub",
    home: "Home",
    backHome: "Back to home",
    backToProjects: "Back to projects",
  },
  language: {
    label: "Language",
    tr: "Türkçe",
    en: "English",
  },
  landing: {
    eyebrow: "Open source · every number published · TR/EN",
    thesis: ["Ask your policy.", "Get the clause, not a guess."],
    lede: "Every answer arrives with its clause, highlighted in the document. “That isn't in this document” is an answer too.",
    ctaPrimary: "Try it on a sample policy",
    ctaSecondary: "How it works",
    ctaNote: "Samples readable without an account · Google sign-in to ask · 3 questions a day",
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
    injection: {
      badge: "instruction text",
      title: "This document gives orders to the system reading it",
      body:
        "{count} passage(s) inside this document are written at an AI system " +
        "rather than at a reader. Answers are still produced from the real " +
        "clauses — that text is treated as the document's content, not as " +
        "instructions.",
      show: "Show",
      hide: "Hide",
      footer:
        "You can find each passage in your own PDF and judge it yourself. This " +
        "says nothing about what whoever prepared the document intended; it " +
        "reports only what the text contains.",
      rules: {
        rule_override: "text cancelling the reader's instructions",
        addresses_the_model: "text speaking to an AI rather than to a reader",
        forged_context: "text imitating the system's own format",
        orders_an_omission: "text ordering a clause to be left out",
        impersonates_us: "text claiming to come from the BioPolicy team",
      },
    },
    profile: {
      title: "Policy profile",
      lede:
        "The whole document read into a fixed schema, without asking anything. " +
        "Every row is bound to the clause it came from — click one to see it.",
      build: "Read this document into the schema",
      building: "Reading the document…",
      buildNote: "Runs once per document, then it is ready for everyone.",
      signInToBuild: "You need to be signed in for this.",
      buildFailed: "The profile could not be built. Try again shortly.",
      show: "Show",
      hide: "Hide",
      fields: {
        insured: "Insured",
        policy_period: "Policy period",
        territorial_scope: "Territorial scope",
        covered_peril: "Cover",
        sub_limit: "Sub-limits",
        deductible: "Deductibles",
        waiting_period: "Waiting periods",
        notification_deadline: "Notification deadlines",
        exclusion: "Exclusions",
      },
      absentTitle: "Not in this document",
      absentNote:
        "Not one clause was found under these headings. A policy usually has " +
        "them — this one does not.",
      emptyTitle: "No field in the schema was filled",
      emptyBody:
        "The document was read and no clause matched any of the fixed fields.",
      partialTitle: "The whole document was not read",
      partialBody:
        "{seen} of {total} passages were read. The rest may contain clauses " +
        "under these headings, which is why the “not in this document” list is " +
        "withheld.",
      failedTitle: "Some passages could not be read",
      failedBody:
        "{count} batch(es) failed at the provider. Missing is not the same as " +
        "absent from the document.",
      dropped: "{count} row(s) are not shown: their quote could not be verified.",
    },
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
  account: {
    signIn: "Sign in with Google",
    signInLink: "Sign in",
    signInTitle: "Sign in to continue",
    signInBody:
      "Asking questions and uploading documents needs a Google account. The sample documents are readable without one.",
    signInWhy:
      "Why: every question is a real model call against a real bill. Signing in is what the daily limit is counted against.",
    signOut: "Sign out",
    signOutTitle: "Sign out?",
    signOutBody:
      "Your conversations and documents stay on your account — signing back " +
      "in picks up where you left off.",
    signOutCancel: "Cancel",
    signOutConfirm: "Sign out",
    signingOut: "Signing out…",
    providerDisabledTitle: "Google sign-in is off",
    providerDisabled:
      "The Google provider is not enabled for this Supabase project. Sign-in works once Authentication → Sign In / Providers → Google is turned on.",
    signInFailed: "Could not start sign-in. Reload the page and try again.",
    remaining: "Left today",
    questions: "questions",
    documents: "documents",
    unlimited: "unlimited",
    exhaustedTitle: "You have used today's questions",
    exhaustedBody:
      "All {limit} of them. The allowance resets at midnight UTC. You can still read the documents and your earlier conversations.",
    menu: "Your account",
    deleteAccount: "Delete my account",
    deleteTitle: "Delete your account?",
    deleteBody:
      "Your uploaded documents, your conversations and your account are removed for good. This cannot be undone.",
    deleteConfirm: "Yes, delete my account",
    deleteCancel: "Cancel",
    deleting: "Deleting…",
    deleteFailed:
      "The account could not be deleted. Your documents and account are still there; try again shortly.",
  },
  cookies: {
    bannerBody:
      "We use one measurement cookie to see where people get stuck. Decline and the site works exactly the same.",
    bannerLink: "Details",
    accept: "Accept",
    decline: "Only what is needed",
    reset: "Change my choice",
  },
  signin: {
    title: "Ask your policy",
    lede: "Sign in with Google to continue. The sample documents are readable without an account.",
    why: "Every question is a real model call against a real bill. Signing in is what the daily allowance is counted against — that is the whole reason for it.",
    browse: "Look around first",
    signedOut: "You are signed out.",
    legalNote:
      "By signing in you accept the following, and the measurement cookie.",
    updated: "Updated: 5 August 2026",
    privacyTitle: "Privacy Policy",
    privacy: [
      {
        title: "Your account",
        body: "Signing in with Google gives us your name, email address and profile picture. Nothing else is asked for.",
      },
      {
        title: "Documents you upload",
        body: "Only you can see them, and they are deleted automatically after 24 hours. You can also delete them yourself at any time.",
      },
      {
        title: "Your questions",
        body: "Your question and the relevant parts of the document are sent to AI models to produce the answer. They are not used to train anything.",
      },
      {
        title: "Sharing",
        body: "Your data is not sold, not used for advertising, and not passed to third parties.",
      },
      {
        title: "Deleting",
        body: "You can delete your account from the profile menu. Your documents, your conversations and your account go together.",
      },
    ],
    cookiesTitle: "Cookies",
    cookiesDoc: [
      {
        title: "Your session",
        body: "Your browser's storage is used to keep you signed in. It is not a tracker and cannot be switched off; without it there is no sign-in.",
      },
      {
        title: "Measurement (Microsoft Clarity)",
        body: "To see which pages are used and where people get stuck. Decline and it is never loaded, and the site works exactly the same.",
      },
      {
        title: "What is not recorded",
        body: "Your questions, the answers you get and your documents are kept out of it. Anything you type is masked as well.",
      },
      {
        title: "If you change your mind",
        body: "The button below resets your choice: you are asked again, and declining means measurement is never loaded again.",
      },
    ],
    termsTitle: "Terms of Use",
    terms: [
      {
        title: "Not advice",
        body: "BioPolicy does not give legal or insurance advice. It cannot tell you what a policy means for your situation — only what the text says.",
      },
      {
        title: "The samples are not real",
        body: "They are synthetic documents written for this project and represent no real company.",
      },
      {
        title: "Daily allowance",
        body: "Each account has a daily allowance of questions and uploads. The demo is limited because it produces a real bill.",
      },
      {
        title: "No guarantees",
        body: "This is a portfolio project. It is not guaranteed to stay up, nor is every answer guaranteed to be right.",
      },
    ],
  },
  tour: {
    start: "Watch it refuse (30 seconds)",
    label: "Recorded walkthrough",
    close: "Close",
    next: "Next",
    toEval: "See the numbers",
    recorded: "A recording — it does not use one of your questions",
    step1Title: "A question the document cannot answer",
    step1Body:
      "The home policy is asked: “is damage my pet caused to a neighbour covered?” The policy says nothing about it — but it does have passages nearby.",
    step2Title: "The system finds the nearby clause",
    step2Body:
      "Search returns the one article that mentions pets at all. Inventing a yes or no from here is easy: the clause is real, the quote is real, and the sentence sounds right.",
    step2Quote:
      "Article 4.5 — Damage caused by pets to the insured contents is excluded.",
    step3Title: "And it declines to answer",
    step3Body:
      "That clause is about the policyholder's own contents; damage to a neighbour is a different subject. Rather than reason from an adjacent article, the system says it is not in this document. The whole product is built around that behaviour — and the evaluation page measures it over seventy questions.",
  },
  conversations: {
    title: "Your chats",
    empty: "No conversations yet.",
    newChat: "New chat",
    documentGone: "document deleted",
    remove: "Delete",
    confirmRemove: "Delete this chat?",
    confirmYes: "Yes, delete",
    confirmNo: "Cancel",
    loadFailed: "Could not open that conversation.",
    messages: "messages",
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
    quotaTitle: "You have reached the daily limit",
    budgetTitle: "The demo is paused",
    retentionNote:
      "Your document is deleted automatically after {hours} hours, and you can delete it yourself at any time. The conversation about it goes when it does.",
  },
  evaluation: {
    title: "Evaluation",
    lede: "This page renders eval/report.md from the repository verbatim. The report is produced by python -m eval.run_eval against live models and the live database.",
    missing:
      "The report was not found in this build. It lives at eval/report.md in the repository.",
    regenerate: "To regenerate it",
    languageNote:
      "No Turkish report was generated for this build, so the English one is shown.",
    spendTitle: "What this demo has spent",
    spendTotal: "Total",
    spendPerQuestion: "Per question",
    spendQuestions: "Questions answered",
    spendBudget: "Budget ceiling",
    spendCaveat:
      "Anthropic billing only: {share} of provider calls can be priced. The Google models used for embedding and query rewriting were never price-verified for this project, so the real bill is higher than this figure.",
    historyTitle: "The numbers over time",
    historyNote:
      "The shipped configuration (strict prompt + mechanisms) over the 70-question set. One point per run.",
    historyEmpty:
      "Nothing recorded yet. History accrues as the evaluation runs; the first entry lands after this feature.",
    historyTooShort: "One run so far. Two points are needed before there is a trend to draw.",
    historySeries: {
      balanced_accuracy: "Balanced accuracy",
      refusal_accuracy: "Refusal accuracy",
      false_refusal_rate: "False-refusal rate",
    },
  },
  footer: {
    disclaimer:
      "BioPolicy is a portfolio project. It does not give legal or insurance advice.",
    retention: "Documents deleted after 24 hours · chats kept in your account",
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

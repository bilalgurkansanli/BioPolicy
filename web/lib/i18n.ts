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

/**
 * What a visitor gets before anything is known about them.
 *
 * English, because it is the language the fewest people are locked out of.
 * Turkish is not a fallback here, it is a match: a browser that asks for
 * Turkish gets Turkish (see `lib/locale-store.ts`), and everybody else —
 * including a German or French browser, which used to land on Turkish — gets
 * a language they are more likely to read.
 *
 * This is also what the crawlers and the link previews see, since none of
 * them have a preference to read.
 */
export const DEFAULT_LOCALE: Locale = "en";

const tr = {
  meta: {
    title: "BioPolicy — belgenizde gerçekten ne yazıyor",
    description:
      "Sigorta poliçesi, sözleşme ya da herhangi bir PDF: her cevabı belgedeki maddeye bağlayan, belge cevabı içermiyorsa cevap vermeyi reddeden bir soru-cevap sistemi.",
    // What each route is called. Two consumers, deliberately sharing one
    // source: the browser tab, which `LocaleProvider` rewrites because page
    // metadata is resolved at build time and cannot follow a client-side
    // preference (ADR 011), and the heading on the legal pages, which reads
    // these rather than carrying its own copy. A tab that disagrees with the
    // `<h1>` under it is the drift this avoids.
    pages: {
      app: "Çalışma alanı",
      eval: "Değerlendirme",
      signin: "Giriş",
      privacy: "Gizlilik Bildirimi",
      terms: "Kullanım Koşulları",
      cookies: "Çerezler",
    },
  },
  nav: {
    workspace: "Deneyin",
    source: "GitHub",
    home: "Ana sayfa",
    backHome: "Ana sayfaya dön",
    // Two lengths for one link. The full sentence is what it should say — it
    // is an invitation to somewhere else, not a browser back button — but at
    // `md` the row has ~200px for it and the phrase needs all of them. The
    // short form carries the same meaning where the long one would push the
    // call-to-action off the end.
    backToProjects: "Diğer Projelerim için Tıklayınız",
    backToProjectsShort: "Diğer projelerim",
    menu: "Menü",
    // Read out as part of the link's name, never shown. A new tab is a change
    // of context, and a reader who cannot see it happen has to be told before
    // they follow the link — afterwards the back button no longer goes back.
    opensInNewTab: "yeni sekmede açılır",
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
    // string it breaks mid-sentence — the English reads "Ask your document. Get /
    // the clause, not a guess", which is the dangling word the balancer exists
    // to prevent. A line per sentence is the couplet the tagline is written as.
    thesis: ["Belgenize sorun.", "Tahmin değil, maddenin kendisini alın."],
    lede: "Poliçe, sözleşme, herhangi bir PDF. Her cevap dayandığı maddeyle birlikte belgede işaretli gelir; “bu bilgi bu belgede yok” da bir cevaptır.",
    ctaPrimary: "Örnek bir belgeyle deneyin",
    ctaSecondary: "Nasıl çalışıyor",
    ctaNote: "Örnekler hesapsız okunur · Soru sormak için Google ile giriş · Günde 3 soru",
    // Bir pazarlama bölümü değil, bir tanım.
    //
    // Google'ın OAuth marka doğrulaması iki şey arıyor: ana sayfanın
    // uygulamanın ne işe yaradığını anlatması ve rıza ekranındaki adın sayfada
    // birebir geçmesi. Hero'nun tamamı çağrışımla çalışıyordu — "Poliçenize
    // sorun" bir vaat, tanım değil — ve "BioPolicy" sayfada yalnızca header'daki
    // kelime markasında geçiyordu, o da dar ekranda gizli. İkisi de burada
    // düzeltiliyor: ilk cümle adı söyler, gerisi ne yaptığını.
    //
    // Giriş paragrafı ayrıca isteğe konu olan kapsamı gerekçelendiriyor, çünkü
    // doğrulamada asıl sorulan soru budur.
    about: {
      title: "BioPolicy nedir?",
      body:
        "BioPolicy, sigorta poliçelerini ve hukuki sözleşmeleri okuyan bir web " +
        "uygulamasıdır. Bir belge yükler ya da hazır örneklerden birini " +
        "seçersiniz; sorduğunuz soru, cevabın dayandığı madde belgenin üzerinde " +
        "işaretlenmiş halde yanıtlanır. Belge o soruyu yanıtlamıyorsa sistem " +
        "uydurmaz, yanıtlamadığını söyler.",
      signIn:
        "Google ile giriş yalnızca günlük kullanım hakkının kime ait olduğunu " +
        "belirlemek için istenir. Adınız, e-posta adresiniz ve profil " +
        "fotoğrafınız okunur; hesabınızdaki başka hiçbir veriye erişilmez ve " +
        "hiçbir bilgi üçüncü taraflarla paylaşılmaz. Yüklediğiniz belgeler 24 " +
        "saat içinde kalıcı olarak silinir.",
    },
    howTitle: "Üç adımda",
    how: [
      {
        title: "Belge ayrıştırılır — gerekirse OCR",
        body:
          "Metin, tablolar ve satır koordinatları çıkarılır. Sayfada metin " +
          "katmanı yoksa belge taranmış sayılır ve OCR ile okunur; hangi yolun " +
          "kullanıldığı belgenin yanında yazar.",
      },
      {
        title: "İki arama birlikte koşar — RAG",
        body:
          "Anlamsal arama “sel hasarı”nı bulur, sözcük araması “Madde 4.2”yi; " +
          "ikisi birleştirilip modele yalnızca belgenin ilgili bölümleri " +
          "verilir. Bu yönteme RAG deniyor.",
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
    considered: {
      toggle: "Bulunan {total} bölümün {used} tanesi kullanıldı",
      explainer:
        "Aşağıdakiler cevabın önüne konuldu ama alıntılanmadı. Cevap eksikse, " +
        "aranan maddenin burada olup olmadığı size bir şey söyler: buradaysa " +
        "sorun cevabı üretirken, değilse belgeyi ararken oluşmuş demektir.",
      page: "sayfa",
    },
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
    summary: {
      titles: {
        cover: "Teminat özeti",
        exclusions: "İstisnalar ve muafiyetler",
        terms: "Süre, taraflar ve kapsam",
      },
      badge: "şemadan çıkarıldı",
      note:
        "Bu özet model tarafından yazılmadı; belgeden çıkarılmış künyeden " +
        "derlendi. Her satır, alındığı maddeye bağlı — tıklayın, belgede görün.",
      absentTitle: "Bu başlıklarda madde bulunamadı",
      chips: {
        cover: "Teminat özeti",
        exclusions: "İstisnalar",
        terms: "Süre ve taraflar",
      },
      offerTitle: "Bunu tablo hâlinde de verebilirim",
      offerBody:
        "Belgeyi bir kez şemaya çıkarırsanız, bu tür özetler anında ve " +
        "bedelsiz gelir — her satır kendi maddesine bağlı olarak.",
    },
    pages: "sayfa",
    loadingDocuments: "Belgeler yükleniyor…",
    loadDocumentsFailed:
      "Belgeler alınamadı. API çalışmıyor olabilir; sayfayı yenilemeyi deneyin.",
    emptyTitle: "Bir soru sorun",
    emptyBody:
      "Cevap belgedeyse maddesiyle birlikte gösterilir. Değilse sistem uydurmaz, reddeder — ikincisini de deneyin.",
    suggestions: "Örnek sorular",
    suggestionsDerived:
      "Bu sorular belgenin şemaya çıkarılmış hâlinden türetildi — her biri belgede karşılığı bulunan bir maddeye denk geliyor.",
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
      "Bu soru için sağlayıcılara ödenen tutar: cevap ve doğrulama çağrıları (Anthropic) ile gömme ve sorgu yeniden yazma (Google). Her iki sağlayıcının fiyatları da doğrulandı ve kayıtlı.",
    cached: "önbellekten · bu cevap {count}. kez sunuldu",
    cachedNote:
      "Bu soru daha önce aynı belgeye, aynı prompt sürümü ve aynı modelle soruldu; cevap saklanmıştı. Yeni bir model çağrısı yapılmadı, bu yüzden maliyeti sıfır. Değerlendirme raporundaki süre ve maliyet rakamları gerçek çağrıların ölçümüdür, bu değil.",
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
      "Bugün {limit} sorunun tamamını kullandınız. Bu {limit} soru ve {documents} belge her gün yenilenir. Belgeleri ve geçmiş sohbetlerinizi incelemeye devam edebilirsiniz.",
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
    title: "Belgenize sorun",
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
    exhausted: "Günlük belge yükleme hakkınızı kullandınız — her gün yenilenir.",
    quotaTitle: "Günlük sınıra ulaştınız",
    // The API answers a limit in English, because it has no way of knowing who
    // is asking. Its message is the fallback for anyone reading the API
    // directly; what a visitor reads is written here, in their language.
    quotaQuestions:
      "Bugünkü soru hakkınızın tamamını kullandınız. Haklarınız her gün yenilenir.",
    quotaDocuments:
      "Bugünkü belge yükleme hakkınızı kullandınız. Haklarınız her gün yenilenir.",
    budgetTitle: "Demo şimdilik kapalı",
    budgetBody:
      "Demo harcama sınırına ulaştığı için şimdilik yeni soru yanıtlanmıyor. Sizden hiçbir ücret alınmadı.",
    blockedTitle: "Bu hesap demoyu kullanamıyor",
    blockedBody: "Devam etmek için Google hesabınızla giriş yapın.",
    retentionNote:
      "Yüklediğiniz belge {hours} saat sonra otomatik silinir; dilediğiniz an kendiniz de silebilirsiniz. O belgeyle yaptığınız sohbet de belgeyle birlikte gider.",
  },
  evaluation: {
    title: "Değerlendirme",
    lede: "Aşağıdaki sayıların hiçbirini elle yazmadım. Hepsini bir program üretti: 70 soruyu gerçek modellere sordu, gelen her cevabı tek tek denetledi. Sonuç hoşuma gitmediğinde de aynen yayımladım.",
    caveat:
      "Şunu baştan söyleyeyim: bu sınav, bu proje için yazılmış üç sahte belge üzerinde yapıldı. Gerçek poliçelerde ne olacağını göstermez. Raporun tamamı, neyi ölçemediğini de tek tek sayıyor.",
    fullReport: "Raporun tamamı",
    fullReportNote: "Sayılar nasıl çıktı, neyi ölçmüyor. İlk bölüm zaten bunu anlatıyor.",
    adversarialQuestions: "soru",
    adversarialFile: "Bu koşunun tamamı: report_hard.tr.md",
    adversarial: "Zor belgeler",
    adversarialNote:
      "Kendi kendisiyle çelişen bir poliçe. Bir de iki sütun hâlinde dizilmiş bir kasko. Ayrı sınav, ayrı sayılar.",
    cards: {
      refusalAccuracy: "Doğru ret",
      refusalAccuracyNote: "Cevabı belgede olmayan soruları uydurmadan reddetti.",
      falseRefusal: "Yanlış ret",
      falseRefusalNote: "Cevap belgede vardı ama yine de reddetti. Düşük olması iyi.",
      recall: "Doğru maddeyi buldu",
      recallNote: "Aranan madde, getirilen 8 parçanın arasındaydı.",
      citationValidity: "Alıntılar gerçek",
      citationValidityNote: "Gösterilen her alıntı belgede birebir vardı.",
      footnote:
        "{questions} soru · soru başına ${cost} · commit {commit}. İlk iki sayıyı birlikte okuyun: hiçbir soruya cevap vermeyen bir sistem birincisinden tam puan alır. İkincisi onu yakalar.",
    },
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
      "Her model çağrısı fiyatlanıp kaydediliyor. Bu toplamın {share} kadarı fiyatı doğrulanmış çağrılardan geliyor. Kalanı daha eski çağrılar: Google'ın fiyatları doğrulanmadan önce yapıldılar, o yüzden sıfır yazıldılar. Bugünden sonraki her çağrı tam sayılıyor.",
    historyTitle: "Sayılar zaman içinde",
    historyNote:
      "Yayımlanan yapılandırma, 70 soruluk küme. Her nokta bir koşum.",
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
    privacy: "Gizlilik",
    terms: "Koşullar",
  },
  legal: {
    updated: "Son güncelleme",
    home: "Ana sayfa",
    full: "Tam metni okuyun",
  },
};

type Dictionary = typeof tr;

const en: Dictionary = {
  meta: {
    title: "BioPolicy — what your document actually says",
    description:
      "A policy, a contract or any PDF: question answering that binds every answer to a clause in the document, and refuses when the document does not say.",
    pages: {
      app: "Workspace",
      eval: "Evaluation",
      signin: "Sign in",
      privacy: "Privacy Notice",
      terms: "Terms of Use",
      cookies: "Cookies",
    },
  },
  nav: {
    workspace: "Try it",
    source: "GitHub",
    home: "Home",
    backHome: "Back to home",
    backToProjects: "See my other projects",
    backToProjectsShort: "My projects",
    menu: "Menu",
    opensInNewTab: "opens in a new tab",
  },
  language: {
    label: "Language",
    tr: "Türkçe",
    en: "English",
  },
  landing: {
    eyebrow: "Open source · every number published · TR/EN",
    thesis: ["Ask your document.", "Get the clause, not a guess."],
    lede: "A policy, a contract, any PDF. Every answer arrives with its clause, highlighted in the document — and “that isn't in this document” is an answer too.",
    ctaPrimary: "Try it on a sample document",
    ctaSecondary: "How it works",
    ctaNote: "Samples readable without an account · Google sign-in to ask · 3 questions a day",
    about: {
      title: "What BioPolicy is",
      body:
        "BioPolicy is a web application that reads insurance policies and legal " +
        "contracts. Upload a document or pick one of the bundled samples, ask a " +
        "question, and the answer arrives with the clause it rests on marked in " +
        "the document itself. When the document does not answer the question, it " +
        "says so instead of inventing an answer.",
      signIn:
        "Signing in with Google is used for one thing: telling whose daily " +
        "allowance is whose. It reads your name, email address and profile " +
        "picture, reaches nothing else in your account, and shares nothing with " +
        "anyone. Documents you upload are permanently deleted within 24 hours.",
    },
    howTitle: "In three steps",
    how: [
      {
        title: "The document is parsed — OCR when needed",
        body:
          "Text, tables and line coordinates are extracted. A page with no text " +
          "layer counts as scanned and is read by OCR; which of the two was " +
          "used is shown beside the document.",
      },
      {
        title: "Two searches run together — RAG",
        body:
          "Semantic search finds “flood damage”, keyword search finds " +
          "“Article 4.2”; the two are fused and only the relevant passages of " +
          "the document reach the model. That method is called RAG.",
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
    considered: {
      toggle: "{used} of {total} retrieved passages were used",
      explainer:
        "These were put in front of the answer and not cited. If the answer " +
        "looks wrong, whether the clause you wanted is in this list tells you " +
        "where it went wrong: present means the answer failed to use it, " +
        "absent means the search failed to find it.",
      page: "page",
    },
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
    summary: {
      titles: {
        cover: "Cover summary",
        exclusions: "Exclusions and deductibles",
        terms: "Term, parties and scope",
      },
      badge: "from the schema",
      note:
        "This summary was not written by a model. It is assembled from the " +
        "profile extracted from the document — every row is bound to the " +
        "clause it came from. Click one to see it.",
      absentTitle: "No clause found under these headings",
      chips: {
        cover: "Cover summary",
        exclusions: "Exclusions",
        terms: "Term and parties",
      },
      offerTitle: "I can give you this as a table",
      offerBody:
        "Read the document into the schema once and summaries like this " +
        "arrive instantly and for nothing — every row bound to its clause.",
    },
    pages: "pages",
    loadingDocuments: "Loading documents…",
    loadDocumentsFailed:
      "Could not load the documents. The API may be down; try reloading.",
    emptyTitle: "Ask a question",
    emptyBody:
      "If the answer is in the document, you get it with the clause it came from. If it is not, the system refuses instead of inventing one — try that too.",
    suggestions: "Try one of these",
    suggestionsDerived:
      "Derived from this document's extracted profile — each one corresponds to a clause the document actually contains.",
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
      "What this question cost in provider spend: the answer and verification calls (Anthropic) plus embedding and query rewriting (Google). Both providers' rates are verified and registered.",
    cached: "from cache · served {count} times",
    cachedNote:
      "This question was asked of this document before, under the same prompt version and model, and the answer was kept. No model call was made, so it cost nothing. The latency and cost figures in the evaluation report are measurements of real calls; this is not one.",
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
      "All {limit} of them. The {limit} questions and {documents} upload renew every day. You can still read the documents and your earlier conversations.",
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
    title: "Ask your document",
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
    exhausted: "Today's upload is used — the allowance renews every day.",
    quotaTitle: "You have reached the daily limit",
    quotaQuestions:
      "You have used today's questions. The allowance renews every day.",
    quotaDocuments:
      "You have used today's upload. The allowance renews every day.",
    budgetTitle: "The demo is paused",
    budgetBody:
      "The demo has reached its spending limit, so it is not answering new questions right now. You were not charged for anything.",
    blockedTitle: "This account cannot use the demo",
    blockedBody: "Sign in with your Google account to continue.",
    retentionNote:
      "Your document is deleted automatically after {hours} hours, and you can delete it yourself at any time. The conversation about it goes when it does.",
  },
  evaluation: {
    title: "Evaluation",
    lede: "I did not write a single number below. A program produced all of them: it put 70 questions to the real models and checked every answer that came back. When the result was unflattering, I published it unchanged.",
    caveat:
      "One thing up front: this exam was sat on three synthetic documents written for this project. It does not tell you what happens with real policies. The full report lists what else it cannot measure.",
    fullReport: "The full report",
    fullReportNote: "How the numbers were produced, and what they miss. That is the opening section.",
    adversarialQuestions: "questions",
    adversarialFile: "The whole run: report_hard.md",
    adversarial: "Hard documents",
    adversarialNote:
      "A policy that contradicts itself. And one typeset in two columns. A separate exam, separate numbers.",
    cards: {
      refusalAccuracy: "Correct refusals",
      refusalAccuracyNote: "Questions the document cannot answer, refused instead of invented.",
      falseRefusal: "False refusals",
      falseRefusalNote: "The answer was in the document and it refused anyway. Lower is better.",
      recall: "Found the right clause",
      recallNote: "The clause the answer needed was among the 8 passages retrieved.",
      citationValidity: "Quotes were real",
      citationValidityNote: "Every quote shown appeared in the document, word for word.",
      footnote:
        "{questions} questions · ${cost} each · commit {commit}. Read the first two together: a system that refuses everything scores 100% on the first. The second is what catches it.",
    },
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
      "Every model call is priced and recorded. {share} of this total comes from calls whose rate was verified. The rest are older ones, made before Google's rates were checked, so they were written down as zero. Every call from here on counts in full.",
    historyTitle: "The numbers over time",
    historyNote: "The shipped configuration, over the 70-question set. One point per run.",
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
    privacy: "Privacy",
    terms: "Terms",
  },
  legal: {
    updated: "Last updated",
    home: "Home",
    full: "Read the full text",
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

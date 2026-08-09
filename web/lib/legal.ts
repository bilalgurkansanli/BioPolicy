import type { Locale } from "./i18n";

/**
 * The privacy notice, the terms, and the cookie notice.
 *
 * ## Why these are pages and not only sheets
 *
 * They already existed as panels inside `/signin`, which is where somebody
 * reads them in the thirty seconds before signing in. That is the right place
 * for a summary and the wrong place for the document itself: a policy has to be
 * linkable, quotable and readable without an account, and "it is behind the
 * sign-in screen" is the one thing a privacy notice must never be.
 *
 * So both exist and they are not the same length. The sheets stay short and
 * link here; these carry the whole thing.
 *
 * ## What is in them
 *
 * Only what the system actually does. Every claim below corresponds to code in
 * this repository, and the ones that would be uncomfortable to write are the
 * ones most worth writing — chiefly that the text of an uploaded document is
 * sent to Anthropic and Google, because a "we never share your data" line would
 * be false in the way that matters most here.
 *
 * These are not drafted by a lawyer, and the pages say so rather than implying
 * otherwise by omission.
 */

export type LegalSection = {
  heading: string;
  /** Paragraphs. Rendered in order, no markdown. */
  body: string[];
  /** Optional bullet list under the paragraphs. */
  bullets?: string[];
};

export type LegalDocument = {
  slug: "privacy" | "terms" | "cookies";
  title: string;
  /** One sentence under the title. */
  lede: string;
  updated: string;
  sections: LegalSection[];
};

/**
 * The date these were last written. Not generated: a "last updated" that moves
 * on every deploy tells a reader nothing, and one that moves without the text
 * changing is worse than none.
 */
export const LEGAL_UPDATED = "2026-08-09";

const CONTACT = "bilalsanli129@gmail.com";

const TR: Record<LegalDocument["slug"], LegalDocument> = {
  privacy: {
    slug: "privacy",
    title: "Gizlilik Bildirimi",
    lede: "Hangi veriler işleniyor, neden, ne kadar süreyle ve kimlerle paylaşılıyor.",
    updated: LEGAL_UPDATED,
    sections: [
      {
        heading: "Kısaca",
        body: [
          "BioPolicy bir portföy projesidir; ticari bir hizmet değildir. Yüklediğiniz belgeler 24 saat sonra silinir, sohbetleriniz siz silene kadar hesabınızda kalır ve hiçbir veri satılmaz ya da reklam için kullanılmaz.",
          "Buradaki en önemli madde şudur: sorunuzu cevaplayabilmek için belgenizin ilgili bölümleri yapay zekâ sağlayıcılarına gönderilir. Ayrıntısı aşağıda.",
        ],
      },
      {
        heading: "Kim işliyor",
        body: [
          `Bu projeyi tek kişi olarak Bilal Gürkan Şanlı yürütüyor. Veri sorumlusu olarak iletişim adresi: ${CONTACT}`,
        ],
      },
      {
        heading: "İşlenen veriler",
        body: ["Toplananlar bunlarla sınırlıdır:"],
        bullets: [
          "Hesap: Google ile giriş yaptığınızda adınız, e-posta adresiniz ve profil fotoğrafınızın adresi.",
          "Belgeler: yüklediğiniz PDF dosyası ve ondan çıkarılan metin parçaları.",
          "Sohbetler: sorduğunuz sorular, üretilen cevaplar ve cevabın dayandığı alıntılar.",
          "Kullanım: her model çağrısının hangi modele yapıldığı, kaç jeton harcadığı ve maliyeti. Günlük sınırlar bu kayıttan hesaplanır.",
          "Ölçüm: yalnızca kabul ederseniz, Microsoft Clarity üzerinden sayfa etkileşimleri. Ayrıntısı çerez sayfasında.",
        ],
      },
      {
        heading: "Neden işleniyor",
        body: [
          "Hesap bilgisi girişi ve günlük sınırın kime ait olduğunu belirlemek için. Belgeler ve sorular yalnızca sorduğunuz soruyu cevaplamak için. Kullanım kayıtları, projenin bütçesini aşmamasını sağlayan sayaç için — bu sayaç olmadan tek bir kullanıcı demoyu kapatabilir.",
          "Hukuki dayanak: hizmetin sizin talebiniz üzerine sunulması ve projenin işletilmesindeki meşru menfaat. Ölçüm çerezi için dayanak açık rızanızdır ve istediğiniz an geri alabilirsiniz.",
        ],
      },
      {
        heading: "Belgeniz kimlere gönderiliyor",
        body: [
          "Bu bölüm, çoğu gizlilik metninin geçiştirdiği yerdir. Bir soru sorduğunuzda belgenizden getirilen bölümler, soru metniyle birlikte model sağlayıcılarına gönderilir:",
        ],
        bullets: [
          "Anthropic — cevabın üretilmesi ve doğrulanması.",
          "Google (Gemini) — metnin aranabilir hâle getirilmesi (gömme), taranmış belgelerde metin okuma (OCR) ve Anthropic erişilemezse yedek cevaplama.",
          "Supabase — veritabanı, dosya depolama ve kimlik doğrulama.",
          "Vercel — uygulamanın barındırılması.",
        ],
      },
      {
        heading: "Ne kadar saklanıyor",
        body: [
          "Yüklediğiniz belgeler ve onlardan çıkarılan metin: yüklemeden 24 saat sonra otomatik silinir. Dosya, önce depolamadan sonra veritabanından kaldırılır; bu sıra bilinçlidir, tersi bir dosyayı sahipsiz bırakırdı.",
          "Sohbetleriniz: siz silene kadar. Bir belge silindiğinde o belgeye ait sohbet de gider.",
          "Kullanım kayıtları: harcamanın izlenebilir kalması için tutulur ve kişisel içerik barındırmaz — hangi soruyu sorduğunuzu değil, kaç jeton harcandığını içerir.",
          "Hesabınızı sildiğinizde belgeleriniz, sohbetleriniz ve hesabınız birlikte silinir.",
        ],
      },
      {
        heading: "Haklarınız",
        body: [
          "Kendinizle ilgili verilere erişme, düzeltme, silme ve işlemeye itiraz etme haklarınız vardır. Silme işlemini beklemeden kendiniz yapabilirsiniz: profil menüsündeki hesap silme, tüm belgelerinizi ve sohbetlerinizi kaldırır.",
          `Diğer talepler için: ${CONTACT}`,
        ],
      },
      {
        heading: "Bu metnin sınırı",
        body: [
          "Bu bildirim bir avukat tarafından hazırlanmamıştır. Sistemin gerçekte ne yaptığını olabildiğince açık anlatmayı amaçlar; hukuki bir görüş yerine geçmez.",
        ],
      },
    ],
  },
  terms: {
    slug: "terms",
    title: "Kullanım Koşulları",
    lede: "Ne sunuluyor, ne sunulmuyor ve hangi sınırlar var.",
    updated: LEGAL_UPDATED,
    sections: [
      {
        heading: "Bu ne değildir",
        body: [
          "BioPolicy hukuki ya da sigortacılık tavsiyesi vermez. Bir poliçeyle ilgili karar almadan önce poliçenin kendisine ve gerekiyorsa bir uzmana başvurun.",
          "Sistem cevaplarını belgeden üretir ve dayandığı maddeyi gösterir. Yine de yanlış cevap verebilir; gösterilen alıntıyı belgenin üzerinde kendiniz doğrulayabilirsiniz ve doğrulamanız beklenir.",
        ],
      },
      {
        heading: "Örnek belgeler",
        body: [
          "Demoda sunulan üç belge bu proje için yazılmış kurgusal metinlerdir. Gerçek bir sigorta şirketine, gerçek bir poliçeye veya gerçek bir kişiye ait değildir.",
        ],
      },
      {
        heading: "Kullanım sınırları",
        body: ["Bu bir demodur ve maliyeti gerçek. Bu yüzden sınırlar vardır:"],
        bullets: [
          "Günde 3 soru ve 1 belge yükleme.",
          "En fazla 25 MB, yalnızca PDF.",
          "Projenin toplam bütçesi dolduğunda yükleme kapanır ve yalnızca örnek belgeler okunabilir kalır.",
        ],
      },
      {
        heading: "Ne yüklememelisiniz",
        body: [
          "Yükleme hakkına sahip olmadığınız belgeleri yüklemeyin. Belgeniz üçüncü taraf model sağlayıcılarına gönderildiği için, gizlilik yükümlülüğü altındaki bir belgeyi yüklemeden önce bunu göz önünde bulundurun — ayrıntısı gizlilik bildiriminde.",
        ],
      },
      {
        heading: "Sorumluluk",
        body: [
          "Hizmet olduğu gibi sunulur. Kesintisiz çalışacağı ya da her cevabın doğru olacağı garanti edilmez. Bir portföy projesi olarak, önceden haber vermeden değiştirilebilir veya kapatılabilir.",
        ],
      },
      {
        heading: "Kaynak kodu",
        body: [
          "Proje MIT lisansıyla açık kaynaktır. Kodun kullanımı bu koşullara değil, deponun içindeki lisans metnine tabidir.",
        ],
      },
    ],
  },
  cookies: {
    slug: "cookies",
    title: "Çerezler",
    lede: "İki şey kullanılıyor: biri girişi açık tutuyor, diğeri isteğe bağlı.",
    updated: LEGAL_UPDATED,
    sections: [
      {
        heading: "Zorunlu olan",
        body: [
          "Girişinizi açık tutmak için tarayıcınızın yerel hafızası kullanılır. Bu bir izleme aracı değildir, üçüncü tarafa bir şey göndermez ve kapatılamaz — kapatılırsa giriş yapılamaz.",
        ],
      },
      {
        heading: "İsteğe bağlı olan",
        body: [
          "Microsoft Clarity, hangi sayfaların kullanıldığını ve insanların nerede takıldığını görmek için. Kabul etmezseniz sayfaya hiç yüklenmez — reddedilmiş bir ölçüm aracı için tek bir istek bile yapılmaz — ve site aynı şekilde çalışır.",
        ],
      },
      {
        heading: "Ölçümün dışında tutulanlar",
        body: [
          "Çalışma ekranı maskelenmiştir: belgeleriniz, sorularınız ve aldığınız cevaplar kayıtlara girmez. Tıkladığınız yer kaydedilir, yazdığınız metin kaydedilmez.",
        ],
      },
      {
        heading: "Fikrinizi değiştirirseniz",
        body: [
          "Giriş sayfasındaki çerez bölümünde seçiminizi sıfırlayan bir düğme var. Sıfırladığınızda soru yeniden sorulur; reddederseniz ölçüm bir daha yüklenmez.",
        ],
      },
    ],
  },
};

const EN: Record<LegalDocument["slug"], LegalDocument> = {
  privacy: {
    slug: "privacy",
    title: "Privacy Notice",
    lede: "What is processed, why, for how long, and who it reaches.",
    updated: LEGAL_UPDATED,
    sections: [
      {
        heading: "In short",
        body: [
          "BioPolicy is a portfolio project rather than a commercial service. Documents you upload are deleted after 24 hours, your conversations stay in your account until you delete them, and nothing is sold or used for advertising.",
          "The clause that matters most: to answer your question, the relevant parts of your document are sent to AI providers. Details below.",
        ],
      },
      {
        heading: "Who processes it",
        body: [
          `This project is run by one person, Bilal Gürkan Şanlı. Contact: ${CONTACT}`,
        ],
      },
      {
        heading: "What is collected",
        body: ["This list is exhaustive:"],
        bullets: [
          "Account: your name, email address and the URL of your profile picture, from Google sign-in.",
          "Documents: the PDF you upload and the text extracted from it.",
          "Conversations: the questions you ask, the answers produced, and the citations they rest on.",
          "Usage: which model each call went to, how many tokens it spent, and what it cost. Daily limits are computed from this.",
          "Measurement: only if you accept — page interactions via Microsoft Clarity. See the cookie notice.",
        ],
      },
      {
        heading: "Why",
        body: [
          "Account data identifies who a daily limit belongs to. Documents and questions are processed only to answer what you asked. Usage records feed the budget breaker that keeps this demo from being switched off by a single visitor.",
          "Legal basis: performance of a service at your request, and legitimate interest in operating the project. The measurement cookie rests on your consent, which you can withdraw at any time.",
        ],
      },
      {
        heading: "Where your document goes",
        body: [
          "This is the section most privacy notices are vague about. When you ask a question, the passages retrieved from your document are sent, with your question, to model providers:",
        ],
        bullets: [
          "Anthropic — producing and verifying the answer.",
          "Google (Gemini) — making the text searchable (embeddings), reading scanned pages (OCR), and answering if Anthropic is unavailable.",
          "Supabase — database, file storage and authentication.",
          "Vercel — hosting.",
        ],
      },
      {
        heading: "How long it is kept",
        body: [
          "Uploaded documents and their extracted text: deleted 24 hours after upload. The file goes from storage first and the rows second — that order is deliberate, since the reverse would leave a file nobody can find.",
          "Conversations: until you delete them. Deleting a document takes its conversations with it.",
          "Usage records: kept so spending stays auditable. They hold no personal content — how many tokens were spent, not what you asked.",
          "Deleting your account removes your documents, your conversations and the account together.",
        ],
      },
      {
        heading: "Your rights",
        body: [
          "You can access, correct, delete and object to the processing of data about you. You do not have to wait for the timer or ask anyone: account deletion is in the profile menu and removes every document and conversation you own.",
          `For anything else: ${CONTACT}`,
        ],
      },
      {
        heading: "The limits of this text",
        body: [
          "This notice was not drafted by a lawyer. It aims to describe accurately what the system does; it is not a legal opinion.",
        ],
      },
    ],
  },
  terms: {
    slug: "terms",
    title: "Terms of Use",
    lede: "What is offered, what is not, and the limits that apply.",
    updated: LEGAL_UPDATED,
    sections: [
      {
        heading: "What this is not",
        body: [
          "BioPolicy does not give legal or insurance advice. Before acting on anything about a policy, read the policy itself and consult a professional if it matters.",
          "The system answers from the document and shows the clause it used. It can still be wrong — the citation is shown on the document precisely so you can check it, and checking it is expected.",
        ],
      },
      {
        heading: "The sample documents",
        body: [
          "The three documents in the demo are fiction, written for this project. They do not belong to any real insurer, policy or person.",
        ],
      },
      {
        heading: "Limits",
        body: ["This is a demo and it costs real money, so there are limits:"],
        bullets: [
          "Three questions and one upload per day.",
          "25 MB maximum, PDF only.",
          "When the project's total budget is exhausted, uploads close and the sample documents stay readable.",
        ],
      },
      {
        heading: "What not to upload",
        body: [
          "Do not upload documents you have no right to upload. Because your document is sent to third-party model providers, consider that before uploading anything under a confidentiality obligation — see the privacy notice.",
        ],
      },
      {
        heading: "Liability",
        body: [
          "The service is provided as is. There is no guarantee that it will be available, or that any answer will be correct. As a portfolio project it may change or be switched off without notice.",
        ],
      },
      {
        heading: "Source code",
        body: [
          "The project is open source under the MIT licence. Use of the code is governed by the licence file in the repository rather than by these terms.",
        ],
      },
    ],
  },
  cookies: {
    slug: "cookies",
    title: "Cookies",
    lede: "Two things are used: one keeps you signed in, the other is optional.",
    updated: LEGAL_UPDATED,
    sections: [
      {
        heading: "The necessary one",
        body: [
          "Your browser's local storage keeps you signed in. It is not a tracker, it sends nothing to anyone, and it cannot be switched off — without it there is no sign-in.",
        ],
      },
      {
        heading: "The optional one",
        body: [
          "Microsoft Clarity, to see which pages get used and where people get stuck. If you decline it is never loaded — not one request is made to a measurement tool you refused — and the site behaves identically.",
        ],
      },
      {
        heading: "What measurement never sees",
        body: [
          "The workspace is masked: your documents, your questions and the answers you get stay out of any recording. Where you clicked is captured; what you typed is not.",
        ],
      },
      {
        heading: "Changing your mind",
        body: [
          "The cookie section of the sign-in page has a button that resets your choice. You will be asked again, and if you decline, measurement is never loaded again.",
        ],
      },
    ],
  },
};

export function legalDocument(
  slug: LegalDocument["slug"],
  locale: Locale,
): LegalDocument {
  return (locale === "tr" ? TR : EN)[slug];
}

# Değerlendirme raporu

> `python -m eval.run_eval` komutuyla üretildi. Buradaki her sayı, o komutun canlı modeller ve canlı veritabanı üzerinde ürettiği sayıdır; hiçbiri elle yazılmadı. Hoşa gitmeyen sonuçlar da duruyor — yayımlamanın amacı zaten bu.

## Önce bunu okuyun — bu sayılar neyi göstermiyor

Sonuçlardan sonra değil önce duruyor, çünkü raporun altına yazılan çekince, kimsenin okumadığı çekincedir.

- **2 soru sağlayıcı hatasıyla düştü ve ret olarak sayıldı.** Sağlayıcının hiç cevaplamadığı bir soru, buradaki her ölçütte sistemin reddettiği soruyla birebir aynı görünür — yani API'de kötü geçen bir öğleden sonra, yanlış ret oranı olarak karşımıza çıkar. Çıkarım kontrolünü taşıyan kollar soru başına ikisi yerine üç ardışık sağlayıcı çağrısı yapıyor ve hatalı olanlar da onlar: `naive_entailed` (2). Aşağıdaki her yanlış ret rakamını bu çıkarılmış hâliyle okuyun.

- **Çıkarım kontrolü, yapılma amacını yerine getirmedi.** Bu raporun daha önceki bir koşusu, önceki mekanizmaların dayanaksız çıkarıma kör olduğunu saptadığı için eklendi ve soruyu gören tek aşama o. Bu derlemde ret doğruluğunu +0%, yanlış ret oranını +0% oynattı ve her sorunun maliyetine 28% ekledi. Yukarıdaki sağlayıcı hatalarını çıkarın, hiçbir kararı değiştirmemiş oluyor — kendinden önceki iki mekanizmayla aynı bulgu, aynı yoldan. Çekişmeli kümede (`report_hard.md`) bir şey yakalıyor, burada hiçbir şey; sürekli açık tutmak, bu derlemde bulunmayan belgelerde çalışan bir kontrol için her soruda ödeme yapmak olurdu.

- **İşi yapan istem oldu, mekanizmalar değil.** İstem naif tutulup mekanizmalar açıldığında dengeli doğruluk +0% oynadı — aynı sorular cevaplandı, aynıları kaçırıldı. Mekanizmalar kapalı tutulup istem katı dayanak sürümüne çevrildiğinde ise +5% oynadı. Alıntı bağlama ve kendi kendini doğrulama, her sorunun maliyetine yaklaşık 45% ekliyor ve bu derlemde hiçbir kararı değiştirmedi.

  Sebep, kaçırdıkları hatalarda görünüyor. Naif istemin hataları *dayanaksız bir çıkarımı destekleyen doğru alıntılar*: çalınan bir aracın teminat kapsamında olup olmadığı sorulduğunda hırsızlık maddesini doğru alıntılıyor ve ardından aracın kapsama dahil olduğu sonucuna varıyor. Bağlama, alıntının gerçek olup olmadığına bakıyor — gerçek. Doğrulama, iddiayı alıntıya karşı kontrol ediyor — alıntı gerçekten hırsızlığın kapsandığını söylüyor. İki mekanizma da, belgenin hiç varmadığı bir sonucu desteklemek için kullanılan geçerli bir alıntıyı yakalamak üzere kurulmadı; bu koşu, o kör noktanın ilk kanıtı. Kapatmak için alıntıya değil, *çıkarım* adımına bakan bir kontrol gerekiyor.

- **%100'lük alıntı geçerliliğinin bir kısmı yapısal.** Cevap veren model, sağlayıcı tarafından dayatılan bir JSON şemasıyla kısıtlı ve bağlam küçük; yani bozuk ya da uydurma parça kimlikleri kuruluş gereği neredeyse imkânsız. Bağlamanın asıl ilginç yarısı — adını verdiği parçada geçmeyen bir *alıntıyı* yakalamak — burada hiç sınanmadı.

## Koşu

| | |
|---|---|
| Üretildi | 2026-08-09 18:54 UTC |
| Commit | `7b38611` |
| Cevaplayan model | `claude-haiku-4-5-20251001` |
| Gömme modeli | `gemini-embedding-001` (1536 boyut) |
| İstemler | `answer_v2`, `verify_v1` |
| Soru | 70 |
| Cevabı belgede olmayan sorular | 21 (30%) |

## Ablasyon

İki bağımsız değişken, dört kol: **istem** (katı dayanak istemi ile naif istem) ve **mekanizmalar** (alıntı bağlama ve kendi kendini doğrulama, açık ya da kapalı) çaprazlanıyor.

Naif istem bir korkuluk değil. Doğruluk istiyor, alıntı talep ediyor ve aynı JSON'u döndürüyor — yetkin bir geliştiricinin ilk denemede yazacağı şey. Yapmadığı şey şu: dışarıdan bilgiyi yasaklamıyor, birebir alıntı şart koşmuyor ve “bu belgede yok”un kabul edilebilir bir cevap olduğunu söylemiyor.

| Kol | Ret doğruluğu | Yanlış ret | Dengeli | Alıntı geçerliliği | Bastırılan | $/soru |
|---|---:|---:|---:|---:|---:|---:|
| naif istem, mekanizmasız | 86% | 0% | 93% | 100% | 0 | $0.0035 |
| naif istem + mekanizmalar | 86% | 0% | 93% | 99% | 0 | $0.0062 |
| katı istem, mekanizmasız | 100% | 4% | 98% | 100% | 0 | $0.0049 |
| katı istem + mekanizmalar **(yayımlanan)** | 100% | 4% | 98% | 100% | 0 | $0.0072 |

**Başlangıçtan yayımlanana:** dengeli doğruluk 93% → 98%, ret doğruluğu 86% → 100%.

**Ret doğruluğu ile yanlış ret oranını birlikte okuyun.** Birincisi her şeyi reddederek, ikincisi hiç reddetmeyerek kolayca kandırılır. Dengeli doğruluk ikisinin ortalamasıdır ve bu iki yoz stratejinin ikisinde de %50'ye oturur — kolları karşılaştırmak için bakılacak sütun odur.

**Satırları karşılaştırmak, işi hangi kolun yaptığını söyler.** naive_only → strict_only istemi yalıtır. naive_only → naive_guarded mekanizmaları yalıtır. strict_guarded'a giden iki yol eşit değilse, kollar bağımsız değildir.

## Getirme

Yalnızca cevaplanabilir sorular üzerinden ölçülüyor — cevabı belgede olmayan bir soruda bulunacak doğru parça yoktur. İsabet sayılması için beklenen **her** bölümün, yalnızca getirilmiş değil modele fiilen ulaşmış parçalar içinde bulunması gerekir: limiti olmayan bir teminat, cevabı değil sorunun yeniden yazılmış hâlini getirmiştir.

| | |
|---|---:|
| Recall@8 | 98% |
| MRR | 0.821 |
| Cevaplanabilir soru | 49 |

### Kategoriye göre

| Kategori | Soru | Recall@8 | Karar doğruluğu |
|---|---:|---:|---:|
| cross_lingual | 7 | 100% | 100% |
| factual | 19 | 100% | 95% |
| multi_clause | 9 | 89% | 89% |
| negative | 0 | — | 100% |
| table | 14 | 100% | 100% |

`negative` kategorisinin kuruluş gereği recall değeri yok — getirilecek bir şey yok. Karar doğruluğu, o alt küme için ret doğruluğudur.

## Ret

| | |
|---|---:|
| Doğru ret | 21 / 21 |
| Yanlış ret | 2 / 49 |
| Ret doğruluğu | 100% |
| Yanlış ret oranı | 4% |
| Dengeli doğruluk | 98% |

### Getirme eşiği

Herhangi bir model çağrılmadan önce, getirilen en yakın bölüm bir kosinüs mesafesi eşiğine karşı denetlenir. Hiçbir şeyin yakın olmadığı bir soru bedelsiz reddedilir. Yeniden üretmek için: `uv run python -m eval.measure_floor`.

| Küme | n | min | median | max | Eşiğin reddettiği |
|---|---:|---:|---:|---:|---:|
| cevaplanabilir | 49 | 0.2021 | 0.3028 | 0.4194 | 0 / 49 |
| konu içi, cevapsız | 21 | 0.2710 | 0.3368 | 0.4402 | 0 / 21 |
| başka sigorta konusu | 18 | 0.3206 | 0.4386 | 0.5093 | 7 / 18 |
| tümüyle alakasız | 18 | 0.4681 | 0.5057 | 0.5718 | 18 / 18 |
| tanımlayıcı sorguları | 8 | 0.3059 | 0.3807 | 0.4038 | 0 / 8 |

**Eşiğin yapmadığı şey asıl mesele.** Cevaplanabilir ve konuyla ilgili ama cevapsız kümeler neredeyse tümüyle örtüşüyor — cevapsızların en yakını, cevaplanabilirlerin medyanından daha yakın — dolayısıyla hiçbir eşik bu ikisini ayıramaz ve eşik bunu denemiyor. Aradaki boşluğun gerçek olduğu yerde, konu içi ile konu dışını ayırıyor; zor yargıyı prompt'a bırakıyor.

## Alıntılar ve dayanak

| | |
|---|---:|
| Sunulan alıntı | 62 |
| Bağlamayı geçen | 62 |
| Alıntı geçerliliği | 100% |
| Bastırılan cevap (yakalanan uydurma) | 0 |
| Ortalama dayanak skoru (gösterilen cevaplar) | 0.96 |

Gösterilen cevaplar üzerinden, kategoriye göre ortalama dayanak skoru:

| Kategori | Ortalama dayanak | Karar doğruluğu |
|---|---:|---:|
| multi_clause | 0.94 | 89% |
| factual | 0.96 | 95% |
| table | 0.97 | 100% |
| cross_lingual | 0.98 | 100% |

Gösterilen cevaplarda dayanak skoru dağılımı:

| Aralık | Cevap |
|---|---:|
| high (>=0.8) | 43 |
| medium (0.5-0.8) | 4 |
| low (<0.5) | 0 |

Ortalama yalnızca **gösterilen** cevapları kapsıyor. Bastırılanları da katmak, “kontrol ettik ve tuttu” ile “kontrol ettik, tutmadı, göstermedik”i birbirine karıştırırdı — ikincisi sistemin başarısıdır ve yakalanan uydurma olarak ayrıca sayılır.

## Maliyet ve gecikme

| | |
|---|---:|
| Soru başına maliyet | $0.0072 |
| p50 gecikme | 6.2s |
| p95 gecikme | 15.7s |
| Bu koşunun toplamı | $2.73 |

Ortalama yerine p50 ve p95: tek bir soğuk başlangıç ortalamayı oynatır ve tipik deneyim hakkında hiçbir şey söylemez.


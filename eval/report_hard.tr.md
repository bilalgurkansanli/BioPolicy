# Değerlendirme raporu

> `python -m eval.run_eval` komutuyla üretildi. Buradaki her sayı, o komutun canlı modeller ve canlı veritabanı üzerinde ürettiği sayıdır; hiçbiri elle yazılmadı. Hoşa gitmeyen sonuçlar da duruyor — yayımlamanın amacı zaten bu.

## Önce bunu okuyun — bu sayılar neyi göstermiyor

Sonuçlardan sonra değil önce duruyor, çünkü raporun altına yazılan çekince, kimsenin okumadığı çekincedir.

- **1 soru sağlayıcı hatasıyla düştü ve ret olarak sayıldı.** Sağlayıcının hiç cevaplamadığı bir soru, buradaki her ölçütte sistemin reddettiği soruyla birebir aynı görünür — yani API'de kötü geçen bir öğleden sonra, yanlış ret oranı olarak karşımıza çıkar. Çıkarım kontrolünü taşıyan kollar soru başına ikisi yerine üç ardışık sağlayıcı çağrısı yapıyor ve hatalı olanlar da onlar: `naive_entailed` (1). Aşağıdaki her yanlış ret rakamını bu çıkarılmış hâliyle okuyun.

- **Çıkarım kontrolü, yapılma amacını yerine getirmedi.** Bu raporun daha önceki bir koşusu, önceki mekanizmaların dayanaksız çıkarıma kör olduğunu saptadığı için eklendi ve soruyu gören tek aşama o. Bu derlemde ret doğruluğunu +0%, yanlış ret oranını +10% oynattı ve her sorunun maliyetine 14% ekledi. Yukarıdaki sağlayıcı hatalarını çıkarın, hiçbir kararı değiştirmemiş oluyor — kendinden önceki iki mekanizmayla aynı bulgu, aynı yoldan. Çekişmeli kümede (`report_hard.md`) bir şey yakalıyor, burada hiçbir şey; sürekli açık tutmak, bu derlemde bulunmayan belgelerde çalışan bir kontrol için her soruda ödeme yapmak olurdu.

- **%100'lük alıntı geçerliliğinin bir kısmı yapısal.** Cevap veren model, sağlayıcı tarafından dayatılan bir JSON şemasıyla kısıtlı ve bağlam küçük; yani bozuk ya da uydurma parça kimlikleri kuruluş gereği neredeyse imkânsız. Bağlamanın asıl ilginç yarısı — adını verdiği parçada geçmeyen bir *alıntıyı* yakalamak — burada hiç sınanmadı.

## Koşu

| | |
|---|---|
| Üretildi | 2026-08-05 23:15 UTC |
| Commit | `30e9f68` |
| Cevaplayan model | `claude-haiku-4-5-20251001` |
| Gömme modeli | `gemini-embedding-001` (1536 boyut) |
| İstemler | `answer_v2`, `verify_v1` |
| Soru | 12 |
| Cevabı belgede olmayan sorular | 2 (17%) |

## Ablasyon

İki bağımsız değişken, dört kol: **istem** (katı dayanak istemi ile naif istem) ve **mekanizmalar** (alıntı bağlama ve kendi kendini doğrulama, açık ya da kapalı) çaprazlanıyor.

Naif istem bir korkuluk değil. Doğruluk istiyor, alıntı talep ediyor ve aynı JSON'u döndürüyor — yetkin bir geliştiricinin ilk denemede yazacağı şey. Yapmadığı şey şu: dışarıdan bilgiyi yasaklamıyor, birebir alıntı şart koşmuyor ve “bu belgede yok”un kabul edilebilir bir cevap olduğunu söylemiyor.

| Kol | Ret doğruluğu | Yanlış ret | Dengeli | Alıntı geçerliliği | Bastırılan | $/soru |
|---|---:|---:|---:|---:|---:|---:|
| naif istem, mekanizmasız | 100% | 0% | 100% | 100% | 0 | $0.0028 |
| naif istem + mekanizmalar | 100% | 10% | 95% | 100% | 1 | $0.0049 |
| katı istem, mekanizmasız | 100% | 10% | 95% | 100% | 0 | $0.0036 |
| katı istem + mekanizmalar **(yayımlanan)** | 100% | 10% | 95% | 100% | 0 | $0.0061 |

**Başlangıçtan yayımlanana:** dengeli doğruluk 100% → 95%, ret doğruluğu 100% → 100%.

**Ret doğruluğu ile yanlış ret oranını birlikte okuyun.** Birincisi her şeyi reddederek, ikincisi hiç reddetmeyerek kolayca kandırılır. Dengeli doğruluk ikisinin ortalamasıdır ve bu iki yoz stratejinin ikisinde de %50'ye oturur — kolları karşılaştırmak için bakılacak sütun odur.

**Satırları karşılaştırmak, işi hangi kolun yaptığını söyler.** naive_only → strict_only istemi yalıtır. naive_only → naive_guarded mekanizmaları yalıtır. strict_guarded'a giden iki yol eşit değilse, kollar bağımsız değildir.

## Getirme

Yalnızca cevaplanabilir sorular üzerinden ölçülüyor — cevabı belgede olmayan bir soruda bulunacak doğru parça yoktur. İsabet sayılması için beklenen **her** bölümün, yalnızca getirilmiş değil modele fiilen ulaşmış parçalar içinde bulunması gerekir: limiti olmayan bir teminat, cevabı değil sorunun yeniden yazılmış hâlini getirmiştir.

| | |
|---|---:|
| Recall@8 | 100% |
| MRR | 0.883 |
| Cevaplanabilir soru | 10 |

### Kategoriye göre

| Kategori | Soru | Recall@8 | Karar doğruluğu |
|---|---:|---:|---:|
| contradiction | 2 | 100% | 50% |
| factual | 4 | 100% | 100% |
| multi_clause | 3 | 100% | 100% |
| negative | 0 | — | 100% |
| table | 1 | 100% | 100% |

`negative` kategorisinin kuruluş gereği recall değeri yok — getirilecek bir şey yok. Karar doğruluğu, o alt küme için ret doğruluğudur.

## Ret

| | |
|---|---:|
| Doğru ret | 2 / 2 |
| Yanlış ret | 1 / 10 |
| Ret doğruluğu | 100% |
| Yanlış ret oranı | 10% |
| Dengeli doğruluk | 95% |

## Alıntılar ve dayanak

| | |
|---|---:|
| Sunulan alıntı | 11 |
| Bağlamayı geçen | 11 |
| Alıntı geçerliliği | 100% |
| Bastırılan cevap (yakalanan uydurma) | 0 |
| Ortalama dayanak skoru (gösterilen cevaplar) | 1.00 |

Gösterilen cevaplar üzerinden, kategoriye göre ortalama dayanak skoru:

| Kategori | Ortalama dayanak | Karar doğruluğu |
|---|---:|---:|
| contradiction | 1.00 | 50% |
| factual | 1.00 | 100% |
| multi_clause | 1.00 | 100% |
| table | 1.00 | 100% |

Gösterilen cevaplarda dayanak skoru dağılımı:

| Aralık | Cevap |
|---|---:|
| high (>=0.8) | 9 |
| medium (0.5-0.8) | 0 |
| low (<0.5) | 0 |

Ortalama yalnızca **gösterilen** cevapları kapsıyor. Bastırılanları da katmak, “kontrol ettik ve tuttu” ile “kontrol ettik, tutmadı, göstermedik”i birbirine karıştırırdı — ikincisi sistemin başarısıdır ve yakalanan uydurma olarak ayrıca sayılır.

## Maliyet ve gecikme

| | |
|---|---:|
| Soru başına maliyet | $0.0061 |
| p50 gecikme | 5.9s |
| p95 gecikme | 6.7s |
| Bu koşunun toplamı | $0.36 |

Ortalama yerine p50 ve p95: tek bir soğuk başlangıç ortalamayı oynatır ve tipik deneyim hakkında hiçbir şey söylemez.


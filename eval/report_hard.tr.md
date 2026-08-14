# Değerlendirme raporu

> `python -m eval.run_eval` komutuyla üretildi. Buradaki her sayı, o komutun canlı modeller ve canlı veritabanı üzerinde ürettiği sayıdır; hiçbiri elle yazılmadı. Hoşa gitmeyen sonuçlar da duruyor — yayımlamanın amacı zaten bu.

## Önce bunu okuyun — bu sayılar neyi göstermiyor

Sonuçlardan sonra değil önce duruyor, çünkü raporun altına yazılan çekince, kimsenin okumadığı çekincedir.

- **Çıkarım kontrolü, yapılma amacını yerine getirmedi.** Bu raporun daha önceki bir koşusu, önceki mekanizmaların dayanaksız çıkarıma kör olduğunu saptadığı için eklendi ve soruyu gören tek aşama o. Bu derlemde ret doğruluğunu +0%, yanlış ret oranını +0% oynattı ve her sorunun maliyetine 29% ekledi. Yukarıdaki sağlayıcı hatalarını çıkarın, hiçbir kararı değiştirmemiş oluyor — kendinden önceki iki mekanizmayla aynı bulgu, aynı yoldan. Çekişmeli kümede (`report_hard.md`) bir şey yakalıyor, burada hiçbir şey; sürekli açık tutmak, bu derlemde bulunmayan belgelerde çalışan bir kontrol için her soruda ödeme yapmak olurdu.

- **%100'lük alıntı geçerliliğinin bir kısmı yapısal.** Cevap veren model, sağlayıcı tarafından dayatılan bir JSON şemasıyla kısıtlı ve bağlam küçük; yani bozuk ya da uydurma parça kimlikleri kuruluş gereği neredeyse imkânsız. Bağlamanın asıl ilginç yarısı — adını verdiği parçada geçmeyen bir *alıntıyı* yakalamak — burada hiç sınanmadı.

## Koşu

| | |
|---|---|
| Üretildi | 2026-08-14 17:00 UTC |
| Commit | `8487513` |
| Cevaplayan model | `claude-haiku-4-5-20251001` |
| Gömme modeli | `voyage-4-lite` (1024 boyut) |
| İstemler | `answer_v2`, `verify_v1` |
| Soru | 12 |
| Cevabı belgede olmayan sorular | 2 (17%) |

## Ablasyon

İki bağımsız değişken, dört kol: **istem** (katı dayanak istemi ile naif istem) ve **mekanizmalar** (alıntı bağlama ve kendi kendini doğrulama, açık ya da kapalı) çaprazlanıyor.

Naif istem bir korkuluk değil. Doğruluk istiyor, alıntı talep ediyor ve aynı JSON'u döndürüyor — yetkin bir geliştiricinin ilk denemede yazacağı şey. Yapmadığı şey şu: dışarıdan bilgiyi yasaklamıyor, birebir alıntı şart koşmuyor ve “bu belgede yok”un kabul edilebilir bir cevap olduğunu söylemiyor.

| Kol | Ret doğruluğu | Yanlış ret | Dengeli | Alıntı geçerliliği | Bastırılan | $/soru |
|---|---:|---:|---:|---:|---:|---:|
| naif istem, mekanizmasız | 100% | 0% | 100% | 100% | 0 | $0.0029 |
| naif istem + mekanizmalar | 100% | 10% | 95% | 100% | 1 | $0.0052 |
| katı istem, mekanizmasız | 100% | 10% | 95% | 100% | 0 | $0.0043 |
| katı istem + mekanizmalar **(yayımlanan)** | 100% | 10% | 95% | 100% | 0 | $0.0063 |

**Başlangıçtan yayımlanana:** dengeli doğruluk 100% → 95%, ret doğruluğu 100% → 100%.

**Ret doğruluğu ile yanlış ret oranını birlikte okuyun.** Birincisi her şeyi reddederek, ikincisi hiç reddetmeyerek kolayca kandırılır. Dengeli doğruluk ikisinin ortalamasıdır ve bu iki yoz stratejinin ikisinde de %50'ye oturur — kolları karşılaştırmak için bakılacak sütun odur.

**Satırları karşılaştırmak, işi hangi kolun yaptığını söyler.** naive_only → strict_only istemi yalıtır. naive_only → naive_guarded mekanizmaları yalıtır. strict_guarded'a giden iki yol eşit değilse, kollar bağımsız değildir.

## Getirme

Yalnızca cevaplanabilir sorular üzerinden ölçülüyor — cevabı belgede olmayan bir soruda bulunacak doğru parça yoktur. İsabet sayılması için beklenen **her** bölümün, yalnızca getirilmiş değil modele fiilen ulaşmış parçalar içinde bulunması gerekir: limiti olmayan bir teminat, cevabı değil sorunun yeniden yazılmış hâlini getirmiştir.

| | |
|---|---:|
| Recall@8 | 100% |
| MRR | 0.850 |
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

### Getirme eşiği

Herhangi bir model çağrılmadan önce, getirilen en yakın bölüm bir kosinüs mesafesi eşiğine karşı denetlenir. Hiçbir şeyin yakın olmadığı bir soru bedelsiz reddedilir. Yeniden üretmek için: `uv run python -m eval.measure_floor`.

Eşik **0.72**, `voyage-4-lite` uzayında ölçüldü. İkisi birlikte yazılıyor, çünkü biri olmadan diğeri bir şey ifade etmiyor: kosinüs mesafesi gömme modelleri arasında karşılaştırılabilir değil — tek başına verilen bir eşik denetlenemez, model değişirken yerinde kalan bir eşik ise fark edilemez.

| Küme | n | min | median | max | Eşiğin reddettiği |
|---|---:|---:|---:|---:|---:|
| cevaplanabilir | 49 | 0.3603 | 0.4890 | 0.6967 | 0 / 49 |
| konu içi, cevapsız | 21 | 0.5242 | 0.5891 | 0.7221 | 2 / 21 |
| başka sigorta konusu | 18 | 0.4095 | 0.7184 | 0.8303 | 9 / 18 |
| tümüyle alakasız | 18 | 0.7339 | 0.8559 | 0.9586 | 18 / 18 |
| tanımlayıcı sorguları | 8 | 0.5832 | 0.7012 | 0.8010 | 3 / 8 |

**Eşiğin yapmadığı şey asıl mesele.** Cevaplanabilir ve konuyla ilgili ama cevapsız kümeler neredeyse tümüyle örtüşüyor — cevapsızların en yakını, cevaplanabilirlerin medyanından daha yakın — dolayısıyla hiçbir eşik bu ikisini ayıramaz ve eşik bunu denemiyor. Aradaki boşluğun gerçek olduğu yerde, konu içi ile konu dışını ayırıyor; zor yargıyı prompt'a bırakıyor.

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
| Soru başına maliyet | $0.0063 |
| p50 gecikme | 5.1s |
| p95 gecikme | 6.9s |
| Bu koşunun toplamı | $0.40 |

Ortalama yerine p50 ve p95: tek bir soğuk başlangıç ortalamayı oynatır ve tipik deneyim hakkında hiçbir şey söylemez.


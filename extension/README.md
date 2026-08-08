# Form Doldurucu — Chrome eklentisi

Başvuru formlarındaki tekrar eden alanları kayıtlı profilinden doldurur.
Bağımlılık yok, derleme adımı yok — dosyalar olduğu gibi yüklenir.

## Kurulum

1. Chrome'da `chrome://extensions` aç
2. Sağ üstten **Geliştirici modu**nu aç
3. **Paketlenmemiş öğe yükle** → bu `extension/` klasörünü seç
4. Eklenti simgesine sağ tık → **Seçenekler** → profilini doldur, kaydet

Kullanırken: başvuru formunun olduğu sayfada eklenti simgesine tıkla. Ne
nereye yazılacak listelenir; istemediğini işaretten çıkar, sonra **Seçilenleri
doldur**'a bas.

## Neyi bilerek yapmıyor

Bu eklenti bir otomatik başvuru botu değil. Sınırlar dokümantasyonda değil,
kodda:

| | |
|---|---|
| **Formu göndermez** | `form.submit()` çağrısı, düğme tıklaması, Enter tuşu yok. `fill-test.html` bunu iddia değil test olarak doğruluyor |
| **Kendiliğinden çalışmaz** | Otomatik content script ve `host_permissions` yok. `activeTab` sayesinde sen simgeye tıklayana kadar hiçbir sayfayı göremez |
| **Parola ve ödeme alanlarına dokunmaz** | `NEVER_FILL` deseni ve `type=password` engeli, puan ne olursa olsun geçerli. IBAN, kart numarası, CVV, OTP dahil |
| **Portala senin adına giriş yapmaz** | Oturum senin, CAPTCHA senin, gönderme kararı senin |

Bunun sebebi çekingenlik değil: başvuru portallarının çoğunun kullanım şartları
otomasyonu yasaklıyor ve ihlali başvurunun iptaline yol açabiliyor. Alan
doldurmanın sıkıcılığını almak riski almadan mümkün.

## Hassas alanlar

Pasaport ve kimlik numarası ayrı işaretli. Varsayılan olarak **doldurulmazlar**;
her doldurma öncesi açıkça onay kutusunu işaretlemen gerekir.

Profil `chrome.storage.local`'da, yalnızca bu tarayıcıda tutulur; hiçbir yere
gönderilmez, senkronize edilmez. **Şifreli değildir** — bilgisayarına erişen
biri okuyabilir. Seçenekler sayfasındaki "Tümünü sil" her şeyi temizler.

## Alan eşleştirme

Tek kural yerine puanlama var, çünkü formlar bilgiyi farklı yerlere koyuyor:
bazısı düzgün `<label>` kullanıyor, bazısı sadece `name`, bazısı yalnızca
`placeholder`. Her sinyal puana katkı veriyor, en yüksek puanlı profil alanı
kazanıyor, eşiği geçemeyen alana **dokunulmuyor** — boş bırakılmış bir alan,
yanlış doldurulmuş bir alandan çok daha küçük bir sorun.

Sinyaller ve ağırlıkları (`lib/matcher.js`):

| Sinyal | Ağırlık | Neden |
|---|---|---|
| `autocomplete` | 100 | Sayfanın bilerek belirttiği tek sinyal |
| `<label>` metni | 50 | İnsana gösterilen ad |
| `name` / `id` | 45 | Genelde anlamlı, bazen `q_4471` |
| `placeholder` | 40 | Etiket yoksa tek ipucu |
| `aria-label` | 40 | Aynı |
| Girdi tipi | 20 | `type=date`, `type=email` |

Buna tam eşleşme için +20, çok kelimeli anahtarın uzun metin içinde geçmesi
için +10 ekleniyor. Eşik 45.

Anahtar kelimeler **İngilizce, Almanca, Hollandaca ve Türkçe** — portallar bu
dillerde: `Vorname`/`Voornaam`/`First name` aynı alana gider.

Bir alanı yanlış eşleştirirse açılır listeden düzelt; o düzeltme site bazında
hatırlanır. Eşleme anahtarı `name` üzerinden üretilir, `id` üzerinden değil —
React gibi her render'da id üreten sayfalarda öğrenilen eşleme yoksa boşa
giderdi.

## Testler

Tarayıcıda çalışır, Chrome'a kurmaya gerek yok:

```bash
python -m http.server 8799 --bind 127.0.0.1
```

Sonra `http://127.0.0.1:8799/test/matcher-test.html` ve `.../fill-test.html`
aç. Sayfa geçen/kalan testleri listeler.

- **matcher-test.html** — 38 test: üç dilde alan tanıma, engellenen alanlar,
  hassas alan varsayılanı, aynı değerin iki alana yazılmaması, öğrenilen
  eşlemeler
- **fill-test.html** — 21 test: tarih biçimi çevirme, `<select>` eşleştirme,
  framework'lerin beklediği `input`/`change` olayları, ve **formun
  gönderilmediği**

## Dosyalar

```
manifest.json          MV3, izinler: storage · activeTab · scripting
lib/fields.js          Profil şeması + alan başına çok dilli anahtar kelimeler
lib/matcher.js         Puanlama ve plan üretimi (saf, DOM okur, yazmaz)
content/content.js     Tarama ve doldurma; sadece istek üzerine çalışır
popup/                 Onay adımı: ne nereye yazılacak
options/               Profil düzenleyici
test/                  Tarayıcıda çalışan testler
```

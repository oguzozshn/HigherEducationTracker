# Higher Education Tracker

Almanya ve Hollanda'daki İngilizce yüksek lisans programlarını, başvuru
takvimlerini ve kabul şartlarını tek yerde toplayan kişisel araç. Yanında,
başvuru formlarındaki tekrar eden alanları dolduran bir Chrome eklentisi.

**2859 program** · 221 üniversite · 6253 başvuru tarihi

Bağımlılık yok — sadece Python 3.11+ ve standart kütüphane. `pip install`
gerekmiyor, sanal ortam gerekmiyor, veritabanı sunucusu gerekmiyor.

---

## Kurulum

```bash
git clone https://github.com/oguzozshn/HigherEducationTracker.git
```

Python 3.11 veya üstü yeterli. Başka bir şey kurman gerekmiyor.

## 1. Veriyi çek

Almanya (DAAD kataloğu, ~1560 program, birkaç dakika):

```bash
python -m het ingest de
```

Hollanda (Nuffic Studyfinder, ~1300 program, saniyeler):

```bash
python -m het ingest nl
```

Sadece belli bir alanla ilgileniyorsan daraltabilirsin:

```bash
python -m het ingest de --subject "computer science"
```

Veriler `data/het.db` içine yazılır. Tekrar çalıştırmak günceller, silmez.

> **Windows'ta Hollanda çekimi SSL hatası verirse:** `studyinnl.org`
> sertifikası HARICA köküne zincirleniyor; Windows bu kökü taşımıyor, Linux
> taşıyor. Doğrulamayı kapatma — Git for Windows'un getirdiği Mozilla kök
> paketini göster:
>
> ```bash
> HET_CA_BUNDLE="C:/Program Files/Git/mingw64/etc/ssl/certs/ca-bundle.crt" python -m het ingest nl
> ```

## 2. Arayüzü aç

```bash
python -m het serve
```

Tarayıcıda `http://127.0.0.1:8765` açılır. Üç sekme var:

**Ara** — programları isim, alan, üniversite, şehir ve harç durumuna göre
filtrele. Bir karta tıklayınca sağdan detay paneli açılır. Almanya
programlarında detay sayfası ilk açılışta indirilir (birkaç saniye), sonra
önbellekten gelir; Hollanda programlarında her şey zaten çekilmiştir.

**Kısa Liste** — başvurmayı düşündüğün programlar. Her biri için durum
etiketi (İlgileniyorum → Hazırlanıyorum → Gönderildi → Kabul/Red), belge
ilerleme çubuğu ve en yakın son tarih.

**Takvim** — yaklaşan tarihler aya göre gruplu, geri sayımla. 45 günden
yakın olanlar vurgulanır.

## 3. Belge listesi

Detay panelinde her program için bir belge listesi üretilir — programın kendi
gereklilik metninden okunarak:

```
Lisans diploması · Transkript (ECTS ile) · CV · Pasaport kopyası
İngilizce yeterlilik belgesi   → Hedef: C1 / IELTS 6.5 / TOEFL 95
Mülakat                        → Kısa listeye kalanlar görüşmeye çağrılıyor
```

Metinde `uni-assist`, referans mektubu, motivasyon mektubu, GRE, portfolyo,
blokeli hesap gibi ifadeler geçerse ilgili maddeler de eklenir; her biri
"neden eklendi" notuyla gelir.

Maddeleri işaretleyebilir, silebilir, kendi maddelerini ekleyebilirsin.
Liste zamanla kendini günceller ama **sadece dokunmadığın maddeleri**
değiştirir — işaretlediklerine ve senin eklediklerine karışmaz.

Bu liste bir başlangıç noktasıdır, tam liste değildir. Arayüz de bunu söyler.

---

## Tarihler konusunda: `kesin` ve `metinden`

İki kaynak tarihleri farklı yayımlıyor ve bu fark önemli.

| Etiket | Anlamı |
|---|---|
| **kesin** | Kaynak bunu tarih alanı olarak yayımladı. Yorum yok |
| **metinden** | Düz yazıdan çıkarıldı. Resmî sayfadan doğrula |

Hollanda'da tarihler yapısal geliyor, üstelik **AB ve AB dışı başvuranlar için
ayrı ayrı**. Almanya'da "For the summer semester: until 1 November" gibi düz
metin olarak yayımlanıyor ve tarihe çevrilmesi gerekiyor — bu çıkarım hatasız
değil.

Bu yüzden her tarih, çıkarıldığı ham metinle birlikte saklanır ve her programda
hem kaynak sayfanın hem üniversitenin resmî sayfasının linki tutulur. Yanlış
tarih gösteren bir araç, hiç göstermeyenden kötüdür.

### AB dışı başvuranlar dikkat

Türkiye AB dışı sayılıyor. Hollanda verisinde 961 başlangıç kaydının
**614'ünde AB dışı son tarih, genel son tarihten erken** — bazen aylarca:

```
TU Delft — Data Science and AI Technology
  2026-01-15   Eylül 2026 dönemi / AB dışı başvuranlar   [kesin]
  2026-04-01   Eylül 2026 dönemi / AB & EEA başvuranları [kesin]
```

Genel tarihe bakıp başvuru kaçırmak kolay, o yüzden ikisi ayrı satır.

---

## Komut satırı

| Komut | Ne yapar |
|---|---|
| `ingest de` / `ingest nl` | Kataloğu çeker |
| `search "data science" --free` | Arama; `--country`, `--city`, `--limit` |
| `show <id>` | Bir programın tüm gerekliliklerini yazdırır; `--all`, `--refresh` |
| `shortlist add <id>` | Kısa listeye ekler; `--status`, `--notes` |
| `shortlist` | Kısa listeyi gösterir |
| `deadlines` | Yaklaşan tarihler; `--all` kısa liste dışını da katar |
| `reparse` | Kayıtlı veriyi ağa çıkmadan yeniden işler |
| `serve` | Web arayüzünü açar; `--port`, `--host` |

`ingest` seçenekleri: `--subject`, `--limit`, `--refresh` (önbelleği atla),
`--all-languages` (Almanya: İngilizce olmayanlar da), `--all-degrees` ve
`--wo-only` (Hollanda: lisans dahil / sadece araştırma üniversiteleri).

Veritabanı yolu `--db` ile ya da `HET_DB` ortam değişkeniyle değiştirilebilir;
önbellek dizini `HET_CACHE_DIR` ile.

---

## Form doldurucu eklentisi

`extension/` altında ayrı bir Chrome eklentisi. Kurulum ve ayrıntılar:
**[extension/README.md](extension/README.md)**

Kısaca: `chrome://extensions` → Geliştirici modu → Paketlenmemiş öğe yükle →
`extension/` klasörü. Profilini bir kez doldur, başvuru formlarında eklenti
simgesine tıkla.

Formu **senin tarayıcı oturumunda**, **senin tıklamanla** doldurur ve ne
yazılacağını önce listeler. Gönderme kararı sende kalır: eklenti hiçbir zaman
formu göndermez, düğmeye tıklamaz, parola ve ödeme alanlarına dokunmaz.
Alan tanıma İngilizce, Almanca, Hollandaca ve Türkçe çalışır.

Başvuru portallarının çoğu kullanım şartlarında otomasyonu yasaklıyor ve ihlal
başvurunun iptaline yol açabiliyor. Sıkıcılığı almak, riski almadan mümkün.

---

## Veri kaynakları

| Ülke | Kaynak | Nasıl |
|---|---|---|
| Almanya | DAAD "International Programmes" | Arama API'si + program başına detay sayfası (tembel indirilir) |
| Hollanda | Nuffic "Study in NL" Studyfinder | Tek geçiş; gereklilikler ve tarihler liste yanıtında |

Her istek diske önbelleklenir, aynı sunucuya istekler arasında 0.7 saniye
beklenir ve User-Agent aracı dürüstçe tanıtır. Almanya'da pahalı olan detay
sayfaları sadece bir programı açtığında indirilir — kataloğun tamamı için 1500
istek atmak yerine, gerçekten baktığın programlar için birkaç istek.

---

## Testler

```bash
python -m unittest discover -s tests -t .
```

64 test: deadline çıkarımı, belge listesi üretimi, iki adaptörün sayfalaması
ve alan eşlemesi, sunucunun hangi arayüze bağlandığı kontrolü.

Eklentinin 59 testi tarayıcıda çalışır (Chrome'a kurmadan):

```bash
python -m http.server 8799 --bind 127.0.0.1
```

Sonra `http://127.0.0.1:8799/extension/test/matcher-test.html` ve
`.../fill-test.html`.

---

## Sunucuda barındırma

`deploy/` altında systemd birimi ve iki betik var. Uygulamada **kimlik
doğrulama yok** — sokete ulaşan herkes tam yetkiye sahip. Bu yüzden servis
yalnızca `127.0.0.1`'i dinler ve erişim bir özel ağa (Tailscale gibi)
devredilir; ağın kendisi erişim kontrolüdür.

```bash
./deploy/deploy.sh root@SUNUCU ~/.ssh/ANAHTAR
```

İlk seferde sunucuda:

```bash
sudo bash /opt/het/deploy/install.sh
```

Ardından boş bir HTTPS portu seçip yayınla:

```bash
tailscale serve --bg --https=10000 http://127.0.0.1:8765
```

`--host` bayrağı loopback dışına çıkarıldığında sunucu ne dinlediğini söyleyen
bir uyarı basar; public bir arayüz seçilirse uyarı açıkça bunu yapmamanı söyler.

Servis `het` sistem kullanıcısı altında, kod dizinine yazma izni olmadan
çalışır; veritabanı `/var/lib/het` altındadır ve `MemoryMax` ile sınırlıdır.

Kişisel durumunu (kısa liste, işaretlediğin belgeler) iki kurulum arasında
taşımak için:

```bash
python3 deploy/migrate_state.py --from local.db --to server.db --apply
```

Ham dosya kopyası **yapma**: `programs.id` her veritabanında ayrı atanan bir
sayaç, kısa listen yanlış programlara bağlanır. Betik eşleştirmeyi
`(source, source_id)` üzerinden yapar ve `--apply` verilmedikçe sadece ne
yapacağını yazar.

---

## Proje yapısı

```
het/
  models.py          normalize edilmiş veri modeli
  db.py              SQLite şeması ve sorgular
  http.py            önbellekli, hız sınırlı HTTP
  text.py            HTML temizleme
  deadlines.py       serbest metin → tarih
  checklist.py       gereklilik metni → belge listesi
  service.py         CLI ve sunucunun paylaştığı işlemler
  server.py          yerel web sunucusu + JSON API
  cli.py             komut satırı
  web/               arayüz (bağımlılıksız HTML/CSS/JS)
  adapters/
    base.py          adaptör arayüzü
    daad_de.py       Almanya
    studyinnl_nl.py  Hollanda
extension/           Chrome form doldurucu
deploy/              systemd birimi + dağıtım betikleri
tests/               Python testleri
data/                veritabanı ve önbellek (repoya girmez)
```

Yeni bir ülke eklemek bir adaptör yazmak demek: kataloğu gezen bir
`list_programs()` ve — kaynak her şeyi listede vermiyorsa — bir
`fetch_detail()`. Gerisi ortak.

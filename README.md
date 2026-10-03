# wav_to_text
Ses ve video dosyalarını Türkçe metne dönüştüren masaüstü uygulaması.
MP3, MP4, M4A, FLAC, OGG ve FFmpeg'in okuyabildiği diğer ses/video biçimleri
önce WAV olarak hazırlanır, ardından konuşma tanıma işlemine gönderilir.

Kurulum ve çalıştırma (proje kök dizininde):
```shell
python -m pip install -r requirements.txt
python app.py
```

Varsayılan arayüz artık **HTML/CSS/JavaScript + pywebview (WebView2)**.
Python ses işleme kodu arayüzden bağımsızdır. Bir web sitesi ya da Flutter
istemcisi için ileride bu servis katmanına ayrı bir bağlantı katmanı eklenebilir;
şimdilik yalnızca masaüstü uygulaması çalışır.

Eski PyQt arayüzü `eski/pyqt_frontend.py` dosyasında korunur:

```shell
python -m eski.pyqt_app
```

`requirements.txt` artık tüm tanıma motorlarını, yeni WebView arayüzünü ve
eski PyQt arayüzünü tek komutla kurar. Motor başına ayrı paket kurulumu gerekmez.
Kurulum için tek bağımlılık listesi `requirements.txt` dosyasıdır.
Windows'ta Microsoft Edge **WebView2 Runtime** gerekir; modern bir tarayıcı
motoru kullanılır. Kurulum kaynağı: [Microsoft WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).
Bu değişiklik bir EXE/kurulum dosyası üretmez; EXE dağıtımı sonraki adımdır.

Google varsayılan motor olarak korunur. Arayüzdeki **Servis / motor** listesinden
aşağıdaki seçeneklerden biri seçilebilir. Paketler kurulmuş olsa da yalnızca
seçilen motor belleğe yüklenir. Google kullanırken diğer servislerin anahtarları gerekmez.

| Motor | Arayüzde gerekli ayar |
| --- | --- |
| Google | Yok; internet gerekir |
| Faster Whisper (yerel) | Model ve CPU/NVIDIA GPU |
| Whisper (yerel) | Model ve CPU/NVIDIA GPU |
| Vosk (yerel) | Açılmış Türkçe model klasörü |
| Groq Whisper (bulut) | Groq API anahtarı ve model |
| Azure Speech (bulut) | Azure Speech anahtarı ve kaynak bölgesi |
| OpenAI (bulut) | OpenAI API anahtarı ve model; ücretli |

Kurulum komutlarını PyCharm'ın proje için kullandığı sanal ortamda çalıştırın.
Yerel motorların Python sürümü, işletim sistemi ve işlemci desteği farklıdır;
çok eski işletim sistemlerinde paket kurulumu da sınırlayıcı olabilir.
GPU seçimi NVIDIA CUDA bağımlılıklarını otomatik kurmaz; uyumlu CUDA/cuDNN
kurulumu gerekir. CPU varsayılandır. Whisper ses verisini bellekten aldığı
için bu uygulamada ayrıca sistem FFmpeg kurulumu istemez.

Faster Whisper ve Whisper ilk kullanımda seçilen modeli indirir; sonraki
kullanımlarda önbellekteki modelle çalışabilir. İlk başlatma bu nedenle uzun
sürebilir. Model her dönüşümde bir kez yüklenir ve tüm parçalar için kullanılır.
Vosk için [resmî model listesindeki](https://alphacephei.com/vosk/models)
`vosk-model-small-tr-0.3` (35 MB) arşivini indirip açın; ZIP dosyasını değil,
içinde `am`, `conf` gibi dizinlerin bulunduğu model klasörünü seçin.

Python paketleri ile model ağırlıkları ayrı dosyalardır. `requirements.txt`
paketleri kurar; bütün model boyutlarını indirmez. Yerel Whisper modellerini
indirmek ve çalıştırmak için servis ücreti yoktur. Hugging Face'in
`HF_TOKEN` uyarısı ödeme talebi değildir; anahtarsız indirme sınırlarını
hatırlatır. [Hugging Face limitleri](https://huggingface.co/docs/hub/rate-limits).

Faster Whisper'ı kaldırma (Windows / PowerShell):

- Python paketi proje sanal ortamında, `.venv\Lib\site-packages\faster_whisper`
  dizininde bulunur.
- İndirilen modeller varsayılan olarak kullanıcı klasöründeki
  `.cache\huggingface\hub` dizinindedir. Örneğin `tiny` modeli
  `models--Systran--faster-whisper-tiny` klasörünü kullanır.
  `HF_HOME` veya `HF_HUB_CACHE` ayarlanmışsa konum değişebilir.

Dönüşümün bitmesini bekleyip uygulamayı kapatın. Proje kökünde aşağıdaki
komutla yalnızca `tiny` modelini önbellekten kaldırabilirsiniz. Komut silmeden
önce onay ister; önizleme için sonuna `--dry-run` ekleyin. Önbellekteki ortak
dosyaları da hesaba kattığı için klasörü elle silmek yerine bu aracı kullanın.

```powershell
.\.venv\Scripts\python.exe -m huggingface_hub.cli.hf cache rm model/Systran/faster-whisper-tiny
```

Diğer indirilmiş modelleri görmek için:

```powershell
.\.venv\Scripts\python.exe -m huggingface_hub.cli.hf cache ls
```

Python paketini de kaldırmak isterseniz:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall faster-whisper
```

Paket kaldırma, indirilen modeli veya ortak Python bağımlılıklarını kaldırmaz.
Yalnızca modeli silerseniz bir sonraki Faster Whisper kullanımında yeniden
indirilir. Paketi kaldırırsanız bu motor yeniden kurulana kadar çalışmaz.
`requirements.txt` ile kurulumun tekrarlanması paketi yeniden getirir.
Kaynaklar: [Hugging Face önbellek yönetimi](https://huggingface.co/docs/huggingface_hub/guides/manage-cache#clean-your-cache),
[pip uninstall](https://pip.pypa.io/en/stable/cli/pip_uninstall/).

Yerel motorlar ayrı Python sürecinde çalışır. Böylece PyQt'nin eski C++ DLL'leri
ile CTranslate2 gibi motorların DLL'leri aynı süreçte yüklenmez. Motor çökerse
ana uygulama hata gösterir; WAV parçaları ana süreçte temizlenir. Model aynı
işlemde her parça için yeniden yüklenmez. Özellikle başka bir Python betiğinden
yerel motor çağırırken `if __name__ == "__main__":` korumasını kullanın.

Anahtarlar parola alanında gizlenir, uygulama tarafından diske yazılmaz ve
servis değiştirilince temizlenir. İsterseniz arayüz alanlarını boş bırakıp
ortam değişkenlerini kullanabilirsiniz: `GROQ_API_KEY`, `OPENAI_API_KEY`,
`AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `VOSK_MODEL_PATH`.
Arayüze girilen değer ortam değişkenine göre önceliklidir. Anahtarları kaynak
koda veya Git'e eklemeyin. Google ve bulut motorlarında ses seçilen servise
gönderilir; yerel motorlarda tanıma bilgisayarda yapılır. Başka bir motora
otomatik geçiş yapılmaz. İşlem boyunca motor ayarları kilitlenir.

Eski bilgisayarlarda başlangıç önerileri:

- **Vosk:** düşük kaynak tüketimi için ilk aday. Küçük modeller tipik olarak
  yaklaşık 300 MB çalışma belleği kullanır; bu tüm uygulamanın bellek ihtiyacı
  değildir. Kaynak: [Vosk modelleri](https://alphacephei.com/vosk/models).
- **Faster Whisper:** `tiny` veya `base`, CPU ve uygulamanın kullandığı `int8`
  hesaplama ile başlayın. GPU zorunlu değildir; eski işlemcilerde dönüşüm ses
  süresinden uzun sürebilir. Model büyüdükçe bellek ve süre ihtiyacı artar.
  Kaynak: [Faster Whisper](https://github.com/SYSTRAN/faster-whisper).
- **Whisper medium/large:** eski bilgisayarlarda ağır olabilir. Aynı kayıtta
  küçük bir modelle süreyi ve Türkçe doğruluğunu ölçerek seçim yapın.
  Kaynak: [Whisper model tablosu](https://github.com/openai/whisper#available-models-and-languages).

Bulutta bilgisayarın yükü daha azdır; medya hazırlama yine yerelde çalışır.
3 Ekim 2026 tarihinde kontrol edilen ücretsiz seçenekler:

| Servis | Ücretsiz kullanım koşulu |
| --- | --- |
| Google | Mevcut SpeechRecognition anahtarsız bağlantısı korunur; üretim için garantili kota/SLA olarak değerlendirilmemelidir. Bu, ayrı ücretlendirilen Google Cloud Speech-to-Text API'si değildir. |
| Groq Free | Whisper modellerinde 20 istek/dakika, 2.000 istek/gün; saat başına 7.200 saniye (2 saat), gün başına 28.800 saniye (8 saat) ses. Tüm sınırlar birlikte ve organizasyon düzeyinde uygulanır; hesap limitleri esas alınır. |
| Azure Speech F0 | Aylık 5 saat konuşmayı metne çevirme; F0 kaynağı gerekir. Standard/Custom ortak kotadır; batch servisi dahil değildir. Uygulama kısa ses REST tanımasını kullanır. |
| OpenAI API | Kullanıma göre ücretli; uygulama ücretsiz kullanım varsaymaz. |

Güncel koşullar: [Google bağlantısının açıklaması](https://github.com/Uberi/speech_recognition/blob/3.17.0/speech_recognition/recognizers/google.py),
[Groq limitleri](https://console.groq.com/docs/rate-limits),
[Azure fiyatlandırması](https://azure.microsoft.com/en-us/pricing/details/speech/),
[OpenAI fiyatlandırması](https://developers.openai.com/api/docs/pricing).
Groq istekleri arasında en az 3,1 saniye bırakılır; bu, hesabın diğer
kullanımlarından kaynaklanan kota aşımını önlemez. Kota, bağlantı ve zaman
aşımı hataları ilgili parçayı başarısız sayar; başarılı parçalar varsa sonuç
kısmi olarak kaydedilir.

`imageio-ffmpeg` bağımlılığı desteklenen platformlarda FFmpeg çalıştırılabilir
dosyasını beraberinde getirir; Windows için ayrıca PATH ayarı gerekmez.
Kendi FFmpeg kurulumunuzu kullanmak isterseniz `IMAGEIO_FFMPEG_EXE` ortam
değişkenini çalıştırılabilir dosyanın tam yoluna ayarlayabilirsiniz.

Yeni arayüzde motor ayarları, ilerleme, başarı/kısmi sonuç/hata durumu ve metin
önizlemesi bulunur. Metin kopyalanabilir, çıktının klasörü açılabilir. Hata sonrası
ayarlar yeniden açılır ve tekrar denenebilir. Devam eden işin geçici dosyalarını
yarıda bırakmamak için WebView penceresi işlem bitmeden kapanmaz.

Dosya seçicisindeki **Tüm dosyalar** seçeneği, listede bulunmayan uzantıları da
seçmenizi sağlar. Destek, dosyanın gerçek içeriğine ve FFmpeg'in okuyabildiği
codec'lere bağlıdır; belgeler ve ses kanalı olmayan videolar metne çevrilemez.
Birden fazla ses kanalı/akışı olan videolarda ilk ses akışı kullanılır.

Uyumlu mono/stereo PCM WAV dosyaları doğrudan işlenir. Diğer dosyalar her işlem
için ayrı bir geçici klasörde 16 kHz, 16-bit, mono PCM WAV'a çevrilir. Geçici
dosyalar işlem sonunda veya hata oluştuğunda temizlenir. Özgün dosya korunur;
çıktı onun yanına kaydedilir: `video.mp4` → `video.txt`. Aynı adlı metin dosyası
varsa `video(1).txt` gibi bir ad kullanılır.

Ses işleme yöntemi seçilen motora göre değişir:

| Motor | İşleme yöntemi |
| --- | --- |
| Google | 50 saniyelik istekler. |
| Azure | Kısa ses REST bağlantısının 60 saniyelik sınırı için 50 saniyelik istekler. |
| Groq / OpenAI | Gönderilecek ses önce 16 kHz, 16-bit, mono PCM yapılır. WAV başlığı dahil en fazla 24 MB'lık parçalar gönderilir; bu yaklaşık 12 dakika 30 saniyedir. Daha küçük kayıt tek istekte gönderilir. |
| Faster Whisper / Whisper | Dosya tek tanıma oturumunda işlenir; model kendi iç pencerelerini yönetir. 50 saniyede bir tanıma yeniden başlatılmaz. |
| Vosk | Tek tanıyıcı ses dosyasını küçük bloklarla okur; örnekleme dönüşümünün durumu bloklar arasında korunur. |

Bulut yüklemesinde 24 MB seçimi, servislerin 25 MB sınırının altında pay bırakır.
Kaynaklar: [Azure kısa ses](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-speech-to-text-short),
[Groq dosya sınırları](https://console.groq.com/docs/speech-to-text),
[OpenAI dosya sınırları](https://developers.openai.com/api/docs/guides/speech-to-text).

Yerel motorlara yalnızca dosya yolu gönderilir; ses ana arayüz sürecinde
tamamıyla okunup süreçler arasında kopyalanmaz. Whisper motorları uzun kaydın
sesini/özelliklerini yine kendi süreçlerinde belleğe alabilir; uzun kayıtlar
ve büyük modeller daha fazla RAM gerektirir. Vosk ses verisini akışla okur.

TXT paragrafları ses isteği sınırlarından bağımsızdır. Whisper motorlarının
tamamlanmış metin bölümleri yaklaşık bir dakikalık gruplara ayrılır; Vosk'un
tamamlanmış ifadeleri ayrı paragraflara yazılır. Uzun metin paragraflarında
yaklaşık 500 karakterden sonra uygun noktalama işaretinde yeni paragraf açılır.
Noktalama yoksa cümle ortasından zorla bölünmez. Paragraflar arasında boş satır vardır.
Dosya UTF-8 olarak kaydedilir; Türkçe ve diğer Unicode karakterler Windows'un
varsayılan karakter kodlamasından bağımsız olarak korunur.
Anlaşılamayan veya tanıma hatası oluşan bölümler de kendi paragraflarında
belirtilir.

Arayüz önce WAV hazırlama, ardından konuşma tanıma aşamasını gösterir.
Google/Azure/Groq/OpenAI ilerlemesi tamamlanan istekleri, Faster Whisper
ilerlemesi tamamlanan model bölümlerinin zamanlarını, Vosk ilerlemesi işlenen
ses bloklarını izler. Standart Whisper ara ilerleme sağlamaz; yüzde sonuç
geldiğinde 100 olur. Yerel motorlarda dosya tek tanıma birimi sayılır;
`total_chunks` değeri paragraf sayısını göstermez.
WAV hazırlama için zaman aşımı 10 dakika; Google/Azure tanıma isteğinde
30 saniye, daha uzun ses gönderen Groq/OpenAI isteklerinde 180 saniyedir.
SpeechRecognition'ın Azure kimlik doğrulama isteği için kullandığı süre
60 saniyedir. Bunlar toplam iş süresi sınırı değildir; yerel model yükleme
ve çıkarım süresine ağ zaman aşımı uygulanmaz.

Kodun sorumlulukları ayrı dosyalarda tutulur:

| Dosya | Sorumluluk |
| --- | --- |
| `core/backend.py` | WAV okuma, parçalama, konuşma tanıma, geçici dosyalar ve metni kaydetme. PyQt bağımlılığı yoktur. |
| `core/audio_policy.py` | Motorlara göre istek süresi, yükleme boyutu ve ağ zaman aşımı sınırları. |
| `core/transcript_format.py` | Ses parçalama yönteminden bağımsız paragraf düzeni. |
| `core/engines.py` | Motor seçenekleri, ayar kontrolü, yerel model/bulut istemcisi yükleme ve Türkçe tanıma. PyQt bağımlılığı yoktur. |
| `core/local_engine_process.py` | Yerel modelleri GUI'den ayrı süreçte çalıştırır, çökme kodunu okunabilir hataya çevirir. |
| `core/audio_runtime.py` | Pydub'ı paketle gelen FFmpeg'e yönlendirir. |
| `core/media_converter.py` | Ses/video dosyasını geçici PCM WAV'a hazırlar ve geçici dosyaları temizler. PyQt bağımlılığı yoktur. |
| `services/conversion_service.py` | Arayüz bağımsız iş yönetimi; motor listesi, başlatma ve düz veri olarak durum/sonuç sunar. |
| `desktop/webview_app.py` | Web arayüzünü Python servisine bağlar; masaüstü dosya/klasör diyaloglarını yönetir. |
| `desktop/web_ui/` | HTML, CSS ve JavaScript arayüzü; harici CDN veya font indirmesi yoktur. |
| `app.py` | Yeni WebView2 uygulamasını başlatır. |
| `eski/pyqt_frontend.py`, `eski/worker.py`, `eski/pyqt_app.py` | Korunan eski PyQt arayüzü, QThread adaptörü ve başlatıcısı. |

Yeni akış: `app.py` → `desktop/webview_app.py` ↔ `desktop/web_ui/`.
Python bağlantısı → `ConversionService` → `prepare_wav` → `convert_audio`.
Eski akış: `eski/pyqt_app.py` → `eski/pyqt_frontend.py` → `eski/worker.py` → aynı backend.

Backend, arayüz açmadan da kullanılabilir:

```python
from core.backend import convert_audio
from core.engines import RecognitionOptions

if __name__ == "__main__":
    result = convert_audio(
        "kayit.wav", progress_callback=print,
        recognition_options=RecognitionOptions(engine="faster_whisper", model="tiny"),
    )
    print(result.status, result.output_path)
```

`convert_audio` eşzamanlı çalışır; arayüzden çağrılırken `ConversionService`
veya eski Qt arayüzündeki `eski/worker.py` üzerinden çalıştırılmalıdır.
Google konuşma tanıma servisi için internet bağlantısı gerekir.
Sonucun `status` alanı `success`, `partial` veya `failed` olur. Dosya hataları
çağırana istisna olarak iletilir. İsteğe bağlı `progress_callback`, işlenen
parçaların yüzdesini alır.

MP3, MP4 ve diğer medya dosyalarını arayüz açmadan işlemek için:

```python
from core.backend import convert_audio
from core.media_converter import prepare_wav

source = "video.mp4"
with prepare_wav(source) as wav_path:
    result = convert_audio(wav_path, progress_callback=print, output_source_path=source)
print(result.status, result.output_path)
```

`output_source_path`, metnin geçici WAV klasörüne değil özgün dosyanın yanına
kaydedilmesini sağlar. WAV yolu yalnızca `with` bloğu içinde geçerlidir.

Testler (Python 3.11+; medya dönüşümleri gerçek FFmpeg ile çalıştırılır,
konuşma tanıma yanıtları ve yerel modeller taklit edilir; gerçek API çağrısı
yapılmaz veya model indirilmez):

```shell
python -m unittest discover -s tests -v
```

Yalnızca backend testlerini arayüz açmadan çalıştırmak için:

```shell
python -m unittest discover -s tests -p test_backend.py -v
```

Windows'ta gerçek WebView2 penceresi, JavaScript–Python bağlantısı ve önbellekteki
`tiny` modeliyle entegrasyon kontrolü (model önceden indirilmiş olmalı; bulut
çağrısı yapılmaz):

```shell
python tests/smoke_webview.py
```

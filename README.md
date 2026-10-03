# wav_to_text
Ses ve video dosyalarını Türkçe metne dönüştüren masaüstü uygulaması.
MP3, MP4, M4A, FLAC, OGG ve FFmpeg'in okuyabildiği diğer ses/video biçimleri
önce WAV olarak hazırlanır, ardından konuşma tanıma işlemine gönderilir.

Kurulum ve çalıştırma (proje kök dizininde):
```shell
python -m pip install -r requirements.txt
python proje.py
```

Google varsayılan motor olarak korunur. Arayüzdeki **Servis / motor** listesinden
aşağıdaki seçeneklerden biri seçilebilir. Yalnızca seçilen motor yüklenir;
Google kullanırken diğer motorların paketleri veya anahtarları gerekmez.

| Motor | Ek kurulum | Arayüzde gerekli ayar |
| --- | --- | --- |
| Google | Temel `requirements.txt` yeterli | Yok; internet gerekir |
| Faster Whisper (yerel) | `python -m pip install -r requirements-faster-whisper.txt` | Model ve CPU/NVIDIA GPU |
| Whisper (yerel) | `python -m pip install -r requirements-whisper.txt` | Model ve CPU/NVIDIA GPU |
| Vosk (yerel) | `python -m pip install -r requirements-vosk.txt` | Açılmış Türkçe model klasörü |
| Groq Whisper (bulut) | `python -m pip install -r requirements-cloud.txt` | Groq API anahtarı ve model |
| Azure Speech (bulut) | Temel `requirements.txt` yeterli | Azure Speech anahtarı ve kaynak bölgesi |
| OpenAI (bulut) | `python -m pip install -r requirements-cloud.txt` | OpenAI API anahtarı ve model; ücretli |

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

- Arayüz PyQt5 yerleşimleriyle oluşturulur; alanlar seçilen motora göre değişir.

Dosya seçicisindeki **Tüm dosyalar** seçeneği, listede bulunmayan uzantıları da
seçmenizi sağlar. Destek, dosyanın gerçek içeriğine ve FFmpeg'in okuyabildiği
codec'lere bağlıdır; belgeler ve ses kanalı olmayan videolar metne çevrilemez.
Birden fazla ses kanalı/akışı olan videolarda ilk ses akışı kullanılır.

Uyumlu mono/stereo PCM WAV dosyaları doğrudan işlenir. Diğer dosyalar her işlem
için ayrı bir geçici klasörde 16 kHz, 16-bit, mono PCM WAV'a çevrilir. Geçici
dosyalar işlem sonunda veya hata oluştuğunda temizlenir. Özgün dosya korunur;
çıktı onun yanına kaydedilir: `video.mp4` → `video.txt`. Aynı adlı metin dosyası
varsa `video(1).txt` gibi bir ad kullanılır.

TXT çıktısında her 50 saniyelik ses parçası ayrı bir paragrafta yer alır;
paragraflar arasında bir boş satır bulunur. Son bölüm daha kısa olabilir.
Anlaşılamayan veya tanıma hatası oluşan bölümler de kendi paragraflarında
belirtilir. Paragraf sınırları ses parçalarına dayanır; cümle sonlarına göre
belirlenmez.

Arayüz önce WAV hazırlama, ardından konuşma tanıma aşamasını gösterir.
İlerleme yüzdesi konuşma tanıma parçalarını izler. WAV hazırlama için zaman
aşımı 10 dakika; Google, Groq, OpenAI ve Azure tanıma isteğinde ağ zaman
aşımı 30 saniyedir. SpeechRecognition'ın Azure kimlik doğrulama isteği için
kullandığı süre 60 saniyedir. Bunlar toplam iş süresi sınırı değildir; yerel
model yükleme ve çıkarım süresine 30 saniyelik sınır uygulanmaz.

Kodun sorumlulukları ayrı dosyalarda tutulur:

| Dosya | Sorumluluk |
| --- | --- |
| `backend.py` | WAV okuma, parçalama, konuşma tanıma, geçici dosyalar ve metni kaydetme. PyQt bağımlılığı yoktur. |
| `engines.py` | Motor seçenekleri, ayar kontrolü, yerel model/bulut istemcisi yükleme ve Türkçe tanıma. PyQt bağımlılığı yoktur. |
| `media_converter.py` | Ses/video dosyasını geçici PCM WAV'a hazırlar ve geçici dosyaları temizler. PyQt bağımlılığı yoktur. |
| `worker.py` | WAV hazırlamayı ve backend'i QThread üzerinde çalıştırır; aşama, ilerleme, sonuç ve hataları Qt sinyalleriyle arayüze iletir. |
| `frontend.py` | Pencere, düğmeler, dosya seçimi, ilerleme çubuğu ve kullanıcı mesajları. |
| `proje.py` | Uygulamayı başlatan giriş noktası. |

Akış: `proje.py` → `frontend.py` → `worker.py`.
Worker önce `media_converter.prepare_wav`, ardından `backend.convert_audio` çağırır.

Backend, arayüz açmadan da kullanılabilir:

```python
from backend import convert_audio
from engines import RecognitionOptions

result = convert_audio("kayit.wav", progress_callback=print)
print(result.status, result.output_path)

# İsteğe bağlı motor paketini kurduktan sonra:
result = convert_audio(
    "kayit.wav",
    recognition_options=RecognitionOptions(engine="faster_whisper", model="tiny"),
)
```

`convert_audio` eşzamanlı çalışır; arayüzden çağrılırken `worker.py` üzerinden
çalıştırılmalıdır. Google konuşma tanıma servisi için internet bağlantısı gerekir.
Sonucun `status` alanı `success`, `partial` veya `failed` olur. Dosya hataları
çağırana istisna olarak iletilir. İsteğe bağlı `progress_callback`, işlenen
parçaların yüzdesini alır.

MP3, MP4 ve diğer medya dosyalarını arayüz açmadan işlemek için:

```python
from backend import convert_audio
from media_converter import prepare_wav

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

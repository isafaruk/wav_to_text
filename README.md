# wav_to_text
Ses ve video dosyalarını Türkçe metne dönüştüren masaüstü uygulaması.
MP3, MP4, M4A, FLAC, OGG ve FFmpeg'in okuyabildiği diğer ses/video biçimleri
önce WAV olarak hazırlanır, ardından konuşma tanıma işlemine gönderilir.

Kurulum ve çalıştırma (proje kök dizininde):
```shell
python -m pip install -r requirements.txt
python proje.py
```

`imageio-ffmpeg` bağımlılığı desteklenen platformlarda FFmpeg çalıştırılabilir
dosyasını beraberinde getirir; Windows için ayrıca PATH ayarı gerekmez.
Kendi FFmpeg kurulumunuzu kullanmak isterseniz `IMAGEIO_FFMPEG_EXE` ortam
değişkenini çalıştırılabilir dosyanın tam yoluna ayarlayabilirsiniz.

- Arayüz için Qt Designer uygulaması kullanıldı.

Dosya seçicisindeki **Tüm dosyalar** seçeneği, listede bulunmayan uzantıları da
seçmenizi sağlar. Destek, dosyanın gerçek içeriğine ve FFmpeg'in okuyabildiği
codec'lere bağlıdır; belgeler ve ses kanalı olmayan videolar metne çevrilemez.
Birden fazla ses kanalı/akışı olan videolarda ilk ses akışı kullanılır.

Uyumlu mono/stereo PCM WAV dosyaları doğrudan işlenir. Diğer dosyalar her işlem
için ayrı bir geçici klasörde 16 kHz, 16-bit, mono PCM WAV'a çevrilir. Geçici
dosyalar işlem sonunda veya hata oluştuğunda temizlenir. Özgün dosya korunur;
çıktı onun yanına kaydedilir: `video.mp4` → `video.txt`. Aynı adlı metin dosyası
varsa `video(1).txt` gibi bir ad kullanılır.

Arayüz önce WAV hazırlama, ardından konuşma tanıma aşamasını gösterir.
İlerleme yüzdesi konuşma tanıma parçalarını izler. WAV hazırlama için zaman
aşımı 10 dakika, her konuşma tanıma isteği için 30 saniyedir.

Kodun sorumlulukları ayrı dosyalarda tutulur:

| Dosya | Sorumluluk |
| --- | --- |
| `backend.py` | WAV okuma, parçalama, konuşma tanıma, geçici dosyalar ve metni kaydetme. PyQt bağımlılığı yoktur. |
| `media_converter.py` | Ses/video dosyasını geçici PCM WAV'a hazırlar ve geçici dosyaları temizler. PyQt bağımlılığı yoktur. |
| `worker.py` | WAV hazırlamayı ve backend'i QThread üzerinde çalıştırır; aşama, ilerleme, sonuç ve hataları Qt sinyalleriyle arayüze iletir. |
| `frontend.py` | Pencere, düğmeler, dosya seçimi, ilerleme çubuğu ve kullanıcı mesajları. |
| `proje.py` | Uygulamayı başlatan giriş noktası. |

Akış: `proje.py` → `frontend.py` → `worker.py`.
Worker önce `media_converter.prepare_wav`, ardından `backend.convert_audio` çağırır.

Backend, arayüz açmadan da kullanılabilir:

```python
from backend import convert_audio

result = convert_audio("kayit.wav", progress_callback=print)
print(result.status, result.output_path)
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
Google konuşma tanıma yanıtları taklit edilir):

```shell
python -m unittest discover -s tests -v
```

Yalnızca backend testlerini arayüz açmadan çalıştırmak için:

```shell
python -m unittest discover -s tests -p test_backend.py -v
```

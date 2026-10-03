# wav_to_text
Python ile .wav uzantılı dosya .txt dosyasına dönüştürüldü. Projede PyQt5, Pydub, SpeechRecognition kütüphaneleri kullanıldı.

Kurulum ve çalıştırma (proje kök dizininde):
```shell
python -m pip install -r requirements.txt
python proje.py
```

- Arayüz için Qt Designer uygulaması kullanıldı.

Kodun sorumlulukları ayrı dosyalarda tutulur:

| Dosya | Sorumluluk |
| --- | --- |
| `backend.py` | WAV okuma, parçalama, konuşma tanıma, geçici dosyalar ve metni kaydetme. PyQt bağımlılığı yoktur. |
| `worker.py` | Backend'i QThread üzerinde çalıştırır; ilerleme, sonuç ve hataları Qt sinyalleriyle arayüze iletir. |
| `frontend.py` | Pencere, düğmeler, dosya seçimi, ilerleme çubuğu ve kullanıcı mesajları. |
| `proje.py` | Uygulamayı başlatan giriş noktası. |

Akış: `proje.py` → `frontend.py` → `worker.py` → `backend.py`.

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

Testler (Python 3.11+; ağ yanıtları taklit edilir):

```shell
python -m unittest discover -s tests -v
```

Yalnızca backend testlerini arayüz açmadan çalıştırmak için:

```shell
python -m unittest discover -s tests -p test_backend.py -v
```

# RSI Screener - APK Build Guide

## Method 1: Google Colab (EASIEST - No setup needed)

Open Google Colab (colab.research.google.com) and run these cells:

### Cell 1: Upload files
```python
from google.colab import files
# Upload main.py and buildozer.spec when prompted
uploaded = files.upload()
```

### Cell 2: Install Buildozer
```bash
!pip install buildozer cython
!sudo apt-get update
!sudo apt-get install -y python3-pip build-essential git python3-dev \
  ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
  gstreamer1.0-plugins-ugly gstreamer1.0-plugins-good gstreamer1.0-tools \
  autoconf automake libtool pkg-config zip unzip openjdk-17-jdk cmake
```

### Cell 3: Build APK
```bash
!mkdir -p /content/rsi_app
# Move uploaded files
!mv main.py /content/rsi_app/
!mv buildozer.spec /content/rsi_app/
%cd /content/rsi_app
!buildozer android debug 2>&1 | tail -50
```

### Cell 4: Download APK
```python
import glob
from google.colab import files
apk = glob.glob('/content/rsi_app/bin/*.apk')[0]
files.download(apk)
```

---

## Method 2: WSL / Ubuntu Linux

### Step 1: Install dependencies
```bash
sudo apt update
sudo apt install -y python3-pip build-essential git python3-dev \
  ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev \
  autoconf automake libtool pkg-config zip unzip openjdk-17-jdk cmake
```

### Step 2: Install buildozer
```bash
pip install buildozer cython
```

### Step 3: Copy files to Linux
```bash
mkdir -p ~/rsi_app
cp /mnt/d/rough\ code/rsi\ diversion/rsi_mobile/main.py ~/rsi_app/
cp /mnt/d/rough\ code/rsi\ diversion/rsi_mobile/buildozer.spec ~/rsi_app/
cd ~/rsi_app
```

### Step 4: Build
```bash
buildozer android debug
```

### Step 5: Get APK
APK will be in `~/rsi_app/bin/rsiscreener-1.0-arm64-v8a-debug.apk`

Copy to Windows:
```bash
cp ~/rsi_app/bin/*.apk /mnt/d/rough\ code/rsi\ diversion/rsi_mobile/
```

---

## Method 3: GitHub Actions (Automated)

Create a GitHub repo, push main.py + buildozer.spec, and add this workflow:

Create `.github/workflows/build.yml`:
```yaml
name: Build APK
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build APK
        uses: ArtemSBulgworker/buildozer-action@v1
        id: buildozer
        with:
          command: buildozer android debug
          workdir: .
      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: apk
          path: bin/*.apk
```

---

## Install APK on Phone

1. Transfer the `.apk` file to your phone
2. Go to Settings > Security > Enable "Install from Unknown Sources"
3. Open the APK file and tap Install
4. Open the app and scan!

## Notes

- First build takes 15-30 minutes (downloads Android SDK/NDK)
- Subsequent builds are much faster
- App requires internet connection to fetch stock data
- The app is self-contained — no server needed

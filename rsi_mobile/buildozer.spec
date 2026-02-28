[app]
title = RSI Screener
package.name = rsiscreener
package.domain = org.rsi
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy==2.3.1,kivymd==1.1.1,materialyoucolor,exceptiongroup,asyncgui,asynckivy,pillow,certifi,android,pyjnius,openssl
orientation = portrait
fullscreen = 0

# Android permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# Android API
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True

# Use latest python-for-android develop branch for Cython 3 compatibility
p4a.branch = develop

# App icon (optional — place icon.png in same folder)
# icon.filename = icon.png

# Presplash
# presplash.filename = presplash.png

# Build
android.arch = arm64-v8a

# Logging
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1

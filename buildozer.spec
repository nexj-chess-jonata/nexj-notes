[app]
title = NexJ Notes
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/icon.png
package.name = cofre
package.domain = br.oi
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
android.presplash_color = #0A0C1C
source.exclude_dirs = tests,bin,.github,.buildozer
version = 1.0.0
requirements = python3,kivy==2.3.0,cryptography,pyjnius,android
orientation = portrait
fullscreen = 0

android.permissions = USE_BIOMETRIC
android.api = 34
android.minapi = 29
android.archs = arm64-v8a
android.accept_sdk_license = True
android.add_src = java
android.allow_backup = False
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1

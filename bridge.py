"""Ponte com o Android: biometria, Keystore e bloqueio de capturas de tela.
No computador (sem Android) tudo vira "não disponível" e o app usa só a senha.
"""
from kivy.utils import platform

IS_ANDROID = platform == "android"

if IS_ANDROID:
    from android.runnable import run_on_ui_thread  # type: ignore
    from jnius import PythonJavaClass, autoclass, java_method  # type: ignore

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    BiometricHelper = autoclass("br.oi.cofre.BiometricHelper")
    KeystoreHelper = autoclass("br.oi.cofre.KeystoreHelper")

    class _Listener(PythonJavaClass):
        __javainterfaces__ = ["br/oi/cofre/BiometricHelper$Listener"]
        __javacontext__ = "app"

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method("(ZLjava/lang/String;)V")
        def onResult(self, ok, msg):
            self.callback(bool(ok), str(msg) if msg else "")

    _keep = []  # evita que o coletor de lixo apague o listener

    @run_on_ui_thread
    def set_secure():
        """Bloqueia prints e a miniatura do app na lista de recentes."""
        PythonActivity.mActivity.getWindow().addFlags(0x2000)  # FLAG_SECURE

    def biometric_available():
        try:
            return bool(BiometricHelper.available(PythonActivity.mActivity))
        except Exception:
            return False

    def authenticate(title, callback):
        listener = _Listener(callback)
        _keep.append(listener)
        BiometricHelper.authenticate(PythonActivity.mActivity, title, listener)

    def keystore_encrypt(text):
        return str(KeystoreHelper.encrypt(text))

    def keystore_decrypt(text):
        return str(KeystoreHelper.decrypt(text))

    def keystore_delete():
        try:
            KeystoreHelper.deleteKey()
        except Exception:
            pass

else:

    def set_secure():
        pass

    def biometric_available():
        return False

    def authenticate(title, callback):
        callback(False, "Biometria indisponível neste dispositivo.")

    def keystore_encrypt(text):
        raise RuntimeError("sem Keystore")

    def keystore_decrypt(text):
        raise RuntimeError("sem Keystore")

    def keystore_delete():
        pass

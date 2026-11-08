import json
import os
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import bridge
from vault import TRASH_DAYS, Vault, WeakPassword, WrongPassword

BG = (0.07, 0.08, 0.11, 1)
CARD = (0.14, 0.16, 0.21, 1)
ACCENT = (0.2, 0.55, 0.95, 1)
DANGER = (0.8, 0.18, 0.22, 1)
MUTED = (0.6, 0.65, 0.75, 1)
WHITE = (1, 1, 1, 1)


def btn(text, cb=None, color=CARD, **kw):
    b = Button(text=text, background_normal="", background_color=color,
               color=WHITE, size_hint_y=None, height=dp(48), **kw)
    if cb:
        b.bind(on_release=lambda *_: cb())
    return b


def lbl(text, size=16, color=WHITE, **kw):
    kw.setdefault("halign", "left")
    kw.setdefault("valign", "middle")
    l = Label(text=text, font_size=dp(size), color=color, **kw)
    l.bind(size=lambda i, s: setattr(i, "text_size", s))
    return l


def field(hint, password=False, **kw):
    return TextInput(hint_text=hint, password=password, multiline=False,
                     size_hint_y=None, height=dp(48), write_tab=False,
                     padding=(dp(12), dp(14)), **kw)


def fmt(ts):
    return time.strftime("%d/%m %H:%M", time.localtime(ts))


class CofreApp(App):
    title = "NexJ Notes"

    # ---------- ciclo de vida ----------
    def build(self):
        Window.clearcolor = BG
        folder = os.path.join(self.user_data_dir, "cofre")
        self.vault = Vault(folder)
        self.vault.on_kek_changed = self._kek_changed
        self.prefs_path = os.path.join(folder, "prefs.json")
        self.bio_path = os.path.join(folder, "bio.bin")
        self.current_id = None
        self._authing = False
        self._fails = 0
        self._blocked_until = 0
        self.sm = ScreenManager(transition=NoTransition())
        for n in ("lock", "home", "editor", "trash", "settings"):
            self.sm.add_widget(Screen(name=n))
        Window.bind(on_keyboard=self._key)
        return self.sm

    def on_start(self):
        bridge.set_secure()
        self.show_lock(auto_bio=True)

    def on_pause(self):
        if self._authing:
            return True
        if self.vault.unlocked:
            self.show_lock()
        return True

    def on_resume(self):
        if (not self._authing and not self.vault.unlocked
                and self._bio_enabled() and self.sm.current == "lock"):
            Clock.schedule_once(lambda dt: self.bio_unlock(), 0.3)

    def _key(self, win, key, *args):
        if key == 27:
            cur = self.sm.current
            if cur == "editor":
                self.save_and_back()
                return True
            if cur in ("trash", "settings"):
                self.show_home()
                return True
        return False

    def _show(self, name, widget):
        for n in ("home", "editor", "trash", "settings", "lock"):
            if n != name:
                self.sm.get_screen(n).clear_widgets()
        s = self.sm.get_screen(name)
        s.clear_widgets()
        s.add_widget(widget)
        self.sm.current = name

    # ---------- preferências / biometria ----------
    def _prefs(self):
        try:
            with open(self.prefs_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_prefs(self, d):
        with open(self.prefs_path, "w", encoding="utf-8") as f:
            json.dump(d, f)

    def _bio_enabled(self):
        return (self._prefs().get("bio") and os.path.exists(self.bio_path)
                and bridge.biometric_available())

    def _store_kek(self):
        with open(self.bio_path, "w", encoding="utf-8") as f:
            f.write(bridge.keystore_encrypt(self.vault.export_kek()))

    def _kek_changed(self, kek):
        if self._prefs().get("bio"):
            try:
                self._store_kek()
            except Exception:
                self._disable_bio()

    def _disable_bio(self):
        p = self._prefs()
        p["bio"] = False
        self._save_prefs(p)
        if os.path.exists(self.bio_path):
            os.remove(self.bio_path)
        bridge.keystore_delete()

    # ---------- utilitários de UI ----------
    def info(self, title, msg):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        box.add_widget(lbl(msg, 15))
        pop = Popup(title=title, content=box, size_hint=(0.9, None), height=dp(230))
        box.add_widget(btn("OK", pop.dismiss, ACCENT))
        pop.open()

    def confirm(self, title, msg, on_yes, yes_text="Confirmar", color=DANGER):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        box.add_widget(lbl(msg, 15))
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        pop = Popup(title=title, content=box, size_hint=(0.92, None), height=dp(280))
        row.add_widget(btn("Cancelar", pop.dismiss))
        row.add_widget(btn(yes_text, lambda: (pop.dismiss(), on_yes()), color))
        box.add_widget(row)
        pop.open()

    # ---------- tela de bloqueio ----------
    def show_lock(self, auto_bio=False):
        self.vault.lock()
        self.current_id = None
        new = not self.vault.exists()
        root = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))
        root.add_widget(Widget())
        root.add_widget(lbl("NexJ Notes", 30, bold=True, halign="center",
                            size_hint_y=None, height=dp(50)))
        root.add_widget(lbl(
            "Crie uma senha mestra. Sem ela, ninguém (nem você) abre o cofre."
            if new else "Digite sua senha para abrir.",
            14, MUTED, halign="center", size_hint_y=None, height=dp(44)))
        self.pw = field("Senha", True)
        root.add_widget(self.pw)
        self.pw2 = None
        if new:
            self.pw2 = field("Repita a senha", True)
            root.add_widget(self.pw2)
        self.msg = lbl("", 14, (1, 0.5, 0.5, 1), halign="center",
                       size_hint_y=None, height=dp(30))
        root.add_widget(self.msg)
        root.add_widget(btn("Criar cofre" if new else "Entrar", self.submit_lock, ACCENT))
        if not new and self._bio_enabled():
            root.add_widget(btn("Usar biometria", self.bio_unlock))
        root.add_widget(Widget())
        self._show("lock", root)
        if auto_bio and not new and self._bio_enabled():
            Clock.schedule_once(lambda dt: self.bio_unlock(), 0.4)

    def submit_lock(self):
        pw = self.pw.text
        if self.pw2 is not None:
            if pw != self.pw2.text:
                self.msg.text = "As senhas não coincidem."
                return
            try:
                self.vault.create(pw)
            except WeakPassword as e:
                self.msg.text = str(e)
                return
            self.show_home()
            if bridge.biometric_available():
                self.confirm("Biometria", "Quer abrir o cofre com a digital/rosto?",
                             self.toggle_bio, "Ativar", ACCENT)
            return
        if time.time() < self._blocked_until:
            self.msg.text = f"Aguarde {int(self._blocked_until - time.time())}s."
            return
        try:
            self.vault.unlock(pw)
        except WrongPassword:
            self._fails += 1
            if self._fails >= 5:
                self._blocked_until = time.time() + 30
                self._fails = 0
                self.msg.text = "Muitas tentativas. Aguarde 30s."
            else:
                self.msg.text = "Senha incorreta."
            self.pw.text = ""
            return
        self._fails = 0
        self.show_home()

    def bio_unlock(self):
        if self._authing:
            return
        self._authing = True
        bridge.authenticate(
            "Abrir NexJ Notes",
            lambda ok, m: Clock.schedule_once(lambda dt: self._after_bio(ok, m)))

    def _after_bio(self, ok, msg):
        self._authing = False
        if not ok:
            if msg and hasattr(self, "msg") and self.sm.current == "lock":
                self.msg.text = "Use sua senha."
            return
        try:
            with open(self.bio_path, "r", encoding="utf-8") as f:
                kek = bridge.keystore_decrypt(f.read())
            self.vault.unlock_with_kek(kek)
        except Exception:
            self._disable_bio()
            self.show_lock()
            self.msg.text = "Biometria inválida. Entre com a senha."
            return
        self.show_home()

    # ---------- lista de notas ----------
    def show_home(self):
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        top.add_widget(lbl("Minhas notas", 22, bold=True))
        top.add_widget(btn("Trancar", self.show_lock, size_hint_x=None, width=dp(90)))
        root.add_widget(top)
        self.search = field("Buscar")
        self.search.bind(text=lambda i, t: self._fill_home(t))
        root.add_widget(self.search)
        self.home_grid = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        self.home_grid.bind(minimum_height=self.home_grid.setter("height"))
        sv = ScrollView()
        sv.add_widget(self.home_grid)
        root.add_widget(sv)
        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        bar.add_widget(btn("Nova nota", lambda: self.show_editor(None), ACCENT))
        self.trash_btn = btn("Lixeira", self.show_trash)
        bar.add_widget(self.trash_btn)
        bar.add_widget(btn("Ajustes", self.show_settings))
        root.add_widget(bar)
        self._show("home", root)
        self._fill_home("")

    def _row(self, n, cb, extra=""):
        preview = (n["body"] or "").replace("\n", " ")[:70]
        b = Button(text=f"[b]{n['title']}[/b]\n{extra}{preview}", markup=True,
                   background_normal="", background_color=CARD, color=WHITE,
                   size_hint_y=None, height=dp(64), halign="left", valign="middle")
        b.bind(size=lambda i, s: setattr(i, "text_size", (s[0] - dp(24), s[1])))
        b.bind(on_release=lambda *_: cb(n["id"]))
        return b

    def _fill_home(self, query=""):
        g = self.home_grid
        g.clear_widgets()
        q = query.strip().lower()
        items = [n for n in self.vault.notes()
                 if not q or q in n["title"].lower() or q in n["body"].lower()]
        if not items:
            g.add_widget(lbl("Nenhuma nota." if not q else "Nada encontrado.",
                             15, MUTED, size_hint_y=None, height=dp(60)))
        for n in items:
            g.add_widget(self._row(n, self.show_editor, extra=fmt(n["updated"]) + "  "))
        c = len(self.vault.trashed())
        self.trash_btn.text = f"Lixeira ({c})" if c else "Lixeira"

    # ---------- editor ----------
    def show_editor(self, nid):
        self.current_id = nid
        n = self.vault.get(nid) if nid else None
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        self.e_title = field("Título")
        self.e_title.text = n["title"] if n else ""
        self.e_body = TextInput(hint_text="Escreva aqui...", multiline=True,
                                padding=(dp(12), dp(12)))
        self.e_body.text = n["body"] if n else ""
        root.add_widget(self.e_title)
        root.add_widget(self.e_body)
        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        bar.add_widget(btn("Salvar e voltar", self.save_and_back, ACCENT))
        if n:
            bar.add_widget(btn("Para a lixeira", self.trash_current, DANGER))
        root.add_widget(bar)
        self._show("editor", root)

    def save_and_back(self):
        title = self.e_title.text.strip()
        body = self.e_body.text
        if title or body.strip():
            if not title:
                title = body.strip().split("\n")[0][:40]
            self.vault.save_note(self.current_id, title, body)
        self.show_home()

    def trash_current(self):
        if self.current_id:
            self.vault.trash(self.current_id)
        self.show_home()

    # ---------- lixeira ----------
    def show_trash(self):
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        root.add_widget(lbl("Lixeira", 22, bold=True, size_hint_y=None, height=dp(48)))
        root.add_widget(lbl(
            f"Notas aqui são destruídas sozinhas após {TRASH_DAYS} dias. "
            "Toque numa nota para restaurar ou destruir.",
            13, MUTED, size_hint_y=None, height=dp(44)))
        self.trash_grid = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        self.trash_grid.bind(minimum_height=self.trash_grid.setter("height"))
        sv = ScrollView()
        sv.add_widget(self.trash_grid)
        root.add_widget(sv)
        root.add_widget(btn("Esvaziar lixeira (destruir tudo)", self._ask_empty, DANGER))
        root.add_widget(btn("Voltar", self.show_home))
        self._show("trash", root)
        self._fill_trash()

    def _fill_trash(self):
        g = self.trash_grid
        g.clear_widgets()
        items = self.vault.trashed()
        if not items:
            g.add_widget(lbl("Lixeira vazia.", 15, MUTED, size_hint_y=None, height=dp(60)))
        for n in items:
            g.add_widget(self._row(n, self._trash_actions,
                                   extra="apagada " + fmt(n["deleted"]) + "  "))

    def _trash_actions(self, nid):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        pop = Popup(title="O que fazer com a nota?", content=box,
                    size_hint=(0.9, None), height=dp(300))

        def restore():
            pop.dismiss()
            self.vault.restore(nid)
            self._fill_trash()

        def destroy():
            pop.dismiss()
            self.confirm("Destruir em definitivo",
                         "Esta nota será apagada para sempre e não poderá ser recuperada.",
                         lambda: (self.vault.destroy(nid), self._fill_trash()),
                         "Destruir")

        box.add_widget(btn("Restaurar", restore, ACCENT))
        box.add_widget(btn("Destruir em definitivo", destroy, DANGER))
        box.add_widget(btn("Cancelar", pop.dismiss))
        pop.open()

    def _ask_empty(self):
        if not self.vault.trashed():
            return
        self.confirm("Esvaziar lixeira",
                     "Todas as notas da lixeira serão destruídas para sempre.",
                     lambda: (self.vault.empty_trash(), self._fill_trash()), "Destruir tudo")

    # ---------- ajustes ----------
    def show_settings(self):
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        root.add_widget(lbl("Ajustes", 22, bold=True, size_hint_y=None, height=dp(48)))
        on = bool(self._prefs().get("bio"))
        root.add_widget(btn("Biometria: ATIVADA (toque para desativar)" if on
                            else "Ativar biometria", self.toggle_bio))
        root.add_widget(btn("Alterar senha", self.change_password_popup))
        root.add_widget(Widget())
        root.add_widget(lbl(
            "Notas ficam cifradas (AES) só neste aparelho. Prints e miniatura "
            "do app ficam bloqueados. O app tranca sozinho ao sair da tela.",
            13, MUTED, size_hint_y=None, height=dp(70)))
        root.add_widget(btn("DESTRUIR COFRE INTEIRO", self._ask_wipe, DANGER))
        root.add_widget(btn("Voltar", self.show_home))
        self._show("settings", root)

    def toggle_bio(self):
        if self._prefs().get("bio"):
            self._disable_bio()
            if self.sm.current == "settings":
                self.show_settings()
            return
        if not bridge.biometric_available():
            self.info("Biometria", "Biometria indisponível ou não cadastrada neste aparelho.")
            return
        self._authing = True
        bridge.authenticate(
            "Confirme para ativar",
            lambda ok, m: Clock.schedule_once(lambda dt: self._bio_enable_done(ok)))

    def _bio_enable_done(self, ok):
        self._authing = False
        if not ok:
            return
        try:
            self._store_kek()
            p = self._prefs()
            p["bio"] = True
            self._save_prefs(p)
        except Exception as e:
            self.info("Erro", f"Não foi possível ativar: {e}")
            return
        if self.sm.current == "settings":
            self.show_settings()

    def change_password_popup(self):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        old = field("Senha atual", True)
        new = field("Nova senha", True)
        new2 = field("Repita a nova senha", True)
        msg = lbl("", 13, (1, 0.5, 0.5, 1), size_hint_y=None, height=dp(24))
        pop = Popup(title="Alterar senha", content=box,
                    size_hint=(0.92, None), height=dp(380))

        def go():
            if new.text != new2.text:
                msg.text = "As senhas novas não coincidem."
                return
            try:
                self.vault.change_password(old.text, new.text)
            except (WrongPassword, WeakPassword) as e:
                msg.text = str(e)
                return
            pop.dismiss()
            self.info("Pronto", "Senha alterada.")

        for w in (old, new, new2, msg):
            box.add_widget(w)
        box.add_widget(btn("Alterar", go, ACCENT))
        pop.open()

    def _ask_wipe(self):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        box.add_widget(lbl("Isto apaga TODAS as notas e a senha, sem volta. "
                           "Digite DESTRUIR para confirmar.", 14))
        t = field("DESTRUIR")
        box.add_widget(t)
        pop = Popup(title="Destruir cofre inteiro", content=box,
                    size_hint=(0.92, None), height=dp(320))

        def go():
            if t.text.strip() != "DESTRUIR":
                return
            pop.dismiss()
            self.vault.wipe_all()
            for p in (self.prefs_path, self.bio_path):
                if os.path.exists(p):
                    os.remove(p)
            bridge.keystore_delete()
            self.show_lock()

        box.add_widget(btn("Destruir tudo", go, DANGER))
        box.add_widget(btn("Cancelar", pop.dismiss))
        pop.open()


if __name__ == "__main__":
    CofreApp().run()

import threading
import time
import webbrowser
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def sort_by_date(url: str) -> str:
    """Добавляет сортировку 'по дате' (s=104) и убирает номер страницы."""
    p = urlparse(url.strip())
    q = dict(parse_qsl(p.query))
    q["s"] = "104"
    q.pop("p", None)
    return urlunparse(p._replace(query=urlencode(q)))


def fetch_items(url: str):
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Авито ответило кодом {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for node in soup.select('[data-marker="item"]'):
        a = node.select_one('a[data-marker="item-title"]') or node.select_one("a[href]")
        if not a:
            continue
        href = a.get("href", "")
        if href.startswith("/"):
            href = "https://www.avito.ru" + href
        title = a.get("title") or a.get_text(strip=True) or "Без названия"
        price_tag = node.select_one('[itemprop="price"]')
        price = price_tag.get("content") if price_tag else ""
        if not price:
            pt = node.select_one('[data-marker="item-price"]')
            price = pt.get_text(" ", strip=True) if pt else ""
        item_id = node.get("data-item-id") or href
        items.append({"id": item_id, "title": title, "price": price, "link": href})
    if not items:
        raise RuntimeError("Объявления не найдены (возможно, капча/блокировка)")
    return items


def notify(title, message):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        pass


class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=8, spacing=8, **kw)
        self.running = False
        self.seen = set()

        self.url_input = TextInput(
            hint_text="Вставь ссылку поиска с Авито",
            multiline=False, size_hint_y=None, height=48,
        )
        self.interval_input = TextInput(
            text="60", hint_text="Интервал, сек", multiline=False,
            input_filter="int", size_hint_y=None, height=48,
        )
        self.btn = Button(text="Старт", size_hint_y=None, height=52)
        self.btn.bind(on_release=self.toggle)
        self.status = Label(text="Остановлено", size_hint_y=None, height=30)

        self.list = GridLayout(cols=1, spacing=6, size_hint_y=None)
        self.list.bind(minimum_height=self.list.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.list)

        for w in (self.url_input, self.interval_input, self.btn, self.status, scroll):
            self.add_widget(w)

    def toggle(self, *_):
        if self.running:
            self.running = False
            self.btn.text = "Старт"
            self.status.text = "Остановлено"
            return
        url = self.url_input.text.strip()
        if "avito" not in url:
            self.status.text = "Нужна ссылка с Авито"
            return
        self.seen.clear()
        self.running = True
        self.btn.text = "Стоп"
        threading.Thread(target=self.worker, args=(sort_by_date(url),), daemon=True).start()

    def set_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.status, "text", text))

    def worker(self, url):
        first = True
        while self.running:
            try:
                items = fetch_items(url)
                new = [i for i in items if i["id"] not in self.seen]
                for i in items:
                    self.seen.add(i["id"])
                if first:
                    first = False  # первый проход только запоминаем текущие
                    self.set_status(f"Слежу. Запомнено: {len(items)}")
                elif new:
                    for i in reversed(new):
                        Clock.schedule_once(lambda dt, i=i: self.add_item(i))
                        notify("Новое на Авито", f"{i['title']} — {i['price']}")
                    self.set_status(f"Новых: {len(new)} ({time.strftime('%H:%M:%S')})")
                else:
                    self.set_status(f"Нет новых ({time.strftime('%H:%M:%S')})")
            except Exception as e:
                self.set_status(f"Ошибка: {e}")
            try:
                delay = max(20, int(self.interval_input.text or 60))
            except ValueError:
                delay = 60
            for _ in range(delay):
                if not self.running:
                    return
                time.sleep(1)

    def add_item(self, item):
        b = Button(
            text=f"{item['title']}\n{item['price']} ₽",
            size_hint_y=None, height=80, halign="center",
        )
        b.bind(width=lambda inst, w: setattr(inst, "text_size", (w - 20, None)))
        b.bind(on_release=lambda *_: webbrowser.open(item["link"]))
        self.list.add_widget(b, index=len(self.list.children))


class AvitoApp(App):
    def build(self):
        return Root()


if __name__ == "__main__":
    AvitoApp().run()

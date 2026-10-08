# VKover

Telegram-стильная библиотека-юзербот для ВКонтакте на веб-токенах (api.vk.ru, Long Poll v3).

VK API после сентября 2026 закрыл сторонние приложения и токены Kate/Маруся. VKover работает как настоящий веб-клиент: логин через браузер один раз, дальше — REST API + Long Poll.

## Установка

```bash
pip install .
```

## Первый запуск (получение токена)

```bash
vkover-login --profile ./vk_profile --token-file ./web_token.json
```

Откроется Chromium (нужен Xvfb на сервере). Войдите в аккаунт VK. Токен появится в `web_token.json`.

## Использование

```python
from vkover import VKover, NewMessage

vk = VKover.from_files("web_token.json", profile_dir="./vk_profile")

@vk.on(NewMessage)
async def handler(event):
    print(event.peer_id, event.text)

vk.run()
```

Отправка и запросы:

```python
vk.send(peer_id=100, text="привет")
vk.send_message_request(100, "сообщение", reply_to_cmid=5)
vk.send_reaction_request(100, cmid=5, reaction_id=3)
vk.delete_reaction_request(100, cmid=5)
vk.edit_message_request(100, message_id=6692, text="исправлено")
vk.delete_message_request([6692, 6693])
vk.forward_request(100, [11, 12], "пересылка")
vk.set_typing_request(100)
vk.request("messages.getConversations", count=20)
```

## Токены и продление

Веб-токен живёт ~сутки. При передаче `profile_dir` в `VKover.from_files` библиотека автоматически открывает headless-Chromium и обновляет токен из localStorage профиля.

## Тесты и бенчмарки

```bash
pip install pytest pytest-benchmark
pytest tests/ -q
```

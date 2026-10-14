import json
import os
import urllib.request
import urllib.parse

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
FORCE_SUMMARY = os.environ.get("FORCE_SUMMARY", "false").lower() == "true"

RELEASES_API_URL = "https://api.github.com/repos/INCY-DEV/incy-platforms/releases"
RELEASE_JSON_URL = "https://raw.githubusercontent.com/INCY-DEV/incy-platforms/main/RELEASE.json"
STATE_FILE = "state.json"


def http_get_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "INCY-GitHub-Action-Monitor"
    }
    if GITHUB_TOKEN and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status == 200


def fetch_incy_versions() -> dict:
    result = {
        "desktop": {"version": "Неизвестно", "url": "https://github.com/INCY-DEV/incy-platforms/releases", "notes": ""},
        "android": {"version": "Неизвестно", "url": "https://github.com/INCY-DEV/incy-platforms/releases", "notes": "", "apk": ""},
        "ios": {"version": "Неизвестно", "build": "", "url": "https://apps.apple.com/app/incy/id6756943388"},
    }

    try:
        manifest = http_get_json(RELEASE_JSON_URL)
        if "desktop" in manifest:
            result["desktop"]["version"] = manifest["desktop"].get("version", "Неизвестно")
        if "android" in manifest:
            result["android"]["version"] = manifest["android"].get("version", "Неизвестно")
            result["android"]["apk"] = manifest["android"].get("download", "")
        if "ios" in manifest:
            result["ios"]["version"] = manifest["ios"].get("version", "Неизвестно")
            result["ios"]["build"] = manifest["ios"].get("build", "")
            result["ios"]["url"] = manifest["ios"].get("AppStore", result["ios"]["url"])
    except Exception as e:
        print(f"Ошибка чтения RELEASE.json: {e}")

    try:
        releases = http_get_json(RELEASES_API_URL)
        found_d, found_a = False, False
        for rel in releases:
            if rel.get("draft"):
                continue
            tag = rel.get("tag_name", "")
            if tag.startswith("desktop-v") and not found_d:
                result["desktop"]["version"] = tag.replace("desktop-v", "")
                result["desktop"]["url"] = rel.get("html_url", result["desktop"]["url"])
                result["desktop"]["notes"] = (rel.get("body") or "").strip()
                found_d = True
            elif tag.startswith("android-v") and not found_a:
                result["android"]["version"] = tag.replace("android-v", "")
                result["android"]["url"] = rel.get("html_url", result["android"]["url"])
                result["android"]["notes"] = (rel.get("body") or "").strip()
                found_a = True
            if found_d and found_a:
                break
    except Exception as e:
        print(f"Ошибка чтения Releases API: {e}")

    return result


def format_summary(data: dict) -> str:
    d, a, i = data["desktop"], data["android"], data["ios"]
    apk_str = f" • <a href='{a['apk']}'>Скачать APK</a>" if a.get("apk") else ""
    build_str = f" (build {i['build']})" if i.get("build") else ""
    return (
        "📦 <b>Актуальные версии INCY на все платформы</b>\n\n"
        f"🖥 <b>Desktop (Win / macOS / Linux):</b> <code>v{d['version']}</code>\n"
        f"└ <a href='{d['url']}'>Страница релиза на GitHub</a>\n\n"
        f"🤖 <b>Android / Android TV:</b> <code>v{a['version']}</code>\n"
        f"└ <a href='{a['url']}'>Релиз на GitHub</a>{apk_str}\n\n"
        f"🍏 <b>iOS / Apple TV:</b> <code>v{i['version']}</code>{build_str}\n"
        f"└ <a href='{i['url']}'>Открыть в App Store</a>"
    )


def main():
    data = fetch_incy_versions()
    current = {
        "desktop": data["desktop"]["version"],
        "android": data["android"]["version"],
        "ios": data["ios"]["version"],
    }

    saved = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            saved = {}

    # Первый запуск или ручной запрос сводки
    if not saved or FORCE_SUMMARY:
        send_telegram_message(format_summary(data))
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        print("Отправлена сводка версий и сохранено состояние.")
        return

    # Проверка изменений по каждой платформе
    titles = {
        "desktop": "🖥 Desktop (Windows / macOS / Linux)",
        "android": "🤖 Android / Android TV",
        "ios": "🍏 iOS / Apple TV",
    }

    changed = False
    for platform, new_ver in current.items():
        old_ver = saved.get(platform)
        if new_ver != "Неизвестно" and old_ver and new_ver != old_ver:
            changed = True
            notes = data[platform].get("notes", "")
            notes_block = f"\n\n<b>Что нового:</b>\n<pre>{notes[:500]}</pre>" if notes else ""
            msg = (
                "🚀 <b>Вышло новое обновление INCY!</b>\n\n"
                f"<b>Платформа:</b> {titles[platform]}\n"
                f"<b>Версия:</b> <code>v{old_ver}</code> ➡️ <code>v{new_ver}</code>\n"
                f"🔗 <a href='{data[platform]['url']}'>Перейти к загрузке</a>"
                f"{notes_block}"
            )
            send_telegram_message(msg)

    if changed:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        print("Обнаружены новые версии, state.json обновлён.")
    else:
        print("Новых версий нет.")


if __name__ == "__main__":
    main()

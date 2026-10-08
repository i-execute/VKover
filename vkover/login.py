import argparse
import json
import os

from vkover.auth import TokenRefresher

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser(description="VKover login helper")
    ap.add_argument("--profile", default="./vk_profile")
    ap.add_argument("--token-file", default="./web_token.json")
    args = ap.parse_args()
    os.makedirs(args.profile, exist_ok=True)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            args.profile, headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://vk.ru/", wait_until="domcontentloaded", timeout=60000)
        print("Log into VK in the opened window...")
        import time
        deadline = time.time() + 900
        tok = None
        while time.time() < deadline and not tok:
            keys = page.evaluate("() => Object.keys(localStorage)")
            for k in keys:
                if "web_token:login:auth" in k:
                    v = page.evaluate(f'() => localStorage.getItem("{k}")')
                    try:
                        tok = json.loads(v)["access_token"]
                    except (ValueError, KeyError, TypeError):
                        pass
            time.sleep(2)
        ctx.close()

    if tok:
        with open(args.token_file, "w", encoding="utf-8") as f:
            json.dump({"access_token": tok}, f)
        print(f"token saved to {args.token_file}")
    else:
        raise SystemExit("no token found after timeout")


if __name__ == "__main__":
    main()

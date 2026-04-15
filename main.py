import asyncio
import base64
import binascii
import datetime
import json
import os
import re
import time
import urllib.parse

import cv2
import numpy as np
import requests
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright
from message_styles import generate_message 

# ================= Configuration =================
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "cli_a933badfd57bdbde")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "zliAQFZ61YOVdhSz8vecahozbGz6Ym5j")
FEISHU_USER_ID = os.getenv("FEISHU_USER_ID", "ou_67774e11bf8d8cf2b981cf2b09bac038")
DOUYIN_PASSWORD = os.getenv("DOUYIN_PASSWORD", "Wan1314520.")
COOKIE_FILE = os.getenv("COOKIE_FILE", "douyin_cookies.json")
CF_TRIGGER_URL = os.getenv(
    "CF_TRIGGER_URL",
    "https://douyin-trigger.w17826038535.workers.dev/?key=Wan1314520",
)
GITHUB_ACTIONS_URL = os.getenv(
    "GITHUB_ACTIONS_URL",
    "https://github.com/wsxvg/douyin-huohua-wds/actions/workflows/main.yml",
).strip()
ENABLE_SEARCH_FALLBACK = os.getenv("ENABLE_SEARCH_FALLBACK", "0").strip() == "1"
RESET_BETWEEN_CONTACTS = os.getenv(
    "RESET_BETWEEN_CONTACTS",
    "1" if os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true" else "0",
).strip() == "1"
DESKTOP_USER_AGENT = os.getenv(
    "DOUYIN_USER_AGENT",
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    ),
)

FRIENDS = [
    "老婆",
    "徐雨栋",
    "刘洋",
    "初生",
    "何松平",
    "gqq",
    "申佳星",
    "小康",
]

CHAT_URL = "https://www.douyin.com/chat"
CHAT_LIST_SELECTOR = ".componentsLeftPanelboxList"
CONVERSATION_ITEM_SELECTOR = ".conversationConversationItemwrapper"
MFA_SELECTOR = "#uc-second-verify"
SUBMIT_BTN_CSS = 'div[class*="uc_verification_component_btn"]'
SEARCH_INPUT_SELECTOR = "input[placeholder='搜索']"
SEARCH_RESULT_GROUP_SELECTOR = ".SearchPanelgroupbox"
SEARCH_CHAT_BUTTON_SELECTOR = ".SearchPanelitemchat_btn"
CAPTCHA_CONTAINER_SELECTOR = "#captcha_container"
HEADER_INFO_SELECTOR = "#ei-conversation-header-info"
HEADER_TITLE_SELECTOR = ".RightPanelHeadertitle"
STREAK_VALUE_SELECTOR = ".commonStreaknormalText"
MESSAGE_EDITOR_SELECTOR = ".zone-container.editor-kit-container[contenteditable='true']"
RE_VERIFY_PWD_OPT = re.compile(r"验证登录密码|Verify.*?Password", re.IGNORECASE)

REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_PAGE_TIMEOUT_MS = 20_000
SHORT_POLL_SECONDS = 0.8
QR_FETCH_TIMEOUT_SECONDS = 16
LOGIN_WAIT_SECONDS = 60
LOGIN_REFRESH_SECONDS = 12
SEND_RETRY_COUNT = 5
SEND_CONFIRM_TIMEOUT_SECONDS = 12
def log(message: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


class FeishuBot:
    def __init__(self) -> None:
        self.token = None
        self.expire = 0.0

    async def _post_json(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        def _request() -> dict:
            response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

        return await asyncio.to_thread(_request)

    async def get_token(self) -> str | None:
        if self.token and time.time() < self.expire:
            return self.token

        try:
            response = await self._post_json(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            )
        except requests.RequestException as exc:
            log(f"feishu_token_failed: {exc}")
            return None
        except ValueError as exc:
            log(f"feishu_token_json_failed: {exc}")
            return None

        token = response.get("tenant_access_token")
        if not token:
            log(f"feishu_token_missing: {response}")
            return None

        self.token = token
        self.expire = time.time() + 7000
        return token

    async def _send_card(self, card: dict) -> bool:
        token = await self.get_token()
        if not token:
            return False

        try:
            await self._post_json(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                {
                    "receive_id": FEISHU_USER_ID,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            return True
        except requests.RequestException as exc:
            log(f"feishu_send_failed: {exc}")
            return False
        except ValueError as exc:
            log(f"feishu_send_json_failed: {exc}")
            return False

    async def send_text(self, title: str, content: str, color: str = "blue") -> bool:
        card = {
            "header": {"title": {"tag": "plain_text", "content": title}, "template": color},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
        }
        return await self._send_card(card)

    async def send_login_card(self, qr_url: str, attempt: int) -> bool:
        encoded_url = urllib.parse.quote(qr_url)
        deep_link = f"snssdk1128://webview?url={encoded_url}"
        card = {
            "header": {
                "title": {"tag": "plain_text", "content": f"抖音授权 ({attempt}/5)"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "登录状态失效，请在 60 秒内完成确认。",
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "立即进入抖音确认"},
                            "url": deep_link,
                            "type": "primary",
                        }
                    ],
                },
            ],
        }
        return await self._send_card(card)

    async def send_timeout_card(self) -> bool:
        actions = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "重新获取二维码"},
                "type": "default",
                "url": CF_TRIGGER_URL,
            }
        ]
        if GITHUB_ACTIONS_URL:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "备用入口 (GitHub)"},
                    "type": "default",
                    "url": GITHUB_ACTIONS_URL,
                }
            )

        card = {
            "header": {
                "title": {"tag": "plain_text", "content": "任务已暂停"},
                "template": "grey",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "两次授权都已超时。准备好手机后，可点击下方按钮重新触发任务。",
                    },
                },
                {"tag": "action", "actions": actions},
            ],
        }
        return await self._send_card(card)


class DouyinEngine:
    def __init__(self) -> None:
        self.bot = FeishuBot()
        self.final_report: dict[str, str] = {}

    async def wait_until(
        self,
        predicate,
        timeout_seconds: float,
        description: str,
        poll_interval: float = SHORT_POLL_SECONDS,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_error = None

        while time.monotonic() < deadline:
            try:
                if await predicate():
                    return
            except PlaywrightError as exc:
                last_error = exc
            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"wait_timeout: {description}") from last_error

    async def is_visible(self, locator) -> bool:
        try:
            return await locator.is_visible()
        except PlaywrightError:
            return False

    def decode_qr(self, b64_data: str) -> str | None:
        try:
            if "base64," in b64_data:
                b64_data = b64_data.split("base64,", 1)[1]
            data = base64.b64decode(b64_data)
            nparr = np.frombuffer(data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            qr_url, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
            return qr_url if qr_url and "v.douyin.com" in qr_url else None
        except (ValueError, binascii.Error, cv2.error) as exc:
            log(f"qr_decode_failed: {exc}")
            return None

    async def wait_for_initial_page_state(self, page, timeout_seconds: float = 35) -> None:
        async def _page_ready() -> bool:
            if await self.is_visible(page.locator(CHAT_LIST_SELECTOR).first):
                return True
            if await self.is_visible(page.locator(SEARCH_INPUT_SELECTOR).first):
                return True
            if await self.is_visible(page.locator(MFA_SELECTOR).first):
                return True
            return await page.locator("img[src*='base64']").count() > 0

        await self.wait_until(_page_ready, timeout_seconds, "chat_or_qr_ready")

    async def is_verification_page(self, page) -> bool:
        try:
            title = await page.title()
            if "验证码中间页" in title:
                return True
        except PlaywrightError:
            return False

        try:
            body = await page.locator("body").inner_text()
        except PlaywrightError:
            return False
        return "验证码中间页" in body

    async def get_qr_link(self, page) -> str | None:
        deadline = time.monotonic() + QR_FETCH_TIMEOUT_SECONDS

        while time.monotonic() < deadline:
            try:
                images = await page.locator("img[src*='base64']").all()
                for image in images:
                    src = await image.get_attribute("src")
                    if not src:
                        continue
                    qr_url = self.decode_qr(src)
                    if qr_url:
                        return qr_url
            except PlaywrightError as exc:
                log(f"qr_read_failed: {exc}")
            await asyncio.sleep(SHORT_POLL_SECONDS)

        log("qr_not_found")
        return None

    async def has_login_cookies(self, context) -> bool:
        try:
            cookies = await context.cookies("https://www.douyin.com")
        except PlaywrightError as exc:
            log(f"cookie_read_failed: {exc}")
            return False

        cookie_map = {cookie.get("name"): cookie.get("value") for cookie in cookies}
        required_keys = ("sessionid", "sessionid_ss", "sid_tt", "uid_tt")
        return any(cookie_map.get(key) for key in required_keys)

    async def is_qr_still_visible(self, page) -> bool:
        try:
            return await page.locator("img[src*='base64']").count() > 0
        except PlaywrightError:
            return False

    async def get_login_signal(self, page, context) -> str | None:
        if await self.is_visible(page.locator(CHAT_LIST_SELECTOR).first):
            return "chat_list"
        if await self.is_visible(page.locator(SEARCH_INPUT_SELECTOR).first):
            return "search_input"
        if await self.has_login_cookies(context) and not await self.is_qr_still_visible(page):
            return "cookie_without_qr"
        return None

    async def handle_mfa(self, page) -> bool:
        log("mfa_detected")
        try:
            password_option = page.get_by_text(RE_VERIFY_PWD_OPT).first
            if await self.is_visible(password_option):
                await password_option.click(force=True)

            password_input = page.locator('input[type="password"]').first
            await password_input.wait_for(state="visible", timeout=DEFAULT_PAGE_TIMEOUT_MS)
            await password_input.fill(DOUYIN_PASSWORD)

            submit_button = page.locator(SUBMIT_BTN_CSS).filter(
                has_text=re.compile(r"验证|确定|Verify|Confirm")
            )
            if await submit_button.count() > 0:
                await submit_button.first.click(force=True)
            else:
                await page.keyboard.press("Enter")

            await self.wait_for_initial_page_state(page, timeout_seconds=20)
            return True
        except (PlaywrightTimeout, PlaywrightError) as exc:
            log(f"mfa_failed: {exc}")
            return False

    async def safe_reset_chat_page(self, page, reason: str) -> bool:
        for attempt in range(1, 4):
            try:
                log(f"chat_reset_start: {reason} attempt={attempt}")
                await page.goto(CHAT_URL, wait_until="commit", timeout=25_000)
                await asyncio.sleep(2.0)
                if await self.is_verification_page(page):
                    log(f"verification_page_detected: {reason} attempt={attempt}")
                    await asyncio.sleep(4.0)
                    continue
                await self.wait_for_initial_page_state(page)
                return True
            except (TimeoutError, PlaywrightTimeout, PlaywrightError) as exc:
                log(f"chat_reset_failed: {reason} attempt={attempt} error={exc}")
                await asyncio.sleep(1.5)
        return False

    async def wait_for_login_or_mfa(self, page, context, wait_seconds: float) -> bool:
        deadline = time.monotonic() + wait_seconds
        next_refresh_at = time.monotonic() + LOGIN_REFRESH_SECONDS

        while time.monotonic() < deadline:
            login_signal = await self.get_login_signal(page, context)
            if login_signal:
                log(f"login_signal={login_signal}")
                return True

            mfa_visible = await self.is_visible(page.locator(MFA_SELECTOR).first)
            password_option_visible = await self.is_visible(page.get_by_text(RE_VERIFY_PWD_OPT).first)
            if mfa_visible or password_option_visible:
                if await self.handle_mfa(page):
                    return True

            if time.monotonic() >= next_refresh_at and await self.has_login_cookies(context):
                await self.safe_reset_chat_page(page, "login_cookie_refresh")
                login_signal = await self.get_login_signal(page, context)
                if login_signal:
                    log(f"login_signal={login_signal}")
                    return True
                next_refresh_at = time.monotonic() + LOGIN_REFRESH_SECONDS

            await asyncio.sleep(SHORT_POLL_SECONDS)

        return False

    async def wait_for_header_match(self, page, name: str, timeout_seconds: float = 3) -> None:
        header = page.locator(HEADER_TITLE_SELECTOR).first

        async def _header_matches() -> bool:
            if not await self.is_visible(header):
                return False
            title = re.sub(r"\s+", " ", await header.inner_text()).strip()
            return name in title

        await self.wait_until(_header_matches, timeout_seconds, f"header_match_{name}")

    async def wait_for_captcha_to_clear(self, page, timeout_seconds: float = 3.5) -> bool:
        captcha = page.locator(CAPTCHA_CONTAINER_SELECTOR).first
        if not await self.is_visible(captcha):
            return True

        async def _captcha_gone() -> bool:
            return not await self.is_visible(captcha)

        try:
            await self.wait_until(_captcha_gone, timeout_seconds, "captcha_clear")
            return True
        except TimeoutError:
            return False

    async def wait_for_conversation_items(self, page, timeout_seconds: float = 12) -> bool:
        chat_list = page.locator(CHAT_LIST_SELECTOR).first

        async def _items_ready() -> bool:
            if not await self.is_visible(chat_list):
                return False
            try:
                items = chat_list.locator(CONVERSATION_ITEM_SELECTOR)
                count = await items.count()
                if count == 0:
                    return False
                sample_count = min(count, 3)
                for index in range(sample_count):
                    text = re.sub(r"\s+", " ", await items.nth(index).inner_text()).strip()
                    if text:
                        return True
                return False
            except PlaywrightError:
                return False

        try:
            await self.wait_until(_items_ready, timeout_seconds, "conversation_items_ready")
            return True
        except TimeoutError:
            return False

    async def reset_left_list_to_top(self, chat_list) -> None:
        try:
            await chat_list.evaluate(
                """
                (node) => {
                  const candidates = [node, ...node.querySelectorAll('*')];
                  const scrollable = candidates.find(
                    (el) => el.scrollHeight > el.clientHeight + 20
                  ) || node;
                  scrollable.scrollTop = 0;
                }
                """
            )
        except PlaywrightError:
            return

    async def scroll_left_list_once(self, chat_list) -> bool:
        try:
            return await chat_list.evaluate(
                """
                (node) => {
                  const candidates = [node, ...node.querySelectorAll('*')];
                  const scrollable = candidates.find(
                    (el) => el.scrollHeight > el.clientHeight + 20
                  ) || node;
                  const previousTop = scrollable.scrollTop;
                  const delta = Math.max(240, Math.floor(scrollable.clientHeight * 0.8));
                  scrollable.scrollTop = Math.min(
                    previousTop + delta,
                    scrollable.scrollHeight
                  );
                  return scrollable.scrollTop > previousTop;
                }
                """
            )
        except PlaywrightError:
            return False

    async def open_conversation_from_left_list(self, page, name: str) -> tuple[bool, bool]:
        chat_list = page.locator(CHAT_LIST_SELECTOR).first
        if not await self.wait_for_conversation_items(page):
            return False, False

        found_in_left_list = False
        await self.reset_left_list_to_top(chat_list)
        await asyncio.sleep(0.3)

        for _ in range(6):
            items = chat_list.locator(CONVERSATION_ITEM_SELECTOR)
            count = await items.count()

            for index in range(count):
                item = items.nth(index)
                try:
                    item_text = re.sub(r"\s+", " ", await item.inner_text()).strip()
                except PlaywrightError:
                    continue

                if name not in item_text:
                    continue

                found_in_left_list = True
                for force_click in (False, True):
                    try:
                        await item.scroll_into_view_if_needed()
                        await item.click(timeout=1_500, force=force_click)
                        await self.wait_for_header_match(page, name)
                        log(f"{name} open=left_list")
                        return True, True
                    except (TimeoutError, PlaywrightTimeout, PlaywrightError):
                        continue

            if not await self.scroll_left_list_once(chat_list):
                break
            await asyncio.sleep(0.35)

        return False, found_in_left_list

    async def open_conversation_via_search(self, page, name: str) -> bool:
        search_input = page.locator(SEARCH_INPUT_SELECTOR).first
        await search_input.wait_for(state="visible", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        try:
            await search_input.focus()
        except PlaywrightError:
            await search_input.evaluate("(node) => node.focus()")
        await search_input.press("Control+A")
        await search_input.press("Delete")
        await search_input.fill(name)

        result_group = page.locator(SEARCH_RESULT_GROUP_SELECTOR).filter(
            has_text=re.compile(re.escape(name))
        ).first
        await result_group.wait_for(state="visible", timeout=4_000)

        chat_button = result_group.locator(SEARCH_CHAT_BUTTON_SELECTOR).first
        try:
            if await chat_button.count() > 0 and await self.is_visible(chat_button):
                await chat_button.click(timeout=4_000)
            else:
                await result_group.click(timeout=4_000)
        except PlaywrightError as exc:
            error_message = str(exc)
            if "intercepts pointer events" in error_message or "captcha" in error_message.lower():
                raise PlaywrightError("search_click_blocked") from exc
            raise

        await self.wait_for_header_match(page, name)
        log(f"{name} open=search")
        return True

    async def get_message_editor(self, page):
        editor = page.locator(MESSAGE_EDITOR_SELECTOR).first
        if await editor.count() == 0:
            editor = page.locator(".editor-kit-container").first
        await editor.wait_for(state="visible", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        return editor

    async def get_streak_value(self, page) -> str:
        streak_node = page.locator(f"{HEADER_INFO_SELECTOR} {STREAK_VALUE_SELECTOR}").first
        if not await self.is_visible(streak_node):
            return "N/A"
        raw_text = await streak_node.inner_text()
        return "".join(re.findall(r"\d+", raw_text)) or "N/A"

    async def confirm_message_sent(self, page, unique_line: str, timeout_seconds: float) -> bool:
        async def _message_visible_in_chat() -> bool:
            try:
                probe = page.locator(f"text={unique_line}").last
                if not await probe.is_visible():
                    return False
                bounding_box = await probe.bounding_box()
                if not bounding_box or bounding_box["x"] < 400:
                    return False
                return True
            except PlaywrightError:
                return False

        try:
            await self.wait_until(_message_visible_in_chat, timeout_seconds, f"message_confirm_{unique_line}")
            return True
        except TimeoutError:
            log(f"confirm_failed: {unique_line} not found on right side within {timeout_seconds}s")
            return False

    async def _send_msg_single_attempt_impl(self, page, name: str) -> tuple[bool, str]:
        log(f"{name} step=open_start")
        opened, found_in_left_list = await self.open_conversation_from_left_list(page, name)
        if not opened:
            if await self.safe_reset_chat_page(page, f"open_retry_{name}"):
                log(f"{name} step=open_retry_after_reset")
                opened, found_in_left_list = await self.open_conversation_from_left_list(page, name)

        if not opened:
            if ENABLE_SEARCH_FALLBACK:
                log(f"{name} step=search_fallback")
                await self.open_conversation_via_search(page, name)
                opened = True
            else:
                return False, "left_list_open_failed"

        if not opened:
            return False, "left_list_open_failed"

        fire = await self.get_streak_value(page)
        
        # 调用外置文件生成高级感消息和校验时间戳
        message_lines, time_line = generate_message(name, fire)

        log(f"{name} step=editor_ready")
        captcha_cleared = await self.wait_for_captcha_to_clear(page)
        if not captcha_cleared:
            log(f"{name} captcha_still_visible_before_editor")
        editor = await self.get_message_editor(page)
        try:
            await editor.focus()
        except PlaywrightError:
            await editor.evaluate("(node) => node.focus()")
        try:
            await editor.press("Control+A")
            await editor.press("Delete")
        except PlaywrightError:
            pass

        for index, line in enumerate(message_lines):
            await page.keyboard.type(line)
            if index < len(message_lines) - 1:
                await page.keyboard.press("Shift+Enter")

        log(f"{name} step=submit")
        await page.keyboard.press("Enter")
        await asyncio.sleep(1.0) # 稍微增加一点提交后的基础等待时间

        # 唯一信任 confirm_message_sent (探测聊天列表中是否存在带有唯一时间戳的消息)
        # 不再使用 message_editor_is_cleared 作为备选，因为它在某些 UI 卡顿时会产生误判(编辑器虽然清空但消息其实没发出去)
        if await self.confirm_message_sent(page, time_line, SEND_CONFIRM_TIMEOUT_SECONDS):
            await self.wait_for_conversation_items(page, timeout_seconds=8)
            return True, fire

        return False, "message_not_confirmed"

    async def send_msg_single_attempt(self, page, name: str) -> tuple[bool, str]:
        try:
            return await self._send_msg_single_attempt_impl(page, name)
        except (TimeoutError, PlaywrightTimeout) as exc:
            log(f"{name} attempt_step_timeout: {exc}")
            return False, str(exc)
        except PlaywrightError as exc:
            error_message = str(exc)
            if "search_click_blocked" in error_message:
                log(f"{name} search_blocked")
                return False, "search_click_blocked"
            log(f"{name} attempt_failed: {exc}")
            return False, error_message

    async def load_cookies(self, context) -> None:
        if not os.path.exists(COOKIE_FILE):
            log(f"cookie_file_not_found: {COOKIE_FILE}")
            return

        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as file:
                cookies = json.load(file)
            
            normalized_cookies = []
            session_id_found = False
            for cookie in cookies:
                name = cookie.get("name")
                domain = cookie.get("domain")
                if not name or not domain:
                    continue
                
                normalized = {
                    "name": name,
                    "value": str(cookie.get("value", "")),
                    "domain": domain,
                    "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", False),
                    "httpOnly": cookie.get("httpOnly", False),
                    "sameSite": cookie.get("sameSite", "Lax")
                }
                
                expires = cookie.get("expires")
                if isinstance(expires, (int, float)) and expires > 0:
                    normalized["expires"] = expires
                
                if name in ("sessionid", "sessionid_ss"):
                    session_id_found = True
                
                normalized_cookies.append(normalized)

            if normalized_cookies:
                await context.add_cookies(normalized_cookies)
                log(f"cookies_injected count={len(normalized_cookies)} sessionid={session_id_found}")
        except (OSError, json.JSONDecodeError, PlaywrightError) as exc:
            log(f"cookie_load_failed: {exc}")

    async def save_cookies(self, context) -> None:
        try:
            cookies = await context.cookies()
            with open(COOKIE_FILE, "w", encoding="utf-8") as file:
                json.dump(cookies, file, ensure_ascii=False, indent=4)
        except OSError as exc:
            log(f"cookie_write_failed: {exc}")
        except PlaywrightError as exc:
            log(f"cookie_save_failed: {exc}")

    async def run(self) -> None:
        browser = None

        try:
            async with async_playwright() as playwright:
                log("engine_start")
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
                )
                context = await browser.new_context(
                    viewport={"width": 1536, "height": 864},
                    user_agent=DESKTOP_USER_AGENT,
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                )
                await context.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = window.chrome || { runtime: {} };
                    Object.defineProperty(navigator, 'languages', {
                      get: () => ['zh-CN', 'zh', 'en-US', 'en']
                    });
                    Object.defineProperty(navigator, 'plugins', {
                      get: () => [1, 2, 3, 4, 5]
                    });
                    """
                )
                page = await context.new_page()
                page.set_default_timeout(DEFAULT_PAGE_TIMEOUT_MS)

                # 在加载 Cookie 前先访问一下域名，帮助浏览器建立上下文，有时能解决 add_cookies 不生效的问题
                try:
                    await page.goto("https://www.douyin.com/", wait_until="commit", timeout=10_000)
                except:
                    pass

                await self.load_cookies(context)
                if not await self.safe_reset_chat_page(page, "startup"):
                    raise RuntimeError("startup_chat_open_failed")

                # 增加对 Cookie 登录状态的最终判定等待，避免页面刚加载完时 Chat List 还没渲染出来
                login_signal = await self.get_login_signal(page, context)
                if not login_signal:
                    log("waiting_for_login_settle")
                    for _ in range(6):
                        await asyncio.sleep(1.0)
                        login_signal = await self.get_login_signal(page, context)
                        if login_signal:
                            log(f"login_settled signal={login_signal}")
                            break

                if not login_signal:
                    log("login_required")
                    login_ok = False

                    for attempt in range(1, 6):
                        qr_url = await self.get_qr_link(page)
                        if not qr_url:
                            log("qr_missing_retry")
                            await self.safe_reset_chat_page(page, "qr_retry")
                            continue

                        await self.bot.send_login_card(qr_url, attempt)
                        log(f"login_card_sent attempt={attempt}")
                        if await self.wait_for_login_or_mfa(page, context, LOGIN_WAIT_SECONDS):
                            login_ok = True
                            break

                    if login_ok:
                        log("login_ok_save_cookie")
                        await self.save_cookies(context)
                        await self.bot.send_text("登录成功", "最新有效 Cookie 已同步保存。", "green")
                    else:
                        log("login_timeout_send_retry_card")
                        await self.bot.send_timeout_card()
                        return

                log("[Pass 1] start")
                failed_queue: list[str] = []

                for index, name in enumerate(FRIENDS):
                    if index > 0 and RESET_BETWEEN_CONTACTS:
                        await self.safe_reset_chat_page(page, f"between_contacts_{name}")

                    success = False
                    fire_value = "N/A"

                    for attempt in range(1, SEND_RETRY_COUNT + 1):
                        ok, result = await self.send_msg_single_attempt(page, name)
                        if ok:
                            log(f"{name} send_ok fire={result}")
                            success = True
                            fire_value = result
                            break

                        log(f"{name} send_fail attempt={attempt} reason={result}")
                        if result in {"left_list_open_failed", "search_click_blocked", "attempt_timeout"}:
                            break

                    if success:
                        self.final_report[name] = f"SUCCESS ({fire_value}d)"
                    else:
                        failed_queue.append(name)
                        self.final_report[name] = "FAILED"

                if failed_queue:
                    log(f"[Pass 2] targets={failed_queue}")
                    if await self.safe_reset_chat_page(page, "pass2"):
                        for index, name in enumerate(failed_queue):
                            if index > 0 and RESET_BETWEEN_CONTACTS:
                                await self.safe_reset_chat_page(page, f"pass2_between_contacts_{name}")

                            ok, result = await self.send_msg_single_attempt(page, name)
                            if ok:
                                log(f"{name} rescue_ok fire={result}")
                                self.final_report[name] = f"SUCCESS ({result}d)"
                            else:
                                log(f"{name} rescue_fail reason={result}")

                report_lines = []
                success_count = 0
                for name in FRIENDS:
                    status = self.final_report.get(name, "FAILED")
                    if "SUCCESS" in status:
                        success_count += 1
                    report_lines.append(f"- {name}: {status}")

                finished_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await self.bot.send_text(
                    "今日巡检任务总报告",
                    (
                        f"完成时间: {finished_at}\n"
                        f"成功率: {success_count}/{len(FRIENDS)}\n\n"
                        + "\n".join(report_lines)
                        + "\n---\n自动化引擎运行结束"
                    ),
                    "green" if success_count == len(FRIENDS) else "orange",
                )
                log(f"engine_done success={success_count}/{len(FRIENDS)}")

                log("save_cookie_before_exit")
                await self.save_cookies(context)
        finally:
            if browser is not None:
                await browser.close()


if __name__ == "__main__":
    asyncio.run(DouyinEngine().run())

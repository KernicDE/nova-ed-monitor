from __future__ import annotations

import logging
import queue
import re
import threading
import time

import httpx

from . import events
from .config import Config
from .state import AppState, EventCategory, LogEvent

_log = logging.getLogger("nova.youtube")

_LIVE_CHAT_URL = "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat"
_CLIENT_CONTEXT = {
    "context": {
        "client": {
            "clientName": "WEB",
            "clientVersion": "2.20260301.00.00",
        }
    }
}


def _accept_consent_if_needed(resp: httpx.Response, client: httpx.Client) -> None:
    """If redirected to YouTube's GDPR consent page, POST acceptance to get session cookie."""
    if "consent.youtube.com" not in str(resp.url):
        return
    try:
        fields = {}
        for name in ("gl", "m", "pc", "continue", "x", "bl", "hl"):
            m = re.search(rf'name="{name}" value="([^"]*)"', resp.text)
            if m:
                fields[name] = m.group(1)
        fields["set_eom"] = "true"
        client.post("https://consent.youtube.com/save", data=fields,
                    follow_redirects=True, timeout=15)
    except Exception:
        pass


def _get_live_video_id(channel: str, client: httpx.Client) -> str | None:
    """Fetch the channel's /live page and extract the video ID if live."""
    handle = channel.lstrip("@")
    url = f"https://www.youtube.com/@{handle}/live"
    try:
        resp = client.get(url, follow_redirects=True, timeout=15)
        _accept_consent_if_needed(resp, client)
        # Re-fetch if we just accepted consent
        if "consent.youtube.com" in str(resp.url):
            resp = client.get(url, follow_redirects=True, timeout=15)
        # Check final URL (redirect case)
        m = re.search(r"watch\?v=([\w-]{11})", str(resp.url))
        if m:
            return m.group(1)
        # YouTube often serves HTML instead of redirecting — scan the body
        m = re.search(r'<link rel="canonical"[^>]*href="[^"]*watch\?v=([\w-]{11})"', resp.text)
        if m:
            return m.group(1)
        m = re.search(r'"videoId"\s*:\s*"([\w-]{11})"', resp.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _get_continuation(video_id: str, client: httpx.Client) -> str | None:
    """Fetch the live chat page and extract the initial continuation token."""
    url = f"https://www.youtube.com/live_chat?v={video_id}&is_popout=1"
    try:
        resp = client.get(url, timeout=15)
        m = re.search(r'"continuation"\s*:\s*"([^"]+)"', resp.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _poll_chat(
    continuation: str, client: httpx.Client
) -> tuple[list[tuple[str, str]], str | None, int]:
    """Poll one batch of live chat messages.

    Returns (messages, next_continuation, timeout_ms).
    messages is a list of (author, text) tuples.
    """
    body = {**_CLIENT_CONTEXT, "continuation": continuation}
    try:
        resp = client.post(_LIVE_CHAT_URL, json=body, timeout=15)
        data = resp.json()
    except Exception:
        return [], None, 5000

    try:
        cont_data = data["continuationContents"]["liveChatContinuation"]
    except (KeyError, TypeError):
        return [], None, 5000

    messages: list[tuple[str, str]] = []
    for action in cont_data.get("actions", []):
        try:
            renderer = action["addChatItemAction"]["item"]["liveChatTextMessageRenderer"]
            author = renderer["authorName"]["simpleText"]
            text = "".join(run.get("text", "") for run in renderer["message"]["runs"])
            if author and text:
                messages.append((author, text))
        except (KeyError, TypeError):
            continue

    next_cont: str | None = None
    timeout_ms = 5000
    try:
        cont_obj = cont_data["continuations"][0]
        timed = cont_obj.get("timedContinuationData") or cont_obj.get(
            "invalidationContinuationData"
        )
        if timed:
            next_cont = timed.get("continuation")
            timeout_ms = int(timed.get("timeoutMs", 5000))
    except (KeyError, TypeError, IndexError):
        pass

    return messages, next_cont, timeout_ms


def monitor(
    state: AppState, lock: threading.RLock, tts_q: queue.Queue, cfg: Config
) -> None:
    """Monitor a YouTube live chat anonymously.
    Does nothing if youtube_channel is not set in config.
    """
    if not cfg.youtube_channel:
        return

    channel = cfg.youtube_channel

    while True:
        try:
            with httpx.Client(
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                }
            ) as client:
                # Find the live stream
                video_id = _get_live_video_id(channel, client)
                if not video_id:
                    _log.debug(f"YouTube: no live stream for @{channel}")
                    time.sleep(60)
                    continue

                _log.info(f"YouTube: live stream found, video_id={video_id}")
                continuation = _get_continuation(video_id, client)
                if not continuation:
                    _log.debug("YouTube: could not get chat continuation token")
                    time.sleep(60)
                    continue

                # Poll chat until continuation runs out or error
                while continuation:
                    msgs, next_cont, timeout_ms = _poll_chat(continuation, client)

                    for author, text in msgs:
                        log_msg = f"[YouTube] {author}: {text}"
                        with lock:
                            state.push_event(LogEvent.new(EventCategory.Chat, log_msg))
                            muted = state.chat_tts_muted or state.youtube_tts_muted

                        if not muted:
                            events._speak_chat(tts_q, author.lstrip("@"), text, source="YouTube")

                    continuation = next_cont
                    time.sleep(timeout_ms / 1000)

        except Exception as exc:
            _log.warning(f"YouTube monitor error (will retry): {exc}")
        time.sleep(5)

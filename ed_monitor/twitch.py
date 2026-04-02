from __future__ import annotations

import logging
import queue
import socket
import threading
import time

from . import events
from .config import Config
from .state import AppState, EventCategory, LogEvent

_log = logging.getLogger("nova.twitch")

SERVER = "irc.chat.twitch.tv"
PORT   = 6667


def monitor(state: AppState, lock: threading.RLock, tts_q: queue.Queue, cfg: Config) -> None:
    """Connects to Twitch IRC anonymously and listens for chat messages.
    Does nothing if twitch_channel is not set in config.
    """
    if not cfg.twitch_channel:
        return

    channel = cfg.twitch_channel.lstrip("#")
    irc_channel = f"#{channel}"
    nickname = "justinfan87234"  # Anonymous read-only login

    while True:
        try:
            sock = socket.socket()
            sock.settimeout(120.0)
            _log.info(f"Connecting to Twitch IRC: {irc_channel}")
            sock.connect((SERVER, PORT))

            sock.send(b"PASS SCHMOOPIIE\r\n")
            sock.send(f"NICK {nickname}\r\n".encode("utf-8"))
            sock.send(f"JOIN {irc_channel}\r\n".encode("utf-8"))
            _log.info(f"Twitch IRC connected: {irc_channel}")

            buf = ""
            while True:
                data = sock.recv(2048).decode("utf-8", errors="replace")
                if not data:
                    break

                buf += data
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")

                    if line.startswith("PING"):
                        sock.send(b"PONG :tmi.twitch.tv\r\n")
                        continue

                    if "PRIVMSG" in line:
                        # Format: :user!user@user.tmi.twitch.tv PRIVMSG #channel :message
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            user = parts[1].split("!", 1)[0]
                            msg  = parts[2].strip()

                            log_msg = f"[Twitch] {user}: {msg}"
                            with lock:
                                state.push_event(LogEvent.new(EventCategory.Chat, log_msg))

                            events._speak_chat(tts_q, user, msg, source="Twitch")

        except Exception as exc:
            _log.warning(f"Twitch IRC error (will reconnect): {exc}")
        finally:
            try:
                sock.close()
            except Exception:
                pass
        time.sleep(5)

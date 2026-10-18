"""
Interactive Telegram Setup & Verification Script for TR-AI.
1. Tests the Bot Token with Telegram API (getMe).
2. If Chat ID is missing, checks getUpdates for incoming user message to detect Chat ID automatically.
3. Saves TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env.
4. Sends a test confirmation message to the user's Telegram.
"""

import os
import sys
import httpx
from dotenv import load_dotenv

DOTENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(DOTENV_PATH)


def update_env_file(token: str, chat_id: str):
    """Updates TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env without overwriting other variables."""
    if not os.path.exists(DOTENV_PATH):
        lines = []
    else:
        with open(DOTENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated = False
    new_lines = []
    has_token = False
    has_chat_id = False

    for line in lines:
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            new_lines.append(f'TELEGRAM_BOT_TOKEN="{token}"\n')
            has_token = True
        elif line.startswith("TELEGRAM_CHAT_ID="):
            new_lines.append(f'TELEGRAM_CHAT_ID="{chat_id}"\n')
            has_chat_id = True
        else:
            new_lines.append(line)

    if not has_token:
        new_lines.append(f'TELEGRAM_BOT_TOKEN="{token}"\n')
    if not has_chat_id:
        new_lines.append(f'TELEGRAM_CHAT_ID="{chat_id}"\n')

    with open(DOTENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def setup_telegram(token: str = None, chat_id: str = None):
    token = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip().strip('"').strip("'")
    chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip().strip('"').strip("'")

    if not token:
        print("❌ Nessun Token fornito. Inserisci il token da @BotFather.")
        return False

    print(f"Verifica token in corso con l'API Telegram...")
    # 1. Test getMe
    try:
        res = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10.0)
        if res.status_code != 200:
            print(f"❌ Errore Token: Risposta API {res.status_code}: {res.text}")
            return False
        bot_info = res.json().get("result", {})
        bot_name = bot_info.get("first_name", "")
        bot_user = bot_info.get("username", "")
        print(f"✅ Bot verificato con successo: {bot_name} (@{bot_user})")
    except Exception as e:
        print(f"❌ Errore di connessione a Telegram: {e}")
        return False

    # 2. Check chat_id
    if not chat_id:
        print("\n🔍 Cercando il tuo Chat ID tra i messaggi ricevuti dal bot...")
        try:
            up_res = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10.0)
            if up_res.status_code == 200:
                updates = up_res.json().get("result", [])
                if updates:
                    latest = updates[-1]
                    sender = latest.get("message", {}).get("from", {})
                    chat_id = str(sender.get("id", ""))
                    user_name = sender.get("first_name", "Utente")
                    print(f"✅ Chat ID rilevato automaticamente: {chat_id} ({user_name})")
                else:
                    print("⚠️ Non ho trovato messaggi recenti.")
                    print("👉 Apri Telegram, cerca il tuo bot (@" + bot_user + "), premi 'Avvia' o scrivigli un messaggio (es. 'ciao'), poi riesegui questo script!")
                    return False
        except Exception as e:
            print(f"❌ Errore nel recupero degli updates: {e}")
            return False

    # 3. Save to .env
    update_env_file(token, chat_id)
    print(f"✅ Credenziali salvate con successo in .env!")

    # 4. Send test message
    test_msg = (
        f"🎉 <b>TR-AI &lt;-&gt; Telegram Collegato con Successo!</b>\n\n"
        f"<b>Bot:</b> @{bot_user}\n"
        f"<b>Chat ID Autorizzato:</b> <code>{chat_id}</code>\n"
        f"<b>Modalità Operativa:</b> PAPER TRADING / DEMO\n"
        f"<b>Dashboard:</b> http://localhost:8000\n\n"
        f"Da adesso riceverai qui tutte le notifiche sui trade e potrai inviare comandi (/status, /positions, /trades, /kill)."
    )
    try:
        send_res = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": test_msg, "parse_mode": "HTML"},
            timeout=10.0
        )
        if send_res.status_code == 200:
            print(f"🚀 Notifica di benvenuto inviata con successo sul tuo Telegram!")
            return True
        else:
            print(f"⚠️ Impossibile inviare la notifica di test: {send_res.text}")
            return False
    except Exception as e:
        print(f"❌ Errore invio notifica: {e}")
        return False


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else None
    c = sys.argv[2] if len(sys.argv) > 2 else None
    setup_telegram(t, c)

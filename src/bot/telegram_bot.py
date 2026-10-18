"""
Telegram Bot Engine for TR-AI.
Provides real-time mobile push notifications and interactive command handling:
- Commands: /start, /status, /positions, /trades, /kill, /resume, /help
- Event Notifications: Signals (approved/rejected), Fills, TP1+BreakEven, Exits, Circuit Breaker
- Security: Multi-tenant safety check (only authorized chat_id), Kill Switch execution
- Resilient Fallback: If TELEGRAM_BOT_TOKEN is unset, operates in Mock Mode with structured logging.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import httpx
from dotenv import load_dotenv

from src.core.events import AccountInfo, Position, Signal, SignalDirection, OrderSide
from src.core.logger import decision_logger

# Load environment variables from .env
load_dotenv()

TELEGRAM_LOGGER = logging.getLogger("TR-AI.Telegram")
TELEGRAM_LOGGER.setLevel(logging.INFO)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramBot:
    """
    Asynchronous Telegram Bot for TR-AI trading system.
    Communicates directly with the Telegram Bot API using httpx.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        live_state: Optional[Dict[str, Any]] = None,
        on_kill_switch: Optional[Callable[[bool, str], None]] = None
    ):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.live_state = live_state
        self.on_kill_switch = on_kill_switch

        self.is_mock = not bool(self.token)
        self._polling_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._last_update_id = 0

        # Memory buffer for mock mode
        self.mock_sent_messages: List[Dict[str, Any]] = []

        if self.is_mock:
            TELEGRAM_LOGGER.info(
                "TelegramBot initialized in MOCK MODE (TELEGRAM_BOT_TOKEN not provided in .env). "
                "Alerts will be logged locally."
            )
        else:
            TELEGRAM_LOGGER.info(f"TelegramBot initialized for authorized chat_id={self.chat_id or 'UNLOCKED'}")

    @property
    def api_url(self) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self.token}"

    # -------------------------------------------------------------
    # Message Dispatcher & Formatting
    # -------------------------------------------------------------

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Sends an HTML/Markdown formatted text message."""
        timestamp = datetime.utcnow().isoformat() + "Z"

        if self.is_mock or not self.chat_id:
            msg_payload = {"timestamp": timestamp, "text": text, "mode": "MOCK"}
            self.mock_sent_messages.append(msg_payload)
            TELEGRAM_LOGGER.info(f"[TELEGRAM MOCK PUSH] {text.replace('<br>', ' ').replace('<b>', '').replace('</b>', '')}")
            return True

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True
                    }
                )
                if res.status_code == 200:
                    return True
                else:
                    TELEGRAM_LOGGER.error(f"Failed to send Telegram message: {res.status_code} - {res.text}")
                    return False
        except Exception as e:
            TELEGRAM_LOGGER.error(f"Telegram send error: {e}")
            return False

    # -------------------------------------------------------------
    # Specialized Push Notifications
    # -------------------------------------------------------------

    async def notify_signal(self, signal: Signal, approved: bool, reason: str, score: float = 0.0) -> bool:
        """Notifies generated trading signals and Risk Manager decision."""
        icon = "🟢" if approved else "🟡"
        status_text = "<b>APPROVATO DAL RISK MANAGER</b>" if approved else f"<b>RESPINTO DAL RISK MANAGER</b>\n<i>Motivo: {reason}</i>"
        dir_icon = "📈 BUY / LONG" if signal.direction == SignalDirection.LONG else "📉 SELL / SHORT"

        msg = (
            f"{icon} <b>TR-AI — SEGNALE STRATEGIA WAM-FVG</b>\n\n"
            f"<b>Strumento:</b> #{signal.symbol}\n"
            f"<b>Direzione:</b> {dir_icon}\n"
            f"<b>Punteggio Qualità:</b> {score:.1f}/100\n"
            f"<b>Prezzo Entry (Limit):</b> {signal.entry_price:.2f}\n"
            f"<b>Stop Loss:</b> {signal.stop_loss:.2f}\n"
            f"<b>Take Profit 1 (50%):</b> {signal.take_profit_1:.2f}\n"
            f"<b>Take Profit 2 (Runner):</b> {signal.take_profit_2 or 'N/A'}\n"
            f"<b>Rapporto R:R:</b> {signal.risk_reward_ratio:.2f}\n\n"
            f"🛡️ <b>Esito:</b> {status_text}\n"
            f"🕒 <i>{signal.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
        )
        return await self.send_message(msg)

    async def notify_trade_opened(self, position: Position) -> bool:
        """Notifies successful limit order fill and position entry."""
        side_icon = "🟢 LONG" if position.side == OrderSide.BUY else "🔴 SHORT"
        msg = (
            f"🚀 <b>TR-AI — OPERAZIONE APERTA (PAPER DEMO)</b>\n\n"
            f"<b>ID:</b> <code>{position.id}</code>\n"
            f"<b>Strumento:</b> #{position.symbol} ({side_icon})\n"
            f"<b>Size Contratti:</b> {position.size_contracts:.2f}\n"
            f"<b>Prezzo Fill:</b> {position.entry_price:.2f}\n"
            f"<b>Stop Loss Protettivo:</b> {position.stop_loss:.2f}\n"
            f"<b>Target TP1 (50%):</b> {position.take_profit_1:.2f}\n"
            f"<b>Rischio Monetario:</b> € {position.risk_amount_monetary:.2f} (1.0% max)\n\n"
            f"ℹ️ <i>Ordine protetto da Stop Loss obbligatorio non-bypassabile.</i>"
        )
        return await self.send_message(msg)

    async def notify_trade_tp1(self, position: Position, pnl: float, r_mult: float) -> bool:
        """Notifies TP1 target reached, partial profit banking and Break-Even move."""
        msg = (
            f"🎯 <b>TR-AI — TARGET TP1 RAGGIUNTO! (50% CHUSO)</b>\n\n"
            f"<b>Strumento:</b> #{position.symbol}\n"
            f"<b>P&L Parziale Incassato:</b> <b>+€ {pnl:.2f} (+{r_mult:.2f} R)</b>\n"
            f"🛡️ <b>Gestione Rischio Eseguita:</b>\n"
            f"- Chiuso il 50% della size originaria\n"
            f"- <b>Stop Loss spostato a BREAK-EVEN ({position.entry_price:.2f})</b>\n"
            f"- Il restante 50% (Runner) corre verso TP2 a rischio zero.\n"
        )
        return await self.send_message(msg)

    async def notify_trade_closed(self, position: Position, pnl: float, r_mult: float, reason: str) -> bool:
        """Notifies position full closure."""
        pnl_icon = "💰" if pnl >= 0 else "🛑"
        sign = "+" if pnl >= 0 else ""
        msg = (
            f"{pnl_icon} <b>TR-AI — OPERAZIONE COMPLETATA</b>\n\n"
            f"<b>Strumento:</b> #{position.symbol}\n"
            f"<b>Motivo Chiusura:</b> {reason}\n"
            f"<b>P&L Realizzato:</b> <b>{sign}€ {pnl:.2f} ({sign}{r_mult:.2f} R)</b>\n"
            f"<b>Prezzo Uscita:</b> {position.current_price:.2f}\n"
        )
        return await self.send_message(msg)

    async def notify_circuit_breaker(self, dd_pct: float) -> bool:
        """Alerts when daily drawdown threshold is breached."""
        msg = (
            f"🚨 <b>TR-AI — CIRCUIT BREAKER ATTIVATO!</b> 🚨\n\n"
            f"<b>Drawdown Giornaliero:</b> {dd_pct:.2f}% (Limite: 3.00%)\n"
            f"<b>Azione:</b> Nuove operazioni BLOCCATE fino alla sessione di domani.\n"
            f"<i>Il capitale e il rischio sono protetti dal Risk Manager centrale.</i>"
        )
        return await self.send_message(msg)

    async def notify_kill_switch(self, active: bool, source: str = "Telegram") -> bool:
        """Alerts emergency kill-switch state toggle."""
        if active:
            msg = (
                f"🛑 <b>TR-AI — KILL SWITCH ATTIVATO!</b>\n\n"
                f"<b>Sorgente:</b> {source}\n"
                f"<b>Stato:</b> Tutte le attività di trading e invio ordini sono STATE BLOCCATE IMMEDIATAMENTE."
            )
        else:
            msg = (
                f"✅ <b>TR-AI — KILL SWITCH DISATTIVATO</b>\n\n"
                f"<b>Sorgente:</b> {source}\n"
                f"<b>Stato:</b> Ripristinata la normale operatività in Paper Trading."
            )
        return await self.send_message(msg)

    # -------------------------------------------------------------
    # Interactive Command Handlers
    # -------------------------------------------------------------

    async def handle_command(self, command: str, args: List[str], sender_id: str) -> str:
        """Processes interactive bot commands."""
        # Multi-tenant security check
        if self.chat_id and str(sender_id) != str(self.chat_id):
            TELEGRAM_LOGGER.warning(f"Unauthorized command from user {sender_id}: {command}")
            return "⛔ <b>Accesso Negato:</b> Non sei autorizzato ad interagire con questo bot TR-AI."

        cmd = command.lower().strip()

        if cmd in ["/start", "/help"]:
            return (
                "🤖 <b>TR-AI Trading Assistant — Comandi Disponibili</b>\n\n"
                "📊 <b>Monitoraggio:</b>\n"
                "• /status — Riepilogo conto, equity, drawdown e stato sistema\n"
                "• /positions — Dettaglio posizioni aperte e floating PnL\n"
                "• /trades — Ultimi trade storici chiusi e statistiche\n\n"
                "🛡️ <b>Controllo e Sicurezza:</b>\n"
                "• /kill — <b>KILL SWITCH IMMEDIATO:</b> Blocca ogni nuova operazione\n"
                "• /resume — Disattiva il Kill Switch e riprende il Paper Trading\n"
                "• /help — Mostra questo messaggio di aiuto"
            )

        elif cmd == "/status":
            if not self.live_state:
                return "⚠️ Stato di sistema non collegato in memoria."

            acc: AccountInfo = self.live_state.get("account")
            positions: List[Position] = self.live_state.get("open_positions", [])
            floating_pnl = sum(p.unrealized_pnl for p in positions)
            curr_equity = acc.balance + floating_pnl if acc else 1000.0
            bal = acc.balance if acc else 1000.0
            dd = acc.daily_drawdown_pct if acc else 0.0
            ks = self.live_state.get("kill_switch_active", False)

            status_badge = "🛑 HALTED (Kill Switch)" if ks else "🟢 ACTIVE (Paper Trading)"
            return (
                f"📊 <b>TR-AI — STATO DI SISTEMA</b>\n\n"
                f"<b>Stato Operativo:</b> {status_badge}\n"
                f"<b>Modalità:</b> DEMO / SIMULAZIONE MAC\n"
                f"<b>Strategia Attiva:</b> WAM-FVG Intraday\n\n"
                f"💰 <b>Finanze Conto:</b>\n"
                f"• <b>Equity Corrente:</b> € {curr_equity:,.2f}\n"
                f"• <b>Balance Saldo:</b> € {bal:,.2f}\n"
                f"• <b>Floating PnL:</b> € {'+' if floating_pnl >= 0 else ''}{floating_pnl:,.2f}\n"
                f"• <b>Daily Drawdown:</b> {dd:.2f}% (Max: 3.00%)\n"
                f"• <b>Slot Posizioni:</b> {len(positions)} / 3 occupati\n"
            )

        elif cmd == "/positions":
            if not self.live_state:
                return "⚠️ Stato posizioni non disponibile."

            positions = self.live_state.get("open_positions", [])
            if not positions:
                return "ℹ️ <b>Nessuna posizione attualmente aperta.</b>\nRisk budget libero (3/3 slot disponibili)."

            resp = [f"📋 <b>POSIZIONI APERTE ({len(positions)}/3):</b>\n"]
            for p in positions:
                side_badge = "🟢 BUY" if p.side == OrderSide.BUY else "🔴 SELL"
                be_badge = " [BREAK-EVEN]" if p.is_at_breakeven else ""
                sign = "+" if p.unrealized_pnl >= 0 else ""
                resp.append(
                    f"• <b>#{p.symbol}</b> {side_badge} ({p.size_contracts:.2f} contratti){be_badge}\n"
                    f"  Entry: {p.entry_price:.2f} | Prezzo: {p.current_price:.2f}\n"
                    f"  SL: {p.stop_loss:.2f} | TP1: {p.take_profit_1:.2f}\n"
                    f"  Floating PnL: <b>{sign}€ {p.unrealized_pnl:.2f}</b>\n"
                )
            return "\n".join(resp)

        elif cmd == "/trades":
            from src.monitoring.api import get_trade_history
            summary = get_trade_history()
            trades = summary.get("trades", [])
            total = summary.get("total_trades", len(trades))
            wr = summary.get("win_rate_pct", 0.0)
            pf = summary.get("profit_factor", 0.0)
            exp_r = summary.get("expectancy_r", 0.0)

            msg = [
                f"📈 <b>STORICO ESECUZIONI TR-AI</b>\n"
                f"<b>Win Rate:</b> {wr:.1f}% | <b>Profit Factor:</b> {pf:.2f} | <b>Expectancy:</b> {exp_r:+.2f} R\n"
                f"<b>Trade Totali:</b> {total}\n\n"
                f"<b>Ultimi trade registrati:</b>"
            ]
            for t in trades[-5:]:
                s_icon = "💰" if t.get("pnl_monetary", 0) >= 0 else "🛑"
                pnl = t.get("pnl_monetary", 0.0)
                sign = "+" if pnl >= 0 else ""
                msg.append(
                    f"{s_icon} #{t.get('symbol')} {t.get('direction')} | "
                    f"<b>{sign}€ {pnl:.2f} ({sign}{t.get('r_multiple', 0):.2f}R)</b>\n"
                    f"   Exit: {t.get('exit_reason')} @ {t.get('exit_price', 0):.2f}"
                )
            return "\n".join(msg)

        elif cmd == "/kill":
            if self.live_state:
                self.live_state["kill_switch_active"] = True
            if self.on_kill_switch:
                self.on_kill_switch(True, f"Comando Telegram da user {sender_id}")
            decision_logger.log_decision("KILL_SWITCH", "ALL", "ACTIVATED", f"Triggered via Telegram by {sender_id}")
            return (
                "🛑 <b>EMERGENCY KILL SWITCH ATTIVATO!</b>\n\n"
                "Tutte le nuove operazioni sono state <b>BLOCCATE</b>.\n"
                "Usa /resume per riattivare la piattaforma quando opportuno."
            )

        elif cmd == "/resume":
            if self.live_state:
                self.live_state["kill_switch_active"] = False
            if self.on_kill_switch:
                self.on_kill_switch(False, f"Comando Telegram da user {sender_id}")
            decision_logger.log_decision("KILL_SWITCH", "ALL", "DEACTIVATED", f"Resumed via Telegram by {sender_id}")
            return "✅ <b>KILL SWITCH DISATTIVATO:</b> Operatività Paper Trading ripristinata."

        return f"❓ Comando sconosciuto: <code>{command}</code>. Digita /help per la lista dei comandi."

    # -------------------------------------------------------------
    # Async Long-Polling Loop
    # -------------------------------------------------------------

    async def _polling_worker(self) -> None:
        """Background loop for receiving Telegram updates via getUpdates."""
        TELEGRAM_LOGGER.info("Starting Telegram long-polling loop...")
        async with httpx.AsyncClient(timeout=35.0) as client:
            while self._is_running:
                try:
                    res = await client.get(
                        f"{self.api_url}/getUpdates",
                        params={"offset": self._last_update_id + 1, "timeout": 20}
                    )
                    if res.status_code == 200:
                        data = res.json()
                        updates = data.get("result", [])
                        for update in updates:
                            self._last_update_id = max(self._last_update_id, update["update_id"])
                            message = update.get("message", {})
                            text = message.get("text", "").strip()
                            sender_id = str(message.get("from", {}).get("id", ""))

                            if text.startswith("/"):
                                parts = text.split()
                                cmd = parts[0]
                                args = parts[1:]
                                reply = await self.handle_command(cmd, args, sender_id)
                                # Reply to user
                                await client.post(
                                    f"{self.api_url}/sendMessage",
                                    json={"chat_id": sender_id, "text": reply, "parse_mode": "HTML"}
                                )
                    elif res.status_code == 401:
                        TELEGRAM_LOGGER.error("Invalid TELEGRAM_BOT_TOKEN. Check .env configuration.")
                        await asyncio.sleep(10.0)
                    else:
                        await asyncio.sleep(2.0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    TELEGRAM_LOGGER.warning(f"Error in Telegram polling loop: {e}")
                    await asyncio.sleep(3.0)

    def start(self) -> None:
        """Starts Telegram polling if valid token is provided."""
        if self.is_mock:
            TELEGRAM_LOGGER.info("TelegramBot running in MOCK MODE (ready to simulate notifications).")
            return

        if not self._is_running:
            self._is_running = True
            loop = asyncio.get_event_loop()
            self._polling_task = loop.create_task(self._polling_worker())
            TELEGRAM_LOGGER.info("Telegram bot polling task launched.")

    def stop(self) -> None:
        """Stops Telegram polling cleanly."""
        self._is_running = False
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
        TELEGRAM_LOGGER.info("Telegram bot stopped.")

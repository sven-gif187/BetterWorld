# ⚡ Sven's Trading Imperium – 3 Coins Paper Edition

> **Paper-Trading-Bot für BTC/USDC · ETH/USDC · SOL/USDC**  
> Kein echtes Geld. Echte Logik. Volle Power.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-GPL--3.0-green?style=flat-square)
![Mode](https://img.shields.io/badge/Mode-Paper%20Trading-yellow?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)

---

## 🚀 Was ist das?

Ein vollautomatischer **Paper-Trading-Bot** mit professioneller Desktop-Oberfläche.  
Er analysiert BTC, ETH und SOL in Echtzeit und simuliert Käufe & Verkäufe —  
ohne dass echter echter echtes Geld bewegt wird.

Perfekt um Strategien zu testen, zu lernen und gemeinsam zu verbessern.

---

## ✨ Features

| Feature | Beschreibung |
|---|---|
| 📊 **6-Tab-UI** | Cockpit · Strategien · Charts · Schnellhandel · Trade-Viewer · Analyse |
| 🤖 **3 Strategien** | 🐋 Whale · 📈 Swing · ⚡ Scalping |
| 🧠 **Markt-Regime** | TREND↑ / TREND↓ / SEITWÄRTS / VOLATIL – automatisch erkannt |
| 📈 **Indikatoren** | RSI · StochRSI · EMA20/50 · ATR · CVD · VWAP · MACD · ADX |
| 💾 **Absturz-Schutz** | Gewinn, Verlust & Balance überleben Neustarts & Internet-Ausfälle |
| 📱 **Telegram** | Kauf/Verkauf-Benachrichtigungen direkt aufs Handy |
| ♻️ **Paper Reset** | Balance jederzeit zurücksetzen |
| 🔐 **Sicher** | Keine API-Keys nötig – nur Marktdaten (read-only) |

---

## 🖥️ Screenshot

*(Screenshot kommt nach erstem Start)*

---

## ⚙️ Installation

### 1. Repository klonen
```bash
git clone https://github.com/DEIN-USERNAME/svens-imperium.git
cd svens-imperium
```

### 2. Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 3. Konfiguration einrichten
```bash
# .env.example kopieren
cp .env.example .env

# .env öffnen und Werte eintragen
```

Deine `.env` Datei:
```
TELEGRAM_TOKEN=dein_token_von_botfather
TELEGRAM_CHAT_ID=deine_chat_id
```

> **Telegram optional** – ohne Token läuft der Bot, sendet aber keine Nachrichten.

### 4. Bot starten
```bash
python sven_imperium_paper.py
```

---

## 📱 Telegram einrichten (optional)

1. Öffne Telegram → suche **@BotFather**
2. Schreibe `/newbot` → folge den Anweisungen → kopiere den Token
3. Suche **@userinfobot** → schreibe `/start` → kopiere deine Chat-ID
4. Beides in deine `.env` eintragen

---

## 🧰 Weitere Tools in diesem Repo

### 🎙️ [voice2text](voice2text/) – Video & Sprache zu Text

Video oder Online-Link rein, lesbarer Text raus. Mit Uhrzeit im Link wird **nur die
gewünschte Stelle** geladen statt des ganzen Videos.

```bash
pip install -r voice2text/requirements.txt
python -m voice2text                       # Oberfläche
python -m voice2text video.mp4 --start 12:30 --dauer 90
```

Läuft komplett offline (faster-whisper), speichert als `.txt` · `.srt` · `.vtt` · `.md`
und kann Texte auch wieder vorlesen. → [Anleitung](voice2text/README.md)

---

## 🤝 Mitmachen

Beiträge sind herzlich willkommen!

1. **Fork** dieses Repo
2. Erstelle einen **Feature-Branch**: `git checkout -b feature/meine-idee`
3. Commit deine Änderungen: `git commit -m 'Add: meine Idee'`
4. Push den Branch: `git push origin feature/meine-idee`
5. Öffne einen **Pull Request** – ich schaue drüber und merge wenn es passt ✅

### Ideen & Bugs
Einfach ein **Issue** öffnen! Kein Code nötig, nur beschreiben was du dir vorstellst oder was nicht funktioniert.

---

## ⚠️ Haftungsausschluss

Dieser Bot ist ausschließlich für **Paper Trading** (Simulation) gedacht.  
Er bewegt **kein echtes Geld**. Nutzung auf eigene Verantwortung.  
Keine Anlageberatung. Kryptowährungen sind hochspekulativ.

---

## 📄 Lizenz

GPL-3.0 – siehe [LICENSE](LICENSE)  
Jeder darf nutzen, verändern und weitergeben — aber niemand darf es schließen und als eigenes Produkt verkaufen.

---

<div align="center">
  Made with ❤️ by Sven · Stuttgart 🇩🇪
</div>

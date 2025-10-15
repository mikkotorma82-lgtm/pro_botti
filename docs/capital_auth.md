# Capital.com LIVE API — kirjautuminen ilman TOTP:ia (referenssi)

Tämä dokumentoi mallin, jolla kirjaudut Capital LIVE -API:iin ilman TOTP-koodia ja käytät istuntotunnuksia (CST, X-SECURITY-TOKEN) kaikkiin jatkopolkuihin.

## Ydinvirtaus

- POST `{CAPITAL_API_BASE}/api/v1/session`
  - Headers:
    - `X-CAP-API-KEY: <API_KEY>`
    - `Accept: application/json`
    - `Content-Type: application/json`
  - Body:
    ```json
    {"identifier":"<EMAIL>","password":"<API_KEY_PASSWORD>"}
    ```
- Onnistuneessa vastauksessa saat headerit:
  - `CST`
  - `X-SECURITY-TOKEN`
- Lisää nämä headerit kaikkiin jatkokutsuihin (hinnat, toimeksiannot, tilit):
  - `X-CAP-API-KEY`, `CST`, `X-SECURITY-TOKEN` (+ `Accept`, `Content-Type`)

Ei TOTP:ia: jos tilisi/avaimesi on sallittu kirjautumaan ilman 2FA:ta, edellä oleva toimii täysin non‑interactive. Jos backend vaatii TOTP:n, /session palauttaa 401/403 tai geneerisen virheen, eikä non‑interactive login onnistu — pysäytä silloin daemon selkeään virheilmoitukseen.

## Ympäristömuuttujat

```
CAPITAL_API_BASE=https://api-capital.backend-capital.com
CAPITAL_API_KEY=...
CAPITAL_USERNAME=...
CAPITAL_PASSWORD=...   # API key password
CAPITAL_ACCOUNT_TYPE=CFD   # valinnainen
```

EPIC-yliasetukset (valinnainen, symboli → EPIC):
```
CAPITAL_EPIC_US500=US SPX 500
CAPITAL_EPIC_EURUSD=EUR/USD
CAPITAL_EPIC_XAUUSD=GOLD
```

## Istunnon kätkeminen (429:n välttäminen)

Älä kirjaudu sisään jokaisessa pyynnössä. Luo `requests.Session` ja talleta CST/X‑SECURITY‑TOKEN siihen. Uudelleenkäytä istuntoa ja uusi kirjautuminen vasta kun token vanhenee (tyypillisesti ~10 min; käytännössä ~9 min välein).

Toteutus löytyy tiedostosta `tools/capital_session.py`:
- `capital_rest_login(force=False) -> (Session, base_url)`
- `capital_get_bid_ask(symbol)`
- `capital_get_candles(symbol, tf, max_rows)`

## Tyypilliset jatkopolut

- Viimeisin hinta (esimerkki, tarkka malli voi vaihdella tilistä/tuotteesta):
  ```
  GET {BASE}/api/v1/prices/{EPIC}?resolution=MINUTE&max=1
  ```
- Kynttilät (vaihtelee tenantista – tällä referenssillä käytetään `prices`-polkua yksinkertaisuuden vuoksi)
- Toimeksianto (markkina):
  ```
  POST {BASE}/api/v1/positions/otc
  {
    "epic": "<EPIC>",
    "direction": "BUY" | "SELL",
    "size": 0.1,
    "orderType": "MARKET",
    "timeInForce": "FILL_OR_KILL",
    "forceOpen": true,
    "guaranteedStop": false
  }
  ```

## Integrointi

- Lisää `from tools.capital_session import capital_rest_login, capital_get_bid_ask` minne tarvitset (esim. live_daemon).
- Pidä SYMBOL → EPIC -mapping ympäristössä (CAPITAL_EPIC_*) tai käytä suoraan Capitalin nimiä (esim. “US SPX 500”, “EUR/USD”, “GOLD”).

## Virhetilanteet

- 429 too-many.requests: hidasta login-yrityksiä, kätke istunto, vältä peräkkäistä loggausta.
- 400/401/403 loginissa: varmista `X-CAP-API-KEY`, `identifier`, `password` (API key password), sekä ettei TOTP ole pakollinen.

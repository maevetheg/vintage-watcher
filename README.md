# Vintage Watcher

Sends a push notification to your phone when a new listing appears on eBay,
The RealReal, Poshmark, Mercari, Depop or Vestiaire Collective. Tap the
notification to open the listing.

## Setup (about 20 minutes)

1. **Phone alerts:** install the free **ntfy** app, tap +, and subscribe to a
   made-up topic name (e.g. `ad-archive-7391`). Put that name in `config.yaml`.
2. **eBay:** create a free account at developer.ebay.com, create a
   *Production* keyset, and copy the App ID (Client ID) and Cert ID (Client Secret).
3. **Other sites:** on each site, search Ann Demeulemeester, set your size and
   price filters, sort by newest, and paste the URL into `config.yaml`.
4. Set your budget and (optionally) size keywords for eBay in `config.yaml`.

## Run it on your computer (recommended)

```
pip install -r requirements.txt
python -m playwright install chromium
export EBAY_CLIENT_ID="your-client-id"
export EBAY_CLIENT_SECRET="your-client-secret"
python watcher.py --loop 600
```

The first run saves current listings silently; after that you only get alerts
for new ones. Leave the terminal open and the computer awake. A home
connection is also less likely to be blocked than a cloud server.

## Or run it free on GitHub (no computer needed)

1. Create a **public** GitHub repo and upload these files
   (private repos only get 2,000 free minutes/month, not enough for every 10 min).
2. In Settings → Secrets → Actions, add `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`
   and `NTFY_TOPIC` (so your topic stays private).
3. Go to Actions → vintage-watcher → Run workflow to test.

## Good to know

- eBay uses the official API and is solid. The other sites are read from
  their public search pages, which can break when a site redesigns, and
  Depop / Vestiaire sometimes block automated browsers. If a site logs
  "0 listings found", re-check its URL or keep using that app's own alerts.
- Keep their built-in alerts on too (especially The RealReal waitlist);
  they may still fire first.
- Checking every 10 minutes is gentle. Faster checks are more likely to get
  blocked, and automated access may go against some sites' terms.

"""Distributor APIs (official ones only): DigiKey v4, Mouser Search API v1 and
Nexar (Octopart) for everyone else. All results are normalised to one Part
shape so the rest of the program doesn't care where data came from.

Part = {
  source, mpn, mfr, desc, package, datasheet, url, stock, dist_pn, category,
  lifecycle, params: {name: value},
  offers: [{seller, sku, packaging, moq, mult, stock, currency, breaks: [[qty, unit_price], ...], url}]
}
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .net import urlopen
from .config import cache_dir
from .distbom import parse_price

TIMEOUT = 25
CACHE_TTL = 24 * 3600


class ProviderError(Exception):
    pass


class RateLimiter:
    def __init__(self, per_minute):
        self.interval = 60.0 / per_minute
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = self.next - now
            self.next = max(now, self.next) + self.interval
        if delay > 0:
            time.sleep(delay)


def _cache_get(key):
    path = os.path.join(cache_dir(), hashlib.sha1(key.encode()).hexdigest() + ".json")
    try:
        if time.time() - os.path.getmtime(path) < CACHE_TTL:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    except (OSError, ValueError):
        pass
    return None


def _cache_put(key, data):
    path = os.path.join(cache_dir(), hashlib.sha1(key.encode()).hexdigest() + ".json")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass


def _http(method, url, headers=None, body=None, form=None):
    data = None
    headers = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    headers.setdefault("Accept", "application/json")
    headers.setdefault("User-Agent", "kicad-bomtool/1.0")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")[:400]
        if e.code == 404:
            return None
        if e.code == 429:
            raise ProviderError("For mange forespørgsler (rate limit) – prøv igen om lidt.")
        if e.code in (401, 403):
            raise ProviderError(f"Adgang nægtet ({e.code}) – tjek API-nøglen. {text}")
        raise ProviderError(f"HTTP {e.code}: {text}")
    except urllib.error.URLError as e:
        raise ProviderError(f"Ingen forbindelse: {e.reason}")
    except ValueError:
        raise ProviderError("Ugyldigt svar fra serveren.")


def _param(params, *names):
    for n in names:
        for k, v in params.items():
            if k.lower() == n.lower() and v and v != "-":
                return v
    return ""


# ---- DigiKey --------------------------------------------------------------------

class DigiKey:
    name = "DigiKey"
    BASE = "https://api.digikey.com"
    limiter = RateLimiter(100)

    def __init__(self, cfg):
        self.cid = cfg.get("digikey_client_id", "").strip()
        self.secret = cfg.get("digikey_client_secret", "").strip()
        self.customer = cfg.get("digikey_customer_id", "").strip()
        self.currency = cfg.get("currency", "DKK")
        self.site = cfg.get("country", "DK")
        self.token, self.token_exp = None, 0
        self.lock = threading.Lock()

    @property
    def enabled(self):
        return bool(self.cid and self.secret)

    def _auth(self):
        with self.lock:
            if self.token and time.time() < self.token_exp - 60:
                return self.token
            res = _http("POST", self.BASE + "/v1/oauth2/token",
                        form={"client_id": self.cid, "client_secret": self.secret,
                              "grant_type": "client_credentials"})
            if not res or "access_token" not in res:
                raise ProviderError("DigiKey login fejlede – tjek Client ID/Secret.")
            self.token = res["access_token"]
            self.token_exp = time.time() + int(res.get("expires_in", 600))
            return self.token

    def _headers(self):
        h = {"Authorization": "Bearer " + self._auth(), "X-DIGIKEY-Client-Id": self.cid,
             "X-DIGIKEY-Locale-Site": self.site, "X-DIGIKEY-Locale-Language": "en",
             "X-DIGIKEY-Locale-Currency": self.currency}
        if self.customer:
            h["X-DIGIKEY-Customer-Id"] = self.customer
        return h

    def _call(self, method, path, body=None):
        key = f"dk|{self.site}|{self.currency}|{method}|{path}|{json.dumps(body, sort_keys=True)}"
        cached = _cache_get(key)
        if cached is not None:
            return cached
        self.limiter.wait()
        res = _http(method, self.BASE + path, headers=self._headers(), body=body)
        _cache_put(key, res)
        return res

    def lookup(self, pn):
        res = self._call("GET", "/products/v4/search/" + urllib.parse.quote(pn, safe="") + "/productdetails")
        if res and res.get("Product"):
            return [self._part(res["Product"])]
        return self.search(pn, limit=5, exact_first=pn)

    def search(self, keywords, limit=10, exact_first=None):
        res = self._call("POST", "/products/v4/search/keyword",
                         {"Keywords": keywords, "Limit": limit, "Offset": 0})
        if not res:
            return []
        prods = (res.get("ExactMatches") or []) + (res.get("Products") or [])
        seen, out = set(), []
        for p in prods:
            part = self._part(p)
            if part["mpn"] in seen:
                continue
            seen.add(part["mpn"])
            out.append(part)
        return out

    def substitutes(self, pn):
        try:
            res = self._call("GET", "/products/v4/search/" + urllib.parse.quote(pn, safe="") + "/substitutions")
        except ProviderError:
            return []
        out = []
        for s in (res or {}).get("ProductSubstitutes", []) or []:
            out.append({"mpn": s.get("ManufacturerProductNumber", ""),
                        "mfr": (s.get("Manufacturer") or {}).get("Name", ""),
                        "desc": s.get("Description", "") if isinstance(s.get("Description"), str) else
                        (s.get("Description") or {}).get("ProductDescription", ""),
                        "type": s.get("SubstituteType", ""), "url": s.get("ProductUrl", ""),
                        "stock": s.get("QuantityAvailable", 0), "source": self.name})
        return out

    def _part(self, p):
        desc = p.get("Description") or {}
        params = {}
        for prm in p.get("Parameters") or []:
            params[prm.get("ParameterText", "")] = prm.get("ValueText", "")
        offers = []
        for v in p.get("ProductVariations") or []:
            pkg_type = (v.get("PackageType") or {}).get("Name", "")
            breaks = [[b.get("BreakQuantity", 0), b.get("UnitPrice", 0)] for b in v.get("StandardPricing") or []]
            if not breaks:
                continue
            offers.append({"seller": self.name, "sku": v.get("DigiKeyProductNumber", ""), "packaging": pkg_type,
                           "moq": v.get("MinimumOrderQuantity") or breaks[0][0] or 1, "mult": 1,
                           "stock": v.get("QuantityAvailableforPackageType", p.get("QuantityAvailable", 0)),
                           "currency": self.currency, "breaks": breaks, "url": p.get("ProductUrl", ""),
                           "reel_fee": "digi-reel" in pkg_type.lower()})
        status = (p.get("ProductStatus") or {}).get("Status", "")
        return {
            "source": self.name, "mpn": p.get("ManufacturerProductNumber", ""),
            "mfr": (p.get("Manufacturer") or {}).get("Name", ""),
            "desc": desc.get("DetailedDescription") or desc.get("ProductDescription", ""),
            "package": _param(params, "Package / Case", "Supplier Device Package"),
            "package2": _param(params, "Supplier Device Package"),
            "datasheet": p.get("DatasheetUrl", "") or "", "url": p.get("ProductUrl", ""),
            "stock": p.get("QuantityAvailable", 0), "category": (p.get("Category") or {}).get("Name", ""),
            "lifecycle": status, "params": params, "offers": offers,
            "dist_pn": offers[0]["sku"] if offers else "",
        }


# ---- Mouser ---------------------------------------------------------------------

class Mouser:
    name = "Mouser"
    BASE = "https://api.mouser.com/api/v1"
    limiter = RateLimiter(28)   # Mouser allows 30 calls/minute

    def __init__(self, cfg):
        self.key = cfg.get("mouser_key", "").strip()
        self.currency = cfg.get("currency", "DKK")

    @property
    def enabled(self):
        return bool(self.key)

    def _call(self, path, body):
        key = f"mouser|{path}|{json.dumps(body, sort_keys=True)}"
        cached = _cache_get(key)
        if cached is not None:
            return cached
        self.limiter.wait()
        res = _http("POST", f"{self.BASE}{path}?apiKey={urllib.parse.quote(self.key)}", body=body)
        errs = (res or {}).get("Errors") or []
        if errs:
            raise ProviderError("Mouser: " + "; ".join(e.get("Message", str(e)) for e in errs))
        _cache_put(key, res)
        return res

    def lookup(self, pn):
        res = self._call("/search/partnumber",
                         {"SearchByPartRequest": {"mouserPartNumber": pn, "partSearchOptions": "Exact"}})
        parts = self._parts(res)
        if not parts:
            res = self._call("/search/partnumber",
                             {"SearchByPartRequest": {"mouserPartNumber": pn, "partSearchOptions": "None"}})
            parts = self._parts(res)
        return parts

    def search(self, keywords, limit=10, exact_first=None):
        res = self._call("/search/keyword", {"SearchByKeywordRequest": {
            "keyword": keywords, "records": limit, "startingRecord": 0, "searchOptions": "InStock",
            "searchWithYourSignUpLanguage": "false"}})
        return self._parts(res)

    def substitutes(self, pn):
        return []

    def _parts(self, res):
        out = []
        for p in ((res or {}).get("SearchResults") or {}).get("Parts") or []:
            breaks, cur = [], self.currency
            for b in p.get("PriceBreaks") or []:
                price, c = parse_price(b.get("Price"))
                if price is not None:
                    breaks.append([int(b.get("Quantity", 1)), price])
                    cur = b.get("Currency") or c or cur
            params = {a.get("AttributeName", ""): a.get("AttributeValue", "") for a in p.get("ProductAttributes") or []}
            stock = p.get("AvailabilityInStock") or "0"
            try:
                stock = int(str(stock).replace(".", "").replace(",", ""))
            except ValueError:
                stock = 0
            offers = []
            if breaks:
                offers.append({"seller": self.name, "sku": p.get("MouserPartNumber", ""),
                               "packaging": params.get("Packaging", ""),
                               "moq": int(p.get("Min") or breaks[0][0] or 1), "mult": int(p.get("Mult") or 1),
                               "stock": stock, "currency": cur, "breaks": breaks,
                               "url": p.get("ProductDetailUrl", ""), "reel_fee": False})
            desc = p.get("Description", "")
            out.append({
                "source": self.name, "mpn": p.get("ManufacturerPartNumber", ""), "mfr": p.get("Manufacturer", ""),
                "desc": desc, "package": _param(params, "Package / Case", "Case Code - in", "Package/Case") or "",
                "datasheet": p.get("DataSheetUrl", "") or "", "url": p.get("ProductDetailUrl", ""),
                "stock": stock, "category": p.get("Category", ""), "lifecycle": p.get("LifecycleStatus") or "",
                "params": params, "offers": offers, "dist_pn": p.get("MouserPartNumber", ""),
            })
        return [o for o in out if o["mpn"]]


# ---- Nexar / Octopart -----------------------------------------------------------

class Nexar:
    name = "Nexar"
    limiter = RateLimiter(60)
    QUERY = """query($q: String!, $limit: Int!, $cur: String!, $country: String!) {
  supSearchMpn(q: $q, limit: $limit, currency: $cur, country: $country) {
    results { part {
      mpn manufacturer { name } shortDescription category { name }
      bestDatasheet { url } octopartUrl
      specs { attribute { name shortname } displayValue }
      similarParts { mpn manufacturer { name } shortDescription octopartUrl }
      sellers(authorizedOnly: true) { company { name } offers {
        sku packaging moq inventoryLevel clickUrl
        prices { quantity price currency convertedPrice convertedCurrency } } }
    } } } }"""

    def __init__(self, cfg):
        self.cid = cfg.get("nexar_client_id", "").strip()
        self.secret = cfg.get("nexar_client_secret", "").strip()
        self.currency = cfg.get("currency", "DKK")
        self.country = cfg.get("country", "DK")
        self.token, self.token_exp = None, 0
        self.lock = threading.Lock()

    @property
    def enabled(self):
        return bool(self.cid and self.secret)

    def _auth(self):
        with self.lock:
            if self.token and time.time() < self.token_exp - 60:
                return self.token
            res = _http("POST", "https://identity.nexar.com/connect/token",
                        form={"grant_type": "client_credentials", "client_id": self.cid,
                              "client_secret": self.secret, "scope": "supply.domain"})
            if not res or "access_token" not in res:
                raise ProviderError("Nexar login fejlede – tjek Client ID/Secret.")
            self.token = res["access_token"]
            self.token_exp = time.time() + int(res.get("expires_in", 3600))
            return self.token

    def _query(self, q, limit):
        variables = {"q": q, "limit": limit, "cur": self.currency, "country": self.country}
        key = f"nexar|{json.dumps(variables, sort_keys=True)}"
        cached = _cache_get(key)
        if cached is not None:
            return cached
        self.limiter.wait()
        res = _http("POST", "https://api.nexar.com/graphql",
                    headers={"Authorization": "Bearer " + self._auth()},
                    body={"query": self.QUERY, "variables": variables})
        if res and res.get("errors"):
            raise ProviderError("Nexar: " + "; ".join(e.get("message", "") for e in res["errors"]))
        _cache_put(key, res)
        return res

    def lookup(self, pn):
        return self._parts(self._query(pn, 3))

    def search(self, keywords, limit=10, exact_first=None):
        return self._parts(self._query(keywords, limit))

    def substitutes(self, pn):
        out = []
        for part in self.lookup(pn)[:1]:
            for s in part.get("similar", []):
                out.append(dict(s, source=self.name, type="Lignende (Octopart)"))
        return out

    def _parts(self, res):
        out = []
        for r in (((res or {}).get("data") or {}).get("supSearchMpn") or {}).get("results") or []:
            p = r.get("part") or {}
            params = {(s.get("attribute") or {}).get("name", ""): s.get("displayValue", "") for s in p.get("specs") or []}
            offers = []
            for seller in p.get("sellers") or []:
                cname = (seller.get("company") or {}).get("name", "")
                for o in seller.get("offers") or []:
                    breaks = []
                    for pr in o.get("prices") or []:
                        price = pr.get("convertedPrice") if pr.get("convertedPrice") is not None else pr.get("price")
                        breaks.append([pr.get("quantity", 1), price])
                    if not breaks:
                        continue
                    breaks.sort()
                    offers.append({"seller": cname, "sku": o.get("sku", ""), "packaging": o.get("packaging") or "",
                                   "moq": o.get("moq") or breaks[0][0] or 1, "mult": 1,
                                   "stock": o.get("inventoryLevel") or 0, "currency": self.currency,
                                   "breaks": breaks, "url": o.get("clickUrl", ""),
                                   "reel_fee": "reel" in (o.get("packaging") or "").lower() and
                                   "digi" in (o.get("packaging") or "").lower()})
            similar = [{"mpn": s.get("mpn", ""), "mfr": (s.get("manufacturer") or {}).get("name", ""),
                        "desc": s.get("shortDescription", ""), "url": s.get("octopartUrl", "")}
                       for s in p.get("similarParts") or []]
            out.append({
                "source": self.name, "mpn": p.get("mpn", ""), "mfr": (p.get("manufacturer") or {}).get("name", ""),
                "desc": p.get("shortDescription", ""),
                "package": _param(params, "Case/Package", "Package", "Case"),
                "datasheet": (p.get("bestDatasheet") or {}).get("url", ""), "url": p.get("octopartUrl", ""),
                "stock": sum(o["stock"] or 0 for o in offers), "category": (p.get("category") or {}).get("name", ""),
                "lifecycle": _param(params, "Lifecycle Status"), "params": params, "offers": offers,
                "dist_pn": "", "similar": similar,
            })
        return out


def mouser_cart(cfg, items):
    """Put items [(mouser_pn, qty, customer_ref)] in a new Mouser cart via the Cart API.
    Uses the Cart/Order API key if set, otherwise the Search key. Returns Mouser's answer, normalised."""
    key = (cfg.get("mouser_cart_key") or cfg.get("mouser_key") or "").strip()
    if not key:
        raise ProviderError("Ingen Mouser-nøgle – indtast en under Indstillinger.")
    body = {"CartKey": "", "CartItems": [{"MouserPartNumber": pn, "Quantity": int(qty),
                                           "CustomerPartNumber": ref[:30]} for pn, qty, ref in items]}
    query = urllib.parse.urlencode({"apiKey": key, "countryCode": cfg.get("country", "DK"),
                                    "currencyCode": cfg.get("currency", "DKK")})
    res = _http("POST", f"https://api.mouser.com/api/v1/cart/items/insert?{query}", body=body)
    if res is None:
        raise ProviderError("Mouser svarede ikke på kurv-forespørgslen.")
    errs = [e.get("Message", "") for e in res.get("Errors") or []]
    if errs and not res.get("CartItems"):
        raise ProviderError("Mouser: " + "; ".join(errs))
    lines = []
    for it in res.get("CartItems") or []:
        price, _ = parse_price(it.get("UnitPrice"))
        lines.append({"sku": it.get("MouserPartNumber", ""), "mpn": it.get("MfrPartNumber", ""),
                      "qty": it.get("Quantity"), "unit": price,
                      "errors": [e.get("Message", "") for e in it.get("Errors") or []] + list(it.get("InfoMessages") or [])})
    total, _ = parse_price(res.get("MerchandiseTotal"))
    return {"cart_key": res.get("CartKey", ""), "currency": res.get("CurrencyCode", ""), "total": total,
            "lines": lines, "errors": errs}


def make_providers(cfg):
    return [p for p in (DigiKey(cfg), Mouser(cfg), Nexar(cfg)) if p.enabled]

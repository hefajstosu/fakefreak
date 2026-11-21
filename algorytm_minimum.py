"""
MINIMUM algorytmu grupowania reklam w kampanie (wersja z analiza_algorytmu.md, sekcja 4).

Zakres: kanał tekstowy (maskowanie encji -> embedding szablonu, zbiór encji) oraz kanał
infrastruktury (domeny z łańcucha przekierowań, identyfikatory śledzące).
Poza zakresem: obraz (pHash, CLIP, twarze), GUI, kalibracja na wariantach z LLM, graf.

Komentarze oznaczone:
    DO USTALENIA  - wartość/decyzja do dobrania na danych organizatora
    DYSKUSYJNE    - przyjęte uproszczenie, które może okazać się złe
    DO ZMIANY     - świadomie prowizoryczne, do wymiany w kolejnej wersji

Uruchomienie:
    pip install -r requirements.txt
    python -m spacy download pl_core_news_sm
    python algorytm_minimum.py
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import numpy as np
import requests
import spacy
from sentence_transformers import SentenceTransformer

# =============================================================================
# Konfiguracja
# =============================================================================

# DO USTALENIA: wagi kanałów. Docelowo stroić na zbiorze walidacyjnym
# (przeszukiwanie siatki albo regresja logistyczna na parach "ta sama / inna kampania").
WAGI = {
    "szablon": 1.0,   # podobieństwo tekstu po zamaskowaniu encji
    "encje": 0.5,     # wspólne osoby / organizacje / miejsca
    "tracking": 2.0,  # wspólne GA / GTM / Pixel ID
    "domena": 1.5,    # wspólna domena w łańcuchu przekierowań
}

TAU_GLOBALNY = 0.60          # DO USTALENIA: próg dla kampanii, których nie da się skalibrować
K_SIGMA = 2.0                # DO USTALENIA: próg_K = mu_K - K_SIGMA * sigma_K
MIN_CZLONKOW_KALIBRACJA = 3  # DO USTALENIA: od ilu członków liczyć próg per kampania
PROG_MIN, PROG_MAX = 0.45, 0.85  # DYSKUSYJNE: widełki, żeby próg_K nie uciekł przy małych kampaniach
TOP_K = 3                    # podobieństwo do kampanii = średnia z TOP_K najbardziej podobnych członków

# DYSKUSYJNE: wspólny rzadki identyfikator śledzący to "mocne powiązanie",
# które podnosi score do co najmniej MOCNE_POWIAZANIE niezależnie od tekstu.
MOCNE_POWIAZANIE = 0.90
MIN_RZADKOSC_MOCNEGO = 0.5

# DO USTALENIA: e5-small jest szybki; e5-base/large dają lepsze embeddingi kosztem czasu.
MODEL_EMBEDDINGOW = "intfloat/multilingual-e5-small"

# DO USTALENIA: modele e5 mają "ściśnięty" rozkład cosinusa (niezwiązane teksty ~0.7-0.8,
# a nie ~0). Przeskalowanie liniowe [E5_COS_MIN, 1] -> [0, 1]. Dolną granicę wyznaczyć
# empirycznie: średnie podobieństwo par z RÓŻNYCH kampanii w zbiorze organizatora.
E5_COS_MIN = 0.80

# DO ZMIANY: wartości pospolite, które nie mogą łączyć kampanii (CDN-y, hostingi, platformy).
# Rzadkość wyliczana z bazy częściowo to załatwia, ale przy małej bazie wszystko wygląda na rzadkie.
IGNOROWANE_DOMENY = {"facebook.com", "fb.com", "instagram.com", "google.com", "youtube.com",
                     "bit.ly", "t.co", "l.facebook.com", "cloudflare.com"}

TRACKING_REGEXY = {
    "ga": re.compile(r"\b(G-[A-Z0-9]{6,12}|UA-\d{4,10}-\d{1,4})\b"),
    "gtm": re.compile(r"\bGTM-[A-Z0-9]{4,8}\b"),
    "fbpixel": re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{10,20})['\"]"),
    # DO ZMIANY: dodać TikTok Pixel, Yandex Metrica, Hotjar, identyfikatory partnerskie z URL (aff_id, sub1 itd.)
}

# Mapowanie etykiet NER modelu pl_core_news_sm na placeholdery w szablonie.
NER_NA_PLACEHOLDER = {
    "persName": "[OSOBA]",
    "orgName": "[ORGANIZACJA]",
    "placeName": "[MIEJSCE]",
    "geogName": "[MIEJSCE]",
    # DYSKUSYJNE: daty/czasy też maskujemy, bo scamy podmieniają "dziś", "w 2024" itp.
    "date": "[DATA]",
    "time": "[DATA]",
}
KWOTA_RE = re.compile(
    r"\d[\d\s.,]*\s?(?:zł|złotych|pln|eur|euro|€|\$|usd|tys\.?|mln)", re.IGNORECASE
)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

MOBILNY_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")


# =============================================================================
# Struktury danych
# =============================================================================

@dataclass
class Material:
    """Wejście. DO USTALENIA: dopasować do formatu zbioru organizatora (CSV? JSON? zrzuty?)."""
    id: str
    tekst: Optional[str] = None   # tekst reklamy / strony (np. z OCR - poza tym skryptem)
    url: Optional[str] = None     # URL reklamy albo strony docelowej
    html: Optional[str] = None    # jeśli podany, nie pobieramy strony z sieci


@dataclass
class Cechy:
    id: str
    hash_tekstu: Optional[str]
    szablon: Optional[str]
    emb: Optional[np.ndarray]     # znormalizowany embedding szablonu
    encje: Set[str]
    tracking: Set[str]
    domeny: Set[str]
    braki: List[str] = field(default_factory=list)  # czego nie udało się pozyskać (do pokazania w GUI)


@dataclass
class Kampania:
    id: str
    czlonkowie: List[Cechy] = field(default_factory=list)
    potwierdzona: bool = True
    duplikaty: Dict[str, List[str]] = field(default_factory=dict)  # id oryginału -> id duplikatów


@dataclass
class Wynik:
    material_id: str
    decyzja: str                  # "duplikat" | "przypisano" | "nowa_kampania"
    kampania_id: str
    score: float
    prog: Optional[float]
    przeslanki: List[str]
    podobne_kampanie: List[Tuple[str, float]]
    braki: List[str]


# =============================================================================
# Ekstrakcja cech
# =============================================================================

class Ekstraktor:
    def __init__(self) -> None:
        self.nlp = spacy.load("pl_core_news_sm")
        self.model = SentenceTransformer(MODEL_EMBEDDINGOW)

    # ---- tekst ----

    def maskuj(self, tekst: str) -> Tuple[str, Set[str]]:
        """Zamienia encje na placeholdery i zwraca (szablon, zbiór encji)."""
        tekst = URL_RE.sub("[URL]", tekst)
        tekst = KWOTA_RE.sub("[KWOTA]", tekst)
        doc = self.nlp(tekst)
        encje: Set[str] = set()
        czesci, ostatni = [], 0
        for ent in doc.ents:
            placeholder = NER_NA_PLACEHOLDER.get(ent.label_)
            if placeholder is None:
                continue
            czesci.append(tekst[ostatni:ent.start_char])
            czesci.append(placeholder)
            ostatni = ent.end_char
            if placeholder in ("[OSOBA]", "[ORGANIZACJA]", "[MIEJSCE]"):
                # DYSKUSYJNE: lemat ujednolica odmianę ("Kowalskiego" -> "Kowalski"),
                # ale model sm myli się na nazwiskach. Docelowo: model lg albo dopasowanie do bazy osób.
                encje.add(f"{placeholder.strip('[]').lower()}:{ent.lemma_.lower()}")
        czesci.append(tekst[ostatni:])
        # DO ZMIANY: NER nie wykrywa nazw produktów/platform ("QuantumAI", "Bitcoin Era"),
        # które są kluczowe w scamach. Opcje: lista znanych nazw, heurystyka wielkich liter
        # w środku zdania, ekstrakcja przez LLM.
        return "".join(czesci), encje

    def embedding(self, szablon: str) -> np.ndarray:
        # Prefiks "passage: " wymagany przez modele e5.
        # DO ZMIANY: e5 ucina tekst po 512 tokenach; długie strony dzielić na fragmenty i uśredniać.
        return self.model.encode("passage: " + szablon, normalize_embeddings=True)

    # ---- infrastruktura ----

    @staticmethod
    def pobierz_strone(url: str) -> Tuple[Optional[str], List[str]]:
        """Zwraca (html, łańcuch URL-i). Przy błędzie (None, [url])."""
        # DO ZMIANY: requests nie wykonuje JS, więc nie zobaczy przekierowań w JavaScripcie
        # ani treści ukrytej przed botami (cloaking). Docelowo Playwright z mobilnym UA,
        # polskim locale i refererem z platformy społecznościowej + zapis zrzutu i HTML.
        try:
            r = requests.get(url, headers={"User-Agent": MOBILNY_UA, "Accept-Language": "pl-PL"},
                             timeout=10, allow_redirects=True)
            return r.text, [h.url for h in r.history] + [r.url]
        except requests.RequestException:
            return None, [url]

    @staticmethod
    def domena(url: str) -> Optional[str]:
        host = urlparse(url if "://" in url else "http://" + url).hostname
        if not host:
            return None
        # DO ZMIANY: użyć tldextract, żeby a.b.example.co.uk -> example.co.uk.
        # Teraz tylko obcinamy "www.", więc subdomeny tej samej domeny się nie łączą.
        return host[4:] if host.startswith("www.") else host

    # ---- całość ----

    def ekstrahuj(self, m: Material) -> Cechy:
        braki: List[str] = []

        html, lancuch = m.html, ([m.url] if m.url else [])
        if m.url and html is None:
            html, lancuch = self.pobierz_strone(m.url)
            if html is None:
                braki.append("strona niedostępna")

        domeny = {d for u in lancuch if (d := self.domena(u))} - IGNOROWANE_DOMENY
        tracking: Set[str] = set()
        if html:
            for nazwa, rx in TRACKING_REGEXY.items():
                tracking |= {f"{nazwa}:{x}" for x in rx.findall(html)}
        else:
            braki.append("brak HTML")

        tekst = m.tekst
        if not tekst and html:
            # DO ZMIANY: prymitywne wyciąganie tekstu z HTML; docelowo trafilatura/readability.
            tekst = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S)
            tekst = re.sub(r"\s+", " ", tekst).strip()

        szablon, emb, encje, hash_tekstu = None, None, set(), None
        if tekst:
            norm = re.sub(r"\W+", " ", tekst.lower()).strip()
            hash_tekstu = hashlib.sha1(norm.encode()).hexdigest()
            szablon, encje = self.maskuj(tekst)
            emb = self.embedding(szablon)
        else:
            braki.append("brak tekstu")

        return Cechy(m.id, hash_tekstu, szablon, emb, encje, tracking, domeny, braki)


# =============================================================================
# Podobieństwo
# =============================================================================

class Baza:
    def __init__(self) -> None:
        self.kampanie: List[Kampania] = []
        self.df: Counter = Counter()   # w ilu materiałach wystąpiła dana wartość cechy
        self.n = 0
        self._licznik = 0

    # ---- rzadkość ----

    def rzadkosc(self, wartosc: str) -> float:
        """log(N/df) znormalizowane do [0, 1]. 1 = wartość unikalna, 0 = występuje wszędzie."""
        # DYSKUSYJNE: przy małej bazie (N < ~50) wszystko jest "rzadkie" i wagi tracą sens.
        # Rozważyć df liczone z większego, zewnętrznego zbioru albo minimalne N.
        if self.n <= 1:
            return 1.0
        df = max(self.df[wartosc], 1)
        return max(0.0, math.log(self.n / df) / math.log(self.n))

    def _dodaj_do_df(self, c: Cechy) -> None:
        self.n += 1
        for v in c.encje | c.tracking | {f"dom:{d}" for d in c.domeny}:
            self.df[v] += 1

    # ---- podobieństwo dwóch materiałów ----

    def _jaccard_wazony(self, a: Set[str], b: Set[str]) -> Optional[float]:
        if not a or not b:
            return None   # brak danych po którejś stronie = cecha pomijana, nie zero
        suma = sum(self.rzadkosc(v) for v in a | b)
        return sum(self.rzadkosc(v) for v in a & b) / suma if suma else 0.0

    def _max_wspolny(self, a: Set[str], b: Set[str]) -> Optional[Tuple[float, Optional[str]]]:
        # DYSKUSYJNE: dla identyfikatorów liczy się najrzadsza WSPÓLNA wartość, a nie odsetek
        # wspólnych (jeden wspólny GA-ID wśród pięciu skryptów to nadal silny dowód).
        if not a or not b:
            return None
        wspolne = a & b
        if not wspolne:
            return 0.0, None
        v = max(wspolne, key=self.rzadkosc)
        return self.rzadkosc(v), v

    def podobienstwo(self, a: Cechy, b: Cechy) -> Tuple[float, List[str]]:
        sims: Dict[str, float] = {}
        przeslanki: List[str] = []

        if a.emb is not None and b.emb is not None:
            cos = float(a.emb @ b.emb)
            sims["szablon"] = min(1.0, max(0.0, (cos - E5_COS_MIN) / (1 - E5_COS_MIN)))
            przeslanki.append(f"szablon tekstu: cos={cos:.3f} -> {sims['szablon']:.2f}")

        # DYSKUSYJNE: encje działają tylko jako dowód "za". Brak wspólnej osoby nie obniża
        # score, bo kampanie rotują celebrytów (to cel maskowania). Inaczej materiał z tym samym
        # szablonem i inną osobą dostawał 0 w tym kanale i ledwo przechodził próg.
        s = self._jaccard_wazony(a.encje, b.encje)
        if s is not None and a.encje & b.encje:
            sims["encje"] = s
            przeslanki.append(f"wspólne encje {sorted(a.encje & b.encje)}: {s:.2f}")

        mocne = False
        t = self._max_wspolny(a.tracking, b.tracking)
        if t is not None:
            sims["tracking"], v = t
            if v:
                przeslanki.append(f"wspólny identyfikator {v} (rzadkość {t[0]:.2f})")
                mocne = t[0] >= MIN_RZADKOSC_MOCNEGO

        d = self._max_wspolny({f"dom:{x}" for x in a.domeny}, {f"dom:{x}" for x in b.domeny})
        if d is not None:
            sims["domena"], v = d
            if v:
                przeslanki.append(f"wspólna domena {v[4:]} (rzadkość {d[0]:.2f})")

        if not sims:
            return 0.0, ["brak wspólnych dostępnych cech"]

        # Średnia ważona tylko po cechach dostępnych w obu materiałach (brak != zero).
        # DYSKUSYJNE: jeśli dostępny jest tylko jeden słaby kanał, score bywa zawyżony;
        # rozważyć karę za małą liczbę kanałów albo wymóg min. 2 kanałów do przypisania.
        score = sum(WAGI[k] * v for k, v in sims.items()) / sum(WAGI[k] for k in sims)
        if mocne:
            score = max(score, MOCNE_POWIAZANIE)
            przeslanki.append("mocne powiązanie: wspólny rzadki identyfikator")
        return score, przeslanki

    # ---- podobieństwo do kampanii i próg ----

    def score_kampanii(self, c: Cechy, k: Kampania, pomin: Optional[str] = None
                       ) -> Tuple[float, List[str]]:
        wyniki = sorted((self.podobienstwo(c, m) for m in k.czlonkowie if m.id != pomin),
                        key=lambda x: x[0], reverse=True)
        if not wyniki:
            return 0.0, []
        top = wyniki[:TOP_K]
        # Przesłanki pokazujemy z najbardziej podobnego członka.
        return float(np.mean([s for s, _ in top])), top[0][1]

    def prog_kampanii(self, k: Kampania) -> float:
        # DO ZMIANY: docelowo mu/sigma z wariantów walidacyjnych (LLM) przypisanych do kampanii.
        # Tu: leave-one-out na członkach - jak podobny jest każdy członek do reszty kampanii.
        # Koszt O(n^2) na kampanię; przy większej bazie cache'ować.
        if len(k.czlonkowie) < MIN_CZLONKOW_KALIBRACJA:
            return TAU_GLOBALNY
        s = [self.score_kampanii(m, k, pomin=m.id)[0] for m in k.czlonkowie]
        prog = float(np.mean(s) - K_SIGMA * np.std(s))
        return min(PROG_MAX, max(PROG_MIN, prog))

    # ---- główna procedura ----

    def przetworz(self, c: Cechy) -> Wynik:
        # 1. Deduplikacja: identyczny znormalizowany tekst.
        # DO ZMIANY: dodać pHash obrazu i finalny URL jako kryteria duplikatu.
        if c.hash_tekstu:
            for k in self.kampanie:
                for m in k.czlonkowie:
                    if m.hash_tekstu == c.hash_tekstu:
                        k.duplikaty.setdefault(m.id, []).append(c.id)
                        return Wynik(c.id, "duplikat", k.id, 1.0, None,
                                     [f"identyczny tekst jak {m.id}"], [], c.braki)

        # 2. Podobieństwo do każdej kampanii.
        # DO ZMIANY: przy dużej bazie najpierw kandydaci z FAISS + indeksu odwróconego po tracking/domenach.
        oceny = []
        for k in self.kampanie:
            score, przeslanki = self.score_kampanii(c, k)
            prog = self.prog_kampanii(k)
            # DYSKUSYJNE: niepotwierdzone kampanie traktujemy tak samo; rozważyć wyższy próg
            # albo niższą wagę, żeby ograniczyć dryf (problem P8).
            oceny.append((score, prog, k, przeslanki))
        oceny.sort(key=lambda x: x[0] - x[1], reverse=True)   # największa nadwyżka nad progiem
        powyzej = [o for o in oceny if o[0] >= o[1]]

        self._dodaj_do_df(c)

        if powyzej:
            score, prog, k, przeslanki = powyzej[0]
            k.czlonkowie.append(c)
            podobne = [(o[2].id, round(o[0], 3)) for o in powyzej[1:]]
            return Wynik(c.id, "przypisano", k.id, score, prog, przeslanki, podobne, c.braki)

        # 3. Nowa kampania - niepotwierdzona, dopóki analityk jej nie zatwierdzi.
        self._licznik += 1
        nowa = Kampania(f"K{self._licznik}", [c], potwierdzona=False)
        self.kampanie.append(nowa)
        najblizsza = oceny[0] if oceny else None
        przeslanki = ([f"najbliżej {najblizsza[2].id}: score {najblizsza[0]:.3f} < próg {najblizsza[1]:.3f}"]
                      if najblizsza else ["pusta baza"])
        return Wynik(c.id, "nowa_kampania", nowa.id, najblizsza[0] if najblizsza else 0.0,
                     najblizsza[1] if najblizsza else None, przeslanki, [], c.braki)


# =============================================================================
# Demo na zmyślonych danych
# =============================================================================

def _html(ga: Optional[str] = None, pixel: Optional[str] = None) -> str:
    skrypty = ""
    if ga:
        skrypty += f"<script>gtag('config', '{ga}');</script>"
    if pixel:
        skrypty += f"<script>fbq('init', '{pixel}');</script>"
    return f"<html><head>{skrypty}</head><body></body></html>"


PRZYKLADY = [
    # Kampania A: inwestycje, wspólny GA-ID, różne osoby i domeny.
    Material("a1", "Jan Kowalski ujawnia, jak zarobić 15 000 zł miesięcznie na platformie QuantumAI. "
                   "Banki są wściekłe! Zarejestruj się dziś, liczba miejsc ograniczona.",
             "https://zarobek-szybko.example/promo", _html(ga="G-ABC123XYZ")),
    Material("a2", "Anna Nowak zdradza, jak zarabiać 12 000 zł miesięcznie dzięki platformie QuantumAI. "
                   "Banki chcą to ukryć! Zarejestruj się teraz, zostało niewiele miejsc.",
             "https://zysk-teraz.example/start", _html(ga="G-ABC123XYZ", pixel="123456789012345")),
    Material("a3", "Piotr Wiśniewski pokazuje, jak zarobić 20 000 zł miesięcznie na platformie QuantumAI. "
                   "Banki są w szoku! Dołącz dziś, liczba miejsc ograniczona."),  # brak URL/HTML
    # Duplikat a1 (inne białe znaki i interpunkcja).
    Material("a1-dup", "Jan Kowalski ujawnia jak zarobić 15 000 zł miesięcznie na platformie QuantumAI!  "
                       "Banki są wściekłe. Zarejestruj się dziś, liczba miejsc ograniczona"),
    # Kampania B: "cudowny lek", wspólny Pixel ID.
    Material("b1", "Profesor Marek Zieliński: ten naturalny preparat leczy ból stawów w 7 dni. "
                   "Lekarze milczą, bo koncerny farmaceutyczne tracą miliony. Zamów z rabatem 50%.",
             "https://stawy-zdrowe.example/", _html(pixel="999888777666555")),
    Material("b2", "Doktor Ewa Lewandowska: naturalna kuracja usuwa ból stawów w tydzień. "
                   "Koncerny ukrywają tę metodę. Zamów dzisiaj z rabatem 50%.",
             "https://zdrowe-kolana.example/oferta", _html(pixel="999888777666555")),
    # Coś zupełnie innego - powinno dać nową kampanię.
    Material("c1", "Wygraj nowy iPhone! Wypełnij krótką ankietę i odbierz nagrodę za 1 zł.",
             "https://nagroda-dla-ciebie.example/", _html(ga="G-ZZZ999QQQ")),
]


def main() -> None:
    ekstraktor = Ekstraktor()
    baza = Baza()
    for m in PRZYKLADY:
        w = baza.przetworz(ekstraktor.ekstrahuj(m))
        prog = f", próg {w.prog:.3f}" if w.prog is not None else ""
        print(f"\n[{w.material_id}] {w.decyzja.upper()} -> {w.kampania_id} (score {w.score:.3f}{prog})")
        for p in w.przeslanki:
            print(f"    - {p}")
        if w.podobne_kampanie:
            print(f"    podobne kampanie: {w.podobne_kampanie}")
        if w.braki:
            print(f"    braki danych: {', '.join(w.braki)}")

    print("\nKampanie:")
    for k in baza.kampanie:
        status = "" if k.potwierdzona else " [niepotwierdzona]"
        print(f"  {k.id}{status}: {[m.id for m in k.czlonkowie]}  duplikaty: {k.duplikaty or '-'}")


if __name__ == "__main__":
    main()

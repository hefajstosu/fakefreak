# fakefreak

Grupowanie podejrzanych reklam w kampanie oszustw na podstawie wspólnych śladów tekstowych i infrastrukturalnych. Projekt na wyzwanie HackNation „Kolekcjoner fejków / Follow the Fake” (NASK PIB).

- [`analiza_algorytmu.md`](analiza_algorytmu.md): analiza pierwotnego pomysłu, problemy i proponowany algorytm
- [`algorytm_minimum.py`](algorytm_minimum.py): minimalna działająca implementacja (tekst + infrastruktura)
- `diagram_obecny.svg`, `diagram_proponowany.svg`: schematy algorytmów

## Uruchomienie

Wymaga Pythona 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m spacy download pl_core_news_sm
.venv/bin/python algorytm_minimum.py
```

Przy pierwszym uruchomieniu pobierany jest model `intfloat/multilingual-e5-small` (około 470 MB) z Hugging Face. Nie są potrzebne klucze API.

## Użyte modele i licencje

| Model / biblioteka | Licencja |
|---|---|
| `intfloat/multilingual-e5-small` | MIT |
| spaCy | MIT |
| `pl_core_news_sm` | GNU GPL 3.0 |
| sentence-transformers | Apache 2.0 |

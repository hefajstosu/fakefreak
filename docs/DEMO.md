# Demo script (about 6 minutes) and fallback plan

## Before the session
1. `docker compose up --build` (or `pip install -r requirements.lock`, then `cd src && python -m ads.web.server`) with
   the per-case files in `data/cases/` and `GEMINI_API_KEY` in `.env`; open http://127.0.0.1:8000.
2. The status line says "LLM gotowy". Run the new-material analysis you will show once in advance: answers are cached,
   so repeating it on stage costs nothing and cannot hit the daily quota (it resets about 09:00 Warsaw time).

## Walkthrough
1. **The idea (30 s).** Many ads look independent; they share traces. Each case becomes a structured profile, profiles
   are compared feature by feature, and every link is explained.
2. **Rozpoznane grupy.** Campaign K1 (cases 1 and 2) is held together by hard evidence; its explanation lists the rule,
   the shared signature (tracker, registration batch, template, persuasion) and why the nearest campaign stays
   separate: it shares the landing-page tool and page kit (family evidence), not an operator. The family frame groups the
   investment campaigns; open a link's *Dlaczego?* to show the score split into feature groups, shared values,
   differences and the score without each group.
3. **Graf powiązań.** Campaigns by colour, families framed, red edges hard evidence, red dashed edges family evidence.
   Click an edge for its explanation, a case to open its card (domain age, hosting, certificates included).
4. **Analizator.** Drop an ad screenshot, a saved landing page or a HAR log (several files at once), or paste a URL, and
   press *Analizuj*. Read the verdict and *Dlaczego taki werdykt* (the rule that fired, the numbers it compared, whether
   one feature group decides it), *Dopasowanie do kampanii* (joined or not, on which rule, per campaign) and the family
   line. *Pobierz raport* saves it all as Markdown; *Zapisz do bazy* stores it as unconfirmed.
5. **Threshold.** Move τ: campaigns merge only when their mean score allows it; families stay.
6. **Measurements (30 s).** `python -m ads.evaluation.quality`: new material against known campaigns, campaign purity
   1.00 and no false joins; be upfront about the open gaps (`docs/METHODOLOGY.md`, section 10).
7. **Close (30 s).** Two levels of grouping, every link explained, measured on the organiser's own test scenario.

## If something goes wrong
| Symptom | Cause | What to do |
|---|---|---|
| Status says "brak klucza LLM" | no key on this machine | show the groups, the graph and the explanations; they need no LLM |
| "All configured models are out of quota" | daily free-tier limit | use an analysis cached in advance, or try after 09:00 Warsaw time |
| Very little text from a URL | page rendered by JavaScript or cloaked | drop a screenshot, the saved page or a HAR log instead |
| Page does not load | server not running | `docker compose up` or `cd src && python -m ads.web.server` |
| No cases listed | `data/cases/*/profile.json` missing | restore the per-case files (README, "Sample data") |

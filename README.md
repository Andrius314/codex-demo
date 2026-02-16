# Codex Demo Projektas

Tikslas: parodyti minimalu automatizavimo pavyzdi su Codex.

## Struktura
- `app.py` - paprasta funkcija `greet()` ir CLI paleidimas.
- `test_app.py` - 2 minimalus testai.
- `scripts/run.ps1` - viena komanda testams + programos paleidimui.
- `scripts/generate_daily_post.py` - surenka RSS naujienas ir sukuria kasdienio straipsnio `.md` faila.
- `.github/workflows/daily-news.yml` - GitHub Actions workflow kasdieniam publikavimui.
- `posts/` - sugeneruoti straipsniai (tinka GitHub Pages/Jekyll).

## Kaip paleisti lokaliai
1. `cd c:\Users\nerap\Desktop\codex-demo`
2. `python -m pip install pytest`
3. `powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1`
4. `python .\scripts\generate_daily_post.py`

## GitHub automatizavimas
`daily-news.yml` daro sita:
1. Kasdien 07:00 UTC paleidzia `generate_daily_post.py`.
2. Sugeneruoja `posts/YYYY-MM-DD-daily-news-digest.md`.
3. Jei yra pakeitimu, automatinis commit + push i ta pati repo.

Workflow paleidimas ranka:
- GitHub -> `Actions` -> `Daily News Digest` -> `Run workflow`.

## Pritaikymas
- Temos pavadinimas: keisk `NEWS_TOPIC` workflow faile.
- Feed'ai: keisk `NEWS_FEEDS` env (per kablelius) arba redaguok `DEFAULT_FEEDS` skripte.
- Nauju straipsniu kiekis: `NEWS_MAX_ITEMS`.

## Ka tai parodo
- Kaip Codex sukuria failu struktura.
- Kaip Codex automatizuoja veiksmus per skripta.
- Kaip GitHub Actions gali kasdien publikuoti turini.

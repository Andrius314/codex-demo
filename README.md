# Codex Demo Projektas

Tikslas: parodyti praktini automatizavimo pavyzdi su GitHub Pages.

## Struktura
- `scripts/generate_daily_post.py` - surenka RSS naujienas ir sukuria:
  - `posts/YYYY-MM-DD-daily-news-digest.md`
  - `news/latest.json`
- `news/index.html` - naujienu puslapis, kuris atvaizduoja `latest.json`.
- `.github/workflows/daily-news.yml` - kasdienis GitHub Actions paleidimas.

## Kaip paleisti lokaliai
1. `cd c:\Users\nerap\Desktop\codex-demo`
2. `python .\scripts\generate_daily_post.py`
3. Atidaryk `news/index.html` naršyklėje.

## GitHub automatizavimas
`daily-news.yml` daro sita:
1. Kasdien 07:00 UTC paleidzia `generate_daily_post.py`.
2. Atnaujina `posts/` ir `news/latest.json`.
3. Jei yra pakeitimu, padaro commit + push i ta pati repo.

Workflow paleidimas ranka:
- GitHub -> `Actions` -> `Daily News Digest` -> `Run workflow`.

## Pritaikymas
- Temos pavadinimas: `NEWS_TOPIC` workflow faile.
- Feed'ai: `NEWS_FEEDS` env (per kablelius) arba `DEFAULT_FEEDS` skripte.
- Nauju straipsniu kiekis: `NEWS_MAX_ITEMS`.

## GitHub Pages URL
Kai ijungsi Pages is `main` branch, naujienu puslapis bus:
- `https://andrius314.github.io/codex-demo/news/`

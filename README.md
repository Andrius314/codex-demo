# Codex Demo Projektas

Tikslas: praktinis DI ir technologijų naujienų automatizavimas GitHub Pages aplinkoje.

## Kas veikia
- `scripts/generate_daily_post.py` surenka AI/tech RSS srautus ir sugeneruoja:
  - `posts/YYYY-MM-DD-ai-tech-news-digest.md`
  - `news/latest.json`
  - `news/archive.json`
- `news/index.html` rodo gražų puslapį lietuvių kalba su:
  - kalendoriumi (`type=date`) pagal santraukos datą,
  - rikiavimu (naujausios/seniausios/pagal šaltinį),
  - kortelėmis ir miniatiūromis (jei feed pateikia vaizdą).
- `.github/workflows/daily-news.yml` kasdien paleidžia generatorių ir automatiškai commitina pakeitimus.

## Paleidimas lokaliai
1. `cd c:\Users\nerap\Desktop\codex-demo`
2. `python .\scripts\generate_daily_post.py`
3. atidaryk `news/index.html` naršyklėje.

## Naudojami feed'ai
- `https://www.artificialintelligence-news.com/feed/`
- `https://www.marktechpost.com/feed/`
- `https://blog.google/technology/ai/rss/`

## Kur matyti puslapį
Po GitHub Pages deploy:
- `https://andrius314.github.io/codex-demo/news/`

## Konfigūracija
- Temos pavadinimas: `NEWS_TOPIC`
- Įrašų kiekis: `NEWS_MAX_ITEMS`
- Feed'ai (kableliais): `NEWS_FEEDS`
- Santraukos ilgis: `NEWS_SUMMARY_CHARS`

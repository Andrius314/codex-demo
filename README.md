# Codex Demo Projektas

Tikslas: praktinis DI ir technologijų naujienų automatizavimas GitHub Pages aplinkoje.

## Kas veikia dabar
- `scripts/generate_daily_post.py` kas paleidimą sugeneruoja:
  - `posts/YYYY-MM-DD-ai-tech-news-digest.md`
  - `news/latest.json`
  - `news/archive.json`
  - `news/generated-images/*.svg` (lokaliai sugeneruoti viršeliai be jokio API rakto)
- `news/index.html` rodo lietuvišką puslapį su:
  - kalendoriumi pagal datą,
  - rikiavimu,
  - filtru (Visi / YouTube / Straipsniai),
  - kortelėmis su automatiniais viršeliais,
  - `Plačiau` bloku su bullet pointais ir praktine info:
    - ar nemokama/mokama ir kainos užuominos,
    - ar veikia online ar lokaliai,
    - online limitai,
    - lokalūs reikalavimai,
    - ar jau galima bandyti ir kur.
- `.github/workflows/daily-news.yml` kasdien paleidžia generatorių, commitina ir pushina naują turinį.

## YouTube + straipsniai
Generatorius paima naujausius video iš YouTube kanalų, bando nuskaityti transkriptą ir parašo LT santrauką.

Konfigūracija per env:
- `NEWS_YOUTUBE_CHANNELS`:
  - gali būti `UC...` channel ID,
  - arba `https://www.youtube.com/channel/UC...`,
  - arba `https://www.youtube.com/@handle`.

Numatytas workflow pavyzdys jau naudoja kelis AI kanalų ID:
- `UCIgnGlGkVRhd4qNFcEwLL4A` (`@theAIsearch`)
- `UCbfYPyITQ-7l4upoX8nvctg`
- `UCZHmQk67mSJgfCCTn7xBfew`
- `UCXZCJLdBC09xxGZ6gcdrc6A`

## Vertimas į lietuvių kalbą
- `NEWS_TRANSLATE_LT=true` įjungia automatinį vertimą.
- Naudojamas nemokamas vertimo endpoint be API rakto (gali turėti greičio/ribojimų svyravimus).

## Vaizdai be API
- `NEWS_IMAGE_MODE=generated` sukuria SVG viršelius lokaliai (nemokamai, be API).
- `NEWS_IMAGE_MODE=source` ima tik šaltinių pateiktas miniatiūras.
- `NEWS_IMAGE_MODE=hybrid` ima šaltinio miniatiūrą, o jei nėra – sugeneruoja SVG.

## Paleidimas lokaliai
1. `cd c:\Users\nerap\Desktop\codex-demo`
2. `python -m pip install youtube-transcript-api`
3. `python .\scripts\generate_daily_post.py`
4. atidaryk `news/index.html` naršyklėje.

## Kur matyti gyvai
- `https://andrius314.github.io/codex-demo/news/`

## Svarbiausi env
- `NEWS_TOPIC`
- `NEWS_MAX_ITEMS`
- `NEWS_FEEDS`
- `NEWS_YOUTUBE_CHANNELS`
- `NEWS_TRANSLATE_LT`
- `NEWS_IMAGE_MODE`
- `NEWS_MAX_YOUTUBE_PER_CHANNEL`
- `NEWS_MIN_VIDEO_ITEMS`

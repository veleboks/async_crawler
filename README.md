# async_crawler

Асинхронный веб-краулер на Python с управлением конкурентностью, очередью URL и парсингом HTML.

## Возможности

- параллельная загрузка страниц через `aiohttp`;
- глобальные и отдельные для каждого hostname ограничения конкурентности;
- ограничение частоты запросов;
- обход ссылок с ограничением глубины и количества страниц;
- извлечение текста, метаданных, ссылок и изображений через BeautifulSoup и lxml;
- обработка сетевых ошибок, таймаутов и повторяющихся URL;
- логирование и базовая статистика обхода.

## Запуск

Требуются Python 3.13 и [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python examples/simple_fetch.py
uv run python examples/simple_parse.py
uv run python examples/simple_crawl.py
```

Тесты и проверка форматирования:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

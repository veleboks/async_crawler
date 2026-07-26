import logging
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag
from bs4.exceptions import ParserRejectedMarkup

logger = logging.getLogger(__name__)


class HTMLParser:
    def parse_html(self, html: str, url: str) -> dict[str, Any]:
        try:
            soup = BeautifulSoup(html, "lxml")
        except (UnicodeEncodeError, ParserRejectedMarkup) as err:
            logger.warning("Failed to parse html of '%s' error='%s'", url, err)
            return {
                "url": url,
                "title": None,
                "text": "",
                "links": [],
                "images": [],
                "metadata": {
                    "description": None,
                    "keywords": None,
                },
            }

        return {
            "url": url,
            "title": self.extract_title(soup),
            "text": self.extract_text(soup),
            "links": self.extract_links(soup, url),
            "metadata": self.extract_metadata(soup),
            "images": self.extract_images(soup, url),
        }

    def process_image(self, tag: Tag, base_url: str) -> dict[str, str | None] | None:
        result = {}

        src = tag.get("src")
        if not isinstance(src, str) or src.strip() == "":
            logger.debug("Skip img with empty or incorrect src in %s", base_url)
            return None
        src = self.process_link(src.strip(), base_url)
        if src is None:
            return None

        result["src"] = src

        alt = tag.get("alt")
        result["alt"] = alt.strip() if isinstance(alt, str) else None

        return result

    def extract_images(
        self, soup: BeautifulSoup, url: str
    ) -> list[dict[str, str | None]]:
        tags = soup.find_all("img")
        images = []
        for tag in tags:
            image = self.process_image(tag, url)
            if image is not None:
                images.append(image)
        return images

    def extract_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        metadata: dict[str, str | list[str] | None] = {
            "description": None,
            "keywords": None,
        }

        description_tag = soup.find("meta", attrs={"name": "description"}, content=True)
        if description_tag is not None:
            content = description_tag.get("content")
            if isinstance(content, str):
                metadata["description"] = content.strip()

        keywords_tag = soup.find("meta", attrs={"name": "keywords"}, content=True)
        if keywords_tag is not None:
            content = keywords_tag.get("content")
            if isinstance(content, str):
                metadata["keywords"] = [
                    x.strip() for x in content.split(",") if len(x.strip())
                ]

        return metadata

    def extract_title(self, soup: BeautifulSoup) -> str | None:
        tag = soup.find("title")
        if tag is None:
            return None
        return tag.get_text(separator=" ", strip=True)

    def extract_text(self, soup: BeautifulSoup, selector: str | None = None) -> str:
        if selector is not None:
            element = soup.select_one(selector)
            if element is None:
                return ""
            return element.get_text(separator=" ", strip=True)
        return soup.get_text(separator=" ", strip=True)

    def process_link(self, href: str, base_url: str) -> str | None:
        link = href
        try:
            link = urljoin(base_url, link)
            link, _ = urldefrag(link)
            parsed = urlsplit(link)

        except ValueError as err:
            logger.debug(
                "Skipping invalid link: base_url=%r href=%r error=%s",
                base_url,
                href,
                err,
            )
            return None

        if not (parsed.scheme in ["http", "https"] and parsed.hostname):
            logger.debug(
                "Found link '%s' has incorrect scheme or does not have hostname", link
            )
            return None

        return link

    def extract_links(self, soup: BeautifulSoup, url: str) -> list[str]:
        tags = soup.find_all("a", href=True)
        links = []
        for tag in tags:
            href = tag["href"]
            if not isinstance(href, str):
                continue

            link = href.strip()
            if not link:
                logger.debug("Found empty link in '%s' html", url)
                continue

            logger.debug("Found raw link %r in '%s' html", link, url)

            link = self.process_link(link, url)

            if link is not None:
                links.append(link)

        return links

from crawler.html_parser import HTMLParser


def test_parse_valid_html():
    html = """
    <!doctype html>
    <html>
        <head>
            <title>Async crawler</title>
            <meta name="description" content="  A crawler example  ">
            <meta name="keywords" content=" python, asyncio, aiohttp, python ">
        </head>
        <body>
            <main>
                <p>Page content</p>

                <a href="https://other.example/docs">Absolute</a>
                <a href="/about">Root relative</a>
                <a href="next">Path relative</a>
                <a href="mailto:test@example.com">Email</a>
                <a href="javascript:void(0)">JavaScript</a>
                <a href="">Empty</a>

                <img src="https://cdn.example/cat.jpg" alt="Cat">
                <img src="/images/dog.jpg" alt="  Dog  ">
                <img src="images/bird.jpg">
                <img src="data:image/png;base64,AAAA" alt="Embedded">
                <img alt="Missing source">
                <img src="">
            </main>
        </body>
    </html>
    """
    base_url = "https://example.com/articles/page.html"

    result = HTMLParser().parse_html(html, base_url)

    assert result["url"] == base_url
    assert result["title"] == "Async crawler"
    assert "Page content" in result["text"]
    assert result["metadata"] == {
        "description": "A crawler example",
        "keywords": ["python", "asyncio", "aiohttp", "python"],
    }
    assert result["links"] == [
        "https://other.example/docs",
        "https://example.com/about",
        "https://example.com/articles/next",
    ]
    assert result["images"] == [
        {"src": "https://cdn.example/cat.jpg", "alt": "Cat"},
        {"src": "https://example.com/images/dog.jpg", "alt": "Dog"},
        {
            "src": "https://example.com/articles/images/bird.jpg",
            "alt": None,
        },
    ]


def test_parse_broken_html():
    html = """
    <html>
        <head>
            <title>Broken page</title>
            <meta name="description" content="Still parseable">
            <meta name="keywords" content="broken, html">
        </head>
        <body>
            <main>
                <p>Unclosed paragraph
                <div>Nested incorrectly

                <a href="/recovered">Recovered relative link
                <a href="https://other.example/recovered">Recovered absolute link
                <a href="https://[invalid">Invalid link

                <img src="../images/recovered.jpg" alt=" Recovered image ">
                <img src="https://cdn.example/recovered.png">
                <img src="https://[invalid" alt="Invalid image">
    """
    base_url = "https://example.com/articles/page.html"

    result = HTMLParser().parse_html(html, base_url)

    assert result["title"] == "Broken page"
    assert "Unclosed paragraph" in result["text"]
    assert result["metadata"] == {
        "description": "Still parseable",
        "keywords": ["broken", "html"],
    }
    assert result["links"] == [
        "https://example.com/recovered",
        "https://other.example/recovered",
    ]
    assert result["images"] == [
        {
            "src": "https://example.com/images/recovered.jpg",
            "alt": "Recovered image",
        },
        {"src": "https://cdn.example/recovered.png", "alt": None},
    ]


def test_parse_invalid_unicode_returns_partial_result():
    source = "<html><body>\ud800</body></html>"
    url = "https://example.com/invalid"

    result = HTMLParser().parse_html(source, url)

    assert result == {
        "url": url,
        "title": None,
        "text": "",
        "links": [],
        "metadata": {
            "description": None,
            "keywords": None,
        },
        "images": [],
    }

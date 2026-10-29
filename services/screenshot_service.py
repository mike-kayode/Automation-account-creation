from pathlib import Path

from playwright.async_api import Page


async def capture(page: Page, directory: str | Path, name: str) -> Path:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{name}.png"
    # Spec section 9: passwords must never appear in screenshots.
    # Mask password inputs before capturing.
    try:
        await page.evaluate(
            """() => {
                document.querySelectorAll('input[type="password"]').forEach((el) => {
                    el.setAttribute('data-worker-masked', el.getAttribute('type') || '');
                    el.setAttribute('type', 'text');
                    el.value = '********';
                });
            }"""
        )
    except Exception:
        pass
    await page.screenshot(path=str(path), full_page=True)
    return path


async def capture_dom_state(page: Page, directory: str | Path, name: str) -> Path:
    """Spec section 5: on manual-review pause, log DOM/state alongside screenshot."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{name}.html"
    try:
        html = await page.content()
    except Exception as error:
        html = f"<!-- DOM capture failed: {error} -->"
    try:
        url = page.url
    except Exception:
        url = "<unknown>"
    path.write_text(f"<!-- url: {url} -->\n{html}", encoding="utf-8")
    return path

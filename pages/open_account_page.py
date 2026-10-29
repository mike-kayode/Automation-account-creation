import re

from playwright.async_api import Locator, Page

# The account-type picker page ships React-Native-Web markup whose hooks are
# `data-testid` (captured 2026-10-10: account-row-* and account-types-continue
# exist ONLY as data-testid), while the setup form still uses the older
# `data-test` spelling. Select BOTH everywhere so either DOM revision works.
def _hook(name: str) -> str:
    return f'[data-test="{name}"], [data-testid="{name}"]'


ROW_CONTAINER = _hook("account-row-container")
ROW_TITLE = _hook("account-row-title")
ROW_RADIO = _hook("account-row-radio")
ROW_RADIO_MARK = _hook("account-row-radio-mark")
CONTINUE_HOOK = _hook("account-types-continue")


class OpenAccountPage:
    """DOM adapter for the observed Pro demo MT5 setup flow."""

    def __init__(self, page: Page, timeout_ms: int, poll_ms: int = 40, retries: int = 25):
        self.page = page
        self.timeout_ms = timeout_ms
        # Existence-probe bound: an element that is ABSENT must fail fast.
        # Full timeout_ms is reserved for required-state waits only.
        self.probe_ms = min(timeout_ms, 1500)
        self.poll_ms = poll_ms
        self.retries = retries

    async def _settle(self, check, description: str):
        """State-based verify: check IMMEDIATELY first (costs ~0 when the
        state is already true), then poll every poll_ms. Bounded worst case
        = retries * poll_ms; no blind sleeps, no waiting after last try."""
        for attempt in range(self.retries):
            try:
                if await check():
                    return True
            except Exception:
                pass
            if attempt < self.retries - 1:
                await self.page.wait_for_timeout(self.poll_ms)
        return False

    async def wait_until_loaded(self) -> None:
        await self.page.get_by_text(re.compile("set up your account|professional accounts", re.I)).first.wait_for(timeout=self.timeout_ms)

    async def _visible(self, locator: Locator) -> bool:
        try:
            await locator.first.wait_for(state="visible", timeout=self.probe_ms)
            return True
        except Exception:
            return False

    async def _is_enabled(self, locator: Locator) -> bool:
        try:
            return await locator.first.is_enabled(timeout=2000)
        except Exception:
            return False

    async def _scroll_and_click(self, locator: Locator, description: str) -> None:
        # Spec section 5: WAIT -> DETECT -> ACTION -> VERIFY -> CONTINUE.
        # Verify visible + enabled before clicking.
        try:
            await locator.first.wait_for(state="visible", timeout=self.timeout_ms)
        except Exception:
            raise LookupError(f"EXPECTED_ELEMENT_NOT_FOUND: {description}")
        if not await self._is_enabled(locator):
            raise LookupError(f"EXPECTED_ELEMENT_NOT_FOUND (not enabled): {description}")
        await locator.first.scroll_into_view_if_needed()
        await locator.first.click(timeout=self.timeout_ms)

    async def _account_row(self, title: str) -> Locator | None:
        # Locate the account-type row for `title` on either DOM revision
        # (data-testid first - that is what the live picker uses - then the
        # legacy data-test hook, then the role=radio row). Every probe is a
        # non-blocking count(): an absent row costs nothing, and on the setup
        # page (post-Continue) this returns None so callers can fall back to
        # the URL check instead of burning a timeout.
        candidates = (
            self.page.locator(
                f'[data-testid="account-row-container"]:has([data-testid="account-row-title"]:has-text("{title}"))'
            ).first,
            self.page.locator(
                f'[data-test="account-row-container"]:has([data-test="account-row-title"]:has-text("{title}"))'
            ).first,
            self.page.get_by_role("radio", name=re.compile(f"^{re.escape(title)}$", re.I)).first,
        )
        for candidate in candidates:
            if await candidate.count():
                return candidate
        return None

    async def select_pro(self) -> None:
        # Spec section 5 account-type sequence:
        # Detect page -> Find Pro row -> Verify visible + enabled ->
        # Click the ROW (the row itself is role=radio; clicking it selects
        # the option - there is no native input element) -> Verify Pro row
        # is the checked one.
        await self.wait_until_loaded()
        row = await self._account_row("Pro")
        if row is None:
            row = self.page.get_by_text("Pro", exact=True).first
        await self._scroll_and_click(row, "Pro account option")
        if not await self.validate_account_type():
            raise ValueError("ACCOUNT_TYPE_VALIDATION_FAILED")

    async def is_pro_selected(self) -> bool:
        # SPEED: every probe is guarded by a non-blocking count(). On the
        # setup page (post-Continue) the account-row/radio DOM does not
        # exist, so we fall straight through to the URL fallback instead of
        # burning a timeout on absent elements.
        row = await self._account_row("Pro")
        if row is None:
            return "/pro/" in (self.page.url or "").lower()
        return await self._row_checked(row)

    async def _row_checked(self, row: Locator) -> bool:
        # Checked-state detection across DOM revisions:
        # 1. Current RN-Web rows expose it ONLY as an inner radio-mark node
        #    (no aria-checked, no input element at all).
        # 2. Older MUI rows carried a `Mui-checked` class on the radio span.
        # 3. Oldest markup used a native <input type="radio">.
        try:
            if await row.locator(ROW_RADIO_MARK).count():
                return True
        except Exception:
            pass
        try:
            cls = await row.locator(ROW_RADIO).first.get_attribute("class") or ""
            if "Mui-checked" in cls:
                return True
        except Exception:
            pass
        try:
            if await row.locator('input[type="radio"]').first.is_checked(timeout=500):
                return True
        except Exception:
            pass
        try:
            return (await row.get_attribute("aria-checked")) == "true"
        except Exception:
            return False

    async def _checked(self, locator: Locator) -> bool:
        try:
            return await locator.is_checked()
        except Exception:
            return (await locator.get_attribute("aria-checked")) == "true"

    async def validate_account_type(self) -> bool:
        # Pro row must be the checked one; other rows must NOT be checked.
        # Scoped per-row via the account-row hooks (data-test / data-testid).
        try:
            rows = self.page.locator(ROW_CONTAINER)
            count = await rows.count()
            pro_checked = False
            for index in range(count):
                row = rows.nth(index)
                try:
                    title = await row.locator(ROW_TITLE).first.inner_text(timeout=500)
                except Exception:
                    continue
                checked = await self._row_checked(row)
                if title.strip().lower() == "pro":
                    pro_checked = checked
                elif checked:
                    return False
            if count:
                return pro_checked
        except Exception:
            pass
        if not await self.is_pro_selected():
            return False
        for name in ("Standard", "Standard Cent", "Raw spread", "Zero"):
            radios = self.page.get_by_role("radio", name=re.compile(f"^{re.escape(name)}$", re.I))
            # Absence is already conclusive (an absent radio is not checked).
            # The timed visible probe below only runs when the radio exists;
            # on the setup page it used to cost probe_ms x4 (~6s) before the
            # Create account click with no effect on the result.
            if not await radios.count():
                continue
            radio = radios.first
            if await self._visible(radio) and await self._checked(radio):
                return False
        return True

    async def click_continue(self) -> None:
        if not await self.validate_account_type():
            raise ValueError("ACCOUNT_TYPE_VALIDATION_FAILED")
        # The Continue control is <button data-testid="account-types-continue">
        # Continue</button> at the bottom of the account-type page (captured
        # DOM 2026-10-10). Use the stable hook first, keep the role-name
        # lookup as fallback for older markup.
        button = self.page.locator(CONTINUE_HOOK).first
        if not await button.count():
            button = self.page.get_by_role("button", name=re.compile(r"^continue$", re.I)).last
            try:
                await button.wait_for(state="visible", timeout=self.timeout_ms)
            except Exception:
                button = self.page.get_by_role("button", name=re.compile(r"^continue$|^next$", re.I)).last
        await self._scroll_and_click(button, "Continue control")
        await self.page.wait_for_url(re.compile(r"/pa/new-account/mt5/pro/demo", re.I), timeout=self.timeout_ms)

    def _testid(self, name: str) -> Locator:
        # Matches both attribute spellings (data-test / data-testid).
        return self.page.locator(_hook(name)).first

    async def _field(self, labels: tuple[str, ...]) -> Locator:
        # Prefer stable data-test hooks (from real captured DOM) first.
        testid_map = {
            "Currency": ("acc-form-currency",),
            "Max leverage": ("account-form-leverage",),
            "Leverage": ("account-form-leverage",),
            "Starting balance": ("account-form-deposit",),
            "Deposit": ("account-form-deposit",),
            "Nickname": ("account-form-name",),
            "Trading password": ("account-form-password", "PasswordField"),
            "Password": ("account-form-password", "PasswordField"),
            "Platform": ("account-form-platform",),
        }
        for label in labels:
            for testid in testid_map.get(label, ()):
                if testid == "PasswordField":
                    candidate = self.page.locator(_hook("PasswordField")).first
                else:
                    container = self._testid(testid)
                    try:
                        await container.wait_for(state="attached", timeout=self.probe_ms)
                    except Exception:
                        continue
                    candidate = container.locator("input, [role='combobox']").first
                if await self._visible(candidate):
                    return candidate
        for label in labels:
            candidates = (
                self.page.get_by_label(re.compile(f"^{re.escape(label)}$", re.I)).first,
                self.page.get_by_label(re.compile(re.escape(label), re.I)).first,
                self.page.get_by_role("combobox", name=re.compile(label, re.I)).first,
                self.page.locator(f"input[placeholder*='{label}' i]").first,
                self.page.locator(
                    f"div:has-text('{label}'):has(input), div:has-text('{label}'):has([role='combobox'])"
                ).locator("input, [role='combobox']").first,
            )
            for candidate in candidates:
                if await self._visible(candidate):
                    return candidate
        raise LookupError(f"EXPECTED_ELEMENT_NOT_FOUND: {labels[0]}")

    async def _select_value(self, labels: tuple[str, ...], value: str) -> None:
        field = await self._field(labels)
        await field.scroll_into_view_if_needed()
        tag = await field.evaluate("(element) => element.tagName.toLowerCase()")
        if tag == "select":
            try:
                await field.select_option(label=value)
            except Exception:
                await field.select_option(value=value)
            return
        # Custom dropdown / MUI autocomplete (Currency shows default USD).
        # WAIT -> clear existing -> type filter -> pick option -> VERIFY.
        # Fast path: if the closed field already shows the value, skip.
        try:
            if value.casefold() in (await self._field_value(field)):
                return
        except Exception:
            pass
        await field.click(timeout=self.timeout_ms)
        try:
            # Clear any default (e.g. USD) so typing filters correctly.
            await field.press("ControlOrMeta+a")
            await field.fill("")
            await field.type(value, delay=10)
        except Exception:
            pass
        option_candidates = (
            self.page.get_by_role("option", name=re.compile(f"^{re.escape(value)}", re.I)).first,
            self.page.get_by_text(re.compile(f"^{re.escape(value)}(\\s|-|$)", re.I)).first,
            self.page.get_by_text(value, exact=True).first,
        )
        for option in option_candidates:
            try:
                await option.wait_for(state="visible", timeout=1500)
            except Exception:
                continue
            await option.scroll_into_view_if_needed()
            await option.click(timeout=3000)
            break
        else:
            raise LookupError(f"EXPECTED_ELEMENT_NOT_FOUND: {value} option")
        try:
            await field.press("Escape")
        except Exception:
            pass

    async def configure_demo(self) -> None:
        # Setup page uses an MUI ToggleButtonGroup, NOT role=tab:
        # <button value="demo" aria-pressed="true" data-test="account-type-demo">.
        # Fast path: URL already encodes /demo AND the toggle reads pressed.
        demo = self._testid("account-type-demo")
        try:
            await demo.wait_for(state="attached", timeout=1500)
            if (await demo.get_attribute("aria-pressed")) == "true":
                return  # already Demo - do not click away from it.
            await demo.wait_for(state="visible", timeout=self.timeout_ms)
        except Exception:
            demo = self.page.get_by_role("tab", name=re.compile(r"^Demo$", re.I)).first
            if not await self._visible(demo):
                demo = self.page.get_by_text("Demo", exact=True).first
            await self._scroll_and_click(demo, "Demo account mode")
            if not await self._is_selected(demo):
                raise ValueError("DEMO_MODE_VALIDATION_FAILED")
            return
        await self._scroll_and_click(demo, "Demo account mode")
        ok = await self._settle(
            lambda: self._pressed(demo), "demo toggle",
        )
        if not ok:
            raise ValueError("DEMO_MODE_VALIDATION_FAILED")

    async def _pressed(self, locator) -> bool:
        try:
            return (await locator.get_attribute("aria-pressed")) == "true"
        except Exception:
            return False

    async def _is_selected(self, locator: Locator) -> bool:
        try:
            if (await locator.get_attribute("aria-pressed")) == "true":
                return True
        except Exception:
            pass
        return (await locator.get_attribute("aria-selected")) == "true" or (await locator.get_attribute("data-state")) == "active"

    async def _mode_is_demo(self) -> bool:
        try:
            demo = self._testid("account-type-demo")
            await demo.wait_for(state="attached", timeout=1500)
            if (await demo.get_attribute("aria-pressed")) == "true":
                return True
        except Exception:
            pass
        demo = self.page.get_by_role("tab", name=re.compile(r"^Demo$", re.I)).first
        if await self._visible(demo):
            return await self._is_selected(demo)
        return "/demo" in (self.page.url or "").lower()

    async def configure_mt5(self) -> None:
        # Platform on this form is fixed/read-only MT5 (captured DOM) - verify state.
        try:
            field = await self._field(("Platform",))
            value = await self._field_value(field)
            if "mt5" in value:
                return
        except LookupError:
            pass
        await self._select_value(("Platform",), "MT5")
        if not await self._selected_value_is(("Platform",), "MT5"):
            raise ValueError("PLATFORM_VALIDATION_FAILED")

    async def configure_leverage(self, leverage: str) -> None:
        # MUI Select, NOT a text input (captured DOM):
        # <div role="combobox" id="degradable_select_leverage">1:2000</div>
        # inside [data-test="account-form-leverage"]. Click opens a listbox
        # popup - typing into it does nothing, so pick the option directly.
        combo = self._testid("account-form-leverage").locator("[role='combobox']").first
        try:
            await combo.wait_for(state="visible", timeout=self.timeout_ms)
        except Exception:
            combo = await self._field(("Max leverage", "Leverage"))
        await combo.scroll_into_view_if_needed()
        current = ((await combo.inner_text()) or "").strip()
        if current == leverage:
            return
        await combo.click(timeout=self.timeout_ms)
        option_candidates = (
            self.page.get_by_role("option", name=re.compile(f"^{re.escape(leverage)}$", re.I)).first,
            self.page.locator("[role='listbox'] [role='option']").filter(has_text=re.compile(f"^{re.escape(leverage)}$")).first,
            self.page.get_by_text(leverage, exact=True).first,
        )
        for option in option_candidates:
            try:
                await option.wait_for(state="visible", timeout=1500)
            except Exception:
                continue
            await option.scroll_into_view_if_needed()
            await option.click(timeout=3000)
            break
        else:
            try:
                await combo.press("Escape")
            except Exception:
                pass
            raise LookupError(f"EXPECTED_ELEMENT_NOT_FOUND: {leverage} option")
        ok = await self._settle(lambda: self._leverage_is(combo, leverage), "leverage")
        if ok:
            return
        current = ((await combo.inner_text()) or "").strip()
        raise ValueError(f"LEVERAGE_VALIDATION_FAILED (shows {current!r})")

    async def _leverage_is(self, combo, leverage: str) -> bool:
        try:
            return ((await combo.inner_text()) or "").strip() == leverage
        except Exception:
            return False

    async def configure_nickname(self, nickname: str) -> None:
        field = await self._field(("Nickname",))
        await field.scroll_into_view_if_needed()
        await field.click(timeout=self.timeout_ms)
        try:
            await field.press("ControlOrMeta+a")
        except Exception:
            pass
        await field.fill(nickname)
        ok = await self._settle(lambda: self._nickname_is(field, nickname), "nickname")
        if ok:
            return
        raise ValueError("NICKNAME_VALIDATION_FAILED")

    async def _nickname_is(self, field, nickname: str) -> bool:
        try:
            return await field.input_value() == nickname
        except Exception:
            return False

    async def configure_currency(self, currency: str) -> None:
        await self._select_value(("Currency",), currency)
        # VERIFY via dropdown-closed state: the field itself must read NGN.
        ok = await self._settle(
            lambda: self._selected_value_is(("Currency",), currency), "currency",
        )
        if ok:
            return
        field = await self._field(("Currency",))
        value = await self._field_value(field)
        raise ValueError(f"CURRENCY_VALIDATION_FAILED (field shows {value!r})")

    async def configure_deposit(self, deposit: int) -> None:
        field = await self._field(("Starting balance", "Deposit"))
        await field.scroll_into_view_if_needed()
        await field.click(timeout=self.timeout_ms)
        # Clear the default (e.g. 500) fully before typing 1500000:
        # Ctrl+A + fill("") + type, then blur to commit.
        try:
            await field.press("ControlOrMeta+a")
        except Exception:
            pass
        try:
            await field.fill("")
        except Exception:
            pass
        await field.type(str(deposit), delay=10)
        try:
            await field.press("Tab")
        except Exception:
            pass
        ok = await self._settle(
            lambda: self._deposit_is(field, deposit), "deposit",
        )
        if ok:
            return
        raise ValueError("DEPOSIT_VALIDATION_FAILED")

    async def _deposit_is(self, field, deposit: int) -> bool:
        try:
            return re.sub(r"[^0-9]", "", await field.input_value()) == str(deposit)
        except Exception:
            return False

    async def configure_password(self, password: str) -> None:
        field = await self._field(("Trading password", "Password"))
        await field.scroll_into_view_if_needed()
        await field.click(timeout=self.timeout_ms)
        try:
            await field.press("ControlOrMeta+a")
        except Exception:
            pass
        await field.fill(password)
        ok = await self._settle(lambda: self._password_is(field, password), "password")
        if ok:
            return
        raise ValueError("PASSWORD_VALIDATION_FAILED")

    async def _password_is(self, field, password: str) -> bool:
        try:
            return await field.input_value() == password
        except Exception:
            return False

    # ONE page.evaluate round trip returns everything validate_configuration
    # needs. The per-field Playwright path performs ~30 sequential CDP calls
    # (field probes, account-row scan, input reads) and was the long pause
    # between arriving at the filled form and the Create account click.
    # Missing data-test hooks yield null per key so Python can fall back per
    # key without changing validation semantics.
    CONFIG_SNAPSHOT_JS = """() => {
        const formValue = (sel) => {
            const c = document.querySelector(sel);
            if (!c) return null;
            const el = c.querySelector('input, textarea, select, [role="combobox"]');
            if (!el) return null;
            if (el.matches('input, textarea, select')) return el.value;
            return (el.textContent || '').trim();
        };
        const strictValue = (sel) => {
            const c = document.querySelector(sel);
            if (!c) return null;
            const el = c.querySelector('input, textarea, select');
            return el ? el.value : null;
        };
        const rows = [];
        document.querySelectorAll('[data-test="account-row-container"], [data-testid="account-row-container"]').forEach((row) => {
            const title = row.querySelector('[data-test="account-row-title"], [data-testid="account-row-title"]');
            const radio = row.querySelector('[data-test="account-row-radio"], [data-testid="account-row-radio"]');
            const mark = row.querySelector('[data-test="account-row-radio-mark"], [data-testid="account-row-radio-mark"]');
            const input = row.querySelector('input[type="radio"]');
            rows.push({
                title: title ? (title.textContent || '').trim() : null,
                radio_cls: radio ? (radio.getAttribute('class') || '') : '',
                input_checked: !!input && !!input.checked,
                mark: !!mark,
            });
        });
        const demo = document.querySelector('[data-test="account-type-demo"], [data-testid="account-type-demo"]');
        const leverage = document.querySelector('[data-test="account-form-leverage"] [role="combobox"], [data-testid="account-form-leverage"] [role="combobox"]');
        return {
            rows: rows,
            demo_pressed: demo ? demo.getAttribute('aria-pressed') : null,
            nickname: strictValue('[data-test="account-form-name"], [data-testid="account-form-name"]'),
            currency: formValue('[data-test="acc-form-currency"], [data-testid="acc-form-currency"]'),
            deposit: strictValue('[data-test="account-form-deposit"], [data-testid="account-form-deposit"]'),
            password: strictValue('[data-test="account-form-password"], [data-testid="account-form-password"]'),
            platform: formValue('[data-test="account-form-platform"], [data-testid="account-form-platform"]'),
            leverage: leverage ? (leverage.textContent || '').trim() : null,
        };
    }"""

    async def validate_configuration(self, nickname: str, currency: str, deposit: int, password: str, leverage: str = "1:100") -> dict[str, bool]:
        # FAST PATH: snapshot the whole form in ONE evaluate round trip, then
        # compute the same booleans the per-field path computes. A null key
        # (missing hook) falls back to the original logic for that key only;
        # a failed snapshot falls back wholesale. Identical results, no
        # multi-round-trip pause before the Create account click.
        try:
            snap = await self.page.evaluate(self.CONFIG_SNAPSHOT_JS)
        except Exception:
            snap = None
        # Wholesale fallback: snapshot failed, or the whole form (account rows
        # + strict fields) is absent - then behave exactly like the original
        # path (same LookupError raised fast for a wrong/missing page).
        if not isinstance(snap, dict) or (
            not snap.get("rows")
            and snap.get("nickname") is None
            and snap.get("deposit") is None
            and snap.get("password") is None
        ):
            return await self._validate_configuration_fields(nickname, currency, deposit, password, leverage)

        account_type = None
        rows = snap.get("rows")
        if rows:
            pro_checked = False
            other_checked = False
            for row in rows:
                title = row.get("title")
                if title is None:
                    continue
                checked = (
                    bool(row.get("mark"))
                    or "Mui-checked" in (row.get("radio_cls") or "")
                    or bool(row.get("input_checked"))
                )
                if title.strip().lower() == "pro":
                    pro_checked = checked
                elif checked:
                    other_checked = True
            account_type = pro_checked and not other_checked

        demo = snap.get("demo_pressed")
        account_mode = True if demo == "true" else None
        platform_raw = snap.get("platform")
        platform = None if platform_raw is None else "mt5" in platform_raw.strip().casefold()
        nickname_raw = snap.get("nickname")
        nickname_ok = None if nickname_raw is None else nickname_raw == nickname
        currency_raw = snap.get("currency")
        currency_ok = None if currency_raw is None else currency.casefold() in currency_raw.strip().casefold()
        deposit_raw = snap.get("deposit")
        deposit_ok = None if deposit_raw is None else re.sub(r"[^0-9]", "", deposit_raw) == str(deposit)
        leverage_raw = snap.get("leverage")
        leverage_ok = None if leverage_raw is None else leverage_raw.strip() == leverage
        password_raw = snap.get("password")
        password_ok = None if password_raw is None else password_raw == password

        if account_type is None:
            account_type = await self.validate_account_type()
        if account_mode is None:
            account_mode = await self._mode_is_demo()
        if platform is None:
            platform = await self._selected_value_is(("Platform",), "MT5")
        if nickname_ok is None:
            nickname_ok = await (await self._field(("Nickname",))).input_value() == nickname
        if currency_ok is None:
            currency_ok = currency.casefold() in await self._field_value(await self._field(("Currency",)))
        if deposit_ok is None:
            deposit_ok = re.sub(r"[^0-9]", "", await (await self._field(("Starting balance", "Deposit"))).input_value()) == str(deposit)
        if leverage_ok is None:
            leverage_ok = await self._selected_value_is(("Max leverage", "Leverage"), leverage)
        if password_ok is None:
            password_ok = await (await self._field(("Trading password", "Password"))).input_value() == password
        return {
            "account_type": account_type,
            "account_mode": account_mode,
            "platform": platform,
            "nickname": nickname_ok,
            "currency": currency_ok,
            "deposit": deposit_ok,
            "leverage": leverage_ok,
            "password": password_ok,
        }

    async def _validate_configuration_fields(self, nickname: str, currency: str, deposit: int, password: str, leverage: str = "1:100") -> dict[str, bool]:
        # Original per-field validation (~30 sequential locator round trips).
        # Kept verbatim as fallback when the data-test hooks are missing.
        nickname_field = await self._field(("Nickname",))
        currency_field = await self._field(("Currency",))
        deposit_field = await self._field(("Starting balance", "Deposit"))
        password_field = await self._field(("Trading password", "Password"))
        try:
            leverage_combo = self._testid("account-form-leverage").locator("[role='combobox']").first
            await leverage_combo.wait_for(state="attached", timeout=1500)
            leverage_value = ((await leverage_combo.inner_text()) or "").strip()
        except Exception:
            leverage_value = leverage if await self._selected_value_is(("Max leverage", "Leverage"), leverage) else ""
        return {
            "account_type": await self.validate_account_type(),
            "account_mode": await self._mode_is_demo(),
            "platform": await self._selected_value_is(("Platform",), "MT5"),
            "nickname": await nickname_field.input_value() == nickname,
            "currency": currency.casefold() in await self._field_value(currency_field),
            "deposit": re.sub(r"[^0-9]", "", await deposit_field.input_value()) == str(deposit),
            "leverage": leverage_value == leverage,
            "password": await password_field.input_value() == password,
        }

    async def _field_value(self, field: Locator) -> str:
        try:
            return (await field.input_value()).strip().casefold()
        except Exception:
            return (await field.inner_text()).strip().casefold()

    async def _selected_value_is(self, labels: tuple[str, ...], expected: str) -> bool:
        return expected.casefold() in await self._field_value(await self._field(labels))

    async def submit(self) -> None:
        # Captured DOM: <button type="submit" data-test="account-form-submit">
        # Prefer the stable hook over role-name matching.
        # Existence via non-blocking count(): the old wait_for(attached,
        # 1500ms) probe had to TIME OUT before the role-name fallback could
        # start whenever the hook was absent - a fixed 1.5s stall right
        # before the click. count() answers immediately either way.
        hook = self.page.locator(_hook("account-form-submit"))
        if not await hook.count():
            button = self.page.get_by_role("button", name=re.compile(r"^Create account$", re.I)).last
            await button.wait_for(state="visible", timeout=self.timeout_ms)
            await self._scroll_and_click(button, "Create account control")
            return
        button = hook.first
        # FAST PATH: the old chain awaited visible -> scroll -> enabled as
        # three separate round trips, then click() RE-ran stability/scroll/
        # hit-target actionability checks before dispatching - that re-check
        # was the pause before the button reacted. Worse, it passed the
        # Locator as wait_for_function arg=..., which arrives in the page as
        # undefined (Playwright does NOT resolve Locator args), so the old
        # predicate threw, the fast path NEVER ran, and every click silently
        # dropped into the slow _scroll_and_click fallback. Now:
        #   1. scroll once (spec: always scroll before interacting), then
        #   2. ONE self-contained readiness gate (querySelector, no arg)
        #      polls every 20 ms until the button is visible (non-zero rect)
        #      + enabled + actually hit-testable at its center, so the forced
        #      click below always lands on the button, never an overlay;
        #      numeric polling keeps working in a background tab where
        #      requestAnimationFrame would freeze.
        #   3. force=True dispatches trusted mouse events immediately - no
        #      stability wait, no second scroll, no hit-target re-verify.
        try:
            await button.scroll_into_view_if_needed()
            await self.page.wait_for_function(
                """() => {
                    const btn = document.querySelector('[data-test="account-form-submit"], [data-testid="account-form-submit"]');
                    if (!btn) return false;
                    const rect = btn.getBoundingClientRect();
                    if (!rect.width || !rect.height) return false;
                    if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') return false;
                    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
                    return !!hit && (hit === btn || btn.contains(hit));
                }""",
                polling=20,
                timeout=self.timeout_ms,
            )
            await button.click(force=True, timeout=3000)
        except Exception:
            await self._scroll_and_click(button, "Create account control")

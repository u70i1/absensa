"""Optional Chromium integration checks: install playwright and Chromium to run."""

import shutil
import subprocess
from io import BytesIO
from urllib.parse import urlsplit

import pytest
from PIL import Image

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def card_browser(card_admin):
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=shutil.which("chromium"))
        context = browser.new_context(viewport={"width": 1440, "height": 1100})

        def serve(route):
            request = route.request
            url = urlsplit(request.url)
            response = card_admin.request(
                request.method,
                url.path + ("?" + url.query if url.query else ""),
                content=request.post_data_buffer,
                headers={**request.headers, "origin": "http://testserver"},
                follow_redirects=False,
            )
            route.fulfill(
                status=response.status_code,
                headers=dict(response.headers),
                body=response.content,
            )

        context.route("http://testserver/**", serve)
        context.add_init_script(
            "window.print = () => { window.printWasCalled = true; };"
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page, context
        assert not errors
        browser.close()


def test_card_ui_ratio_selection_preview_and_confirmation(
    card_browser, existing_student
):
    page, context = card_browser
    page.goto("http://testserver/admin/cards")
    page.get_by_role("button", name="Pengaturan cetak").click()
    page.locator("#card-width").fill("80")
    assert page.locator("#card-height").input_value() == "128"
    page.locator("#card-height").fill("100")
    assert page.locator("#card-width").input_value() == "62.5"
    page.get_by_role("button", name="Simpan pengaturan").click()
    page.get_by_text("Pengaturan cetak berhasil disimpan untuk semua kartu.").wait_for()
    page.locator("[data-close-modal]").first.click()
    page.locator("#student-modal").wait_for(state="hidden")
    page.locator("#card-scope").select_option("selected")
    assert page.locator('#card-operation [value="print"]').is_disabled()
    page.locator("[data-selection-toggle]").click()
    # Clicking row identity exercises the shared capture listener, not only checkboxes.
    page.locator(".student-name").click()
    assert page.locator(".row-selection").is_checked()
    assert page.locator('#card-operation [value="print"]').is_enabled()
    with context.expect_page() as new_page:
        page.locator('#card-operation [value="print"]').click()
    printed = new_page.value
    printed.wait_for_function("window.printWasCalled === true")
    assert printed.locator(".student-card").count() == 1
    assert printed.locator(".top-header").count() == 0
    printed.close()
    page.locator("[data-selection-toggle]").click()
    page.get_by_role("button", name="Pratinjau kartu", exact=True).click()
    page.locator('#modal-content img[alt^="Kartu"]').wait_for()
    assert (
        page.locator("#modal-content img").evaluate("image => image.naturalWidth")
        == 800
    )
    page.locator("[data-close-modal]").first.click()
    page.locator("#student-modal").wait_for(state="hidden")
    page.locator("#card-scope").select_option("all")
    dialogs = []
    page.once(
        "dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss())
    )
    page.locator('#card-operation [value="download"]').click()
    assert "sumber daya" in dialogs[0] and "waktu" in dialogs[0]
    assert page.locator('[name="confirmed"]').input_value() == "false"
    assert len(context.pages) == 1


def test_print_pdf_has_whole_cards_across_paper_sizes(
    card_browser, card_admin, student_factory, tmp_path
):
    page, _ = card_browser
    if not shutil.which("pdftoppm"):
        pytest.skip("Install Poppler for print pagination checks")
    for i in range(9):
        student_factory(name=f"Siswa {i}", nisn=f"{i:010d}")
    response = card_admin.post(
        "/admin/cards/operate",
        data={"scope": "all", "action": "print", "confirmed": "true"},
    )
    page.set_content(response.text, wait_until="load")
    page.wait_for_function("window.printWasCalled === true")
    assert page.locator(".student-card").count() == 9
    for paper, landscape in [("A4", False), ("Letter", False), ("A4", True)]:
        document = tmp_path / f"cards-{paper}-{landscape}.pdf"
        page.pdf(
            path=str(document), format=paper, landscape=landscape, print_background=True
        )
        assert document.stat().st_size > 1000
        raster_prefix = tmp_path / f"page-{paper}-{landscape}"
        subprocess.run(
            ["pdftoppm", "-png", "-r", "72", str(document), str(raster_prefix)],
            check=True,
            capture_output=True,
        )
        raster_pages = sorted(tmp_path.glob(f"{raster_prefix.name}-*.png"))
        assert len(raster_pages) == 3
        complete_cards = 0
        for raster in raster_pages:
            with Image.open(raster).convert("RGB") as image:
                # Find connected card outlines; white interiors no longer differ
                # from the paper. Every large outline must bound a whole card.
                width, height = image.size
                ink = bytearray(
                    image.convert("L").point(lambda value: int(value < 245)).tobytes()
                )
                for index, marked in enumerate(ink):
                    if not marked:
                        continue
                    ink[index] = 0
                    stack = [index]
                    left = right = index % width
                    top = bottom = index // width
                    while stack:
                        current = stack.pop()
                        x, y = current % width, current // width
                        left, right = min(left, x), max(right, x)
                        top, bottom = min(top, y), max(bottom, y)
                        for ny in range(max(0, y - 1), min(height, y + 2)):
                            for nx in range(max(0, x - 1), min(width, x + 2)):
                                neighbor = ny * width + nx
                                if ink[neighbor]:
                                    ink[neighbor] = 0
                                    stack.append(neighbor)
                    if right - left > 190 and bottom - top > 250:
                        assert 196 <= right - left <= 200
                        assert 315 <= bottom - top <= 320
                        complete_cards += 1
        assert complete_cards == 9


def test_school_logo_editor(card_browser, tmp_path):
    page, _ = card_browser
    page.goto("http://testserver/admin/cards")
    page.get_by_role("button", name="Pengaturan cetak").click()
    playwright.expect(page.get_by_role("group", name="Ukuran kartu")).to_have_count(1)
    playwright.expect(page.get_by_role("group", name="Watermark kartu")).to_have_count(
        1
    )
    assert page.locator('[name="watermark_enabled"]').count() == 0
    page.locator("#school-name").fill("Sekolah Nusantara")
    assert not page.locator("[data-card-settings]").evaluate(
        "form => form.checkValidity()"
    )
    image = BytesIO()
    Image.new("RGB", (60, 60), "blue").save(image, format="PNG")
    page.locator("#school-logo").set_input_files(
        {"name": "logo.png", "mimeType": "image/png", "buffer": image.getvalue()}
    )
    assert page.locator("[data-logo-preview]").is_visible()
    assert page.locator("[data-card-settings]").evaluate("form => form.checkValidity()")
    page.get_by_role("button", name="Simpan pengaturan").click()
    page.get_by_text("Pengaturan cetak berhasil disimpan untuk semua kartu.").wait_for()
    assert "/settings/logo" in page.locator("[data-logo-preview]").get_attribute("src")
    page.wait_for_function(
        "document.querySelector('[data-logo-preview]').naturalWidth > 0"
    )
    preview = page.locator("[data-logo-preview]").bounding_box()
    upload = page.get_by_role("button", name="Unggah logo baru").bounding_box()
    assert upload["y"] > preview["y"] + preview["height"]
    page.locator("#student-modal").screenshot(path=str(tmp_path / "card-settings.png"))
    page.get_by_role("button", name="Kosongkan watermark").click()
    assert page.locator("[data-logo-preview]").is_hidden()
    assert page.locator("#school-name").input_value() == ""
    assert page.locator("[data-card-settings]").evaluate("form => form.checkValidity()")
    page.get_by_role("button", name="Simpan pengaturan").click()
    page.get_by_text("Pengaturan cetak berhasil disimpan untuk semua kartu.").wait_for()
    assert page.locator("[data-logo-preview]").is_hidden()


@pytest.mark.parametrize("dashboard", ["students", "cards", "classes"])
def test_selection_survives_filters_history_and_clear(
    card_browser, class_factory, student_factory, dashboard
):
    page, context = card_browser
    expect = playwright.expect
    alpha_class = class_factory(class_name="Alpha", grade=10)
    beta_class = class_factory(class_name="Beta", grade=11)
    alpha = student_factory(
        name="Alpha", nisn="0000000001", class_id=alpha_class.class_id
    )
    beta = student_factory(name="Beta", nisn="0000000002", class_id=beta_class.class_id)
    first = alpha_class.class_id if dashboard == "classes" else alpha.id
    second = beta_class.class_id if dashboard == "classes" else beta.id
    page.goto(f"http://testserver/admin/{dashboard}")
    page.locator("[data-selection-toggle]").click()
    page.locator(f'.row-selection[value="{first}"]').check()
    if dashboard == "cards":
        page.locator("#card-scope").select_option("selected")
    if dashboard == "classes":
        page.locator("#class-grade").select_option("11")
        search = "#class-search"
    else:
        page.get_by_role("link", name="Kelas 11", exact=True).click()
        search = "#student-search"
    expect(page.locator(f'.row-selection[value="{first}"]')).to_have_count(0)
    expect(page.locator("[data-selection-toggle]")).to_have_text("Selesai")
    expect(page.locator("[data-selection-count]")).to_have_text(
        "1 dipilih · 1 di luar tampilan ini"
    )
    page.locator(f'.row-selection[value="{second}"]').check()
    page.locator(search).fill("Beta")
    page.wait_for_url("**/*Beta*")
    expect(page.locator(f'.row-selection[value="{second}"]')).to_be_checked()
    page.locator(search).fill("TidakAda")
    expect(page.locator(".row-selection")).to_have_count(0)
    expect(page.locator("[data-selection-count]")).to_have_text(
        "2 dipilih · 2 di luar tampilan ini"
    )
    if dashboard == "cards":
        expect(page.locator("#card-scope")).to_have_value("selected")
        with context.expect_page() as new_page:
            page.locator('#card-operation [value="print"]').click()
        printed = new_page.value
        printed.wait_for_function("window.printWasCalled === true")
        assert printed.locator(".student-card").count() == 2
        printed.close()
    else:
        page.locator('#table-selection [value="delete"]').click()
        expect(page.locator("#modal-title")).to_have_text(
            "Hapus 2 kelas?" if dashboard == "classes" else "Hapus 2 siswa?"
        )
        expect(page.locator('#modal-content input[name="ids"]')).to_have_count(2)
        page.locator("[data-close-modal]").first.click()
        page.locator("#student-modal").wait_for(state="hidden")
    page.go_back()
    expect(page.locator(f'.row-selection[value="{second}"]')).to_be_checked()
    page.locator("[data-select-all]").uncheck()
    expect(page.locator("[data-selection-count]")).to_have_text(
        "1 dipilih · 1 di luar tampilan ini"
    )
    page.locator("[data-select-all]").check()
    expect(page.locator("[data-selection-count]")).to_have_text(
        "2 dipilih · 1 di luar tampilan ini"
    )
    page.locator(f'.row-selection[value="{second}"]').uncheck()
    expect(page.locator("[data-selection-count]")).to_have_text(
        "1 dipilih · 1 di luar tampilan ini"
    )
    page.locator("[data-selection-toggle]").click()
    expect(page.locator("[data-selection-count]")).to_have_text("0 dipilih")
    page.go_back()
    expect(page.locator("[data-selection-toggle]")).to_have_text("Pilih")
    page.locator("[data-selection-toggle]").click()
    expect(page.locator(".row-selection:checked")).to_have_count(0)
    expect(page.locator("#table-selection [data-selection-hidden]")).to_have_count(0)


@pytest.mark.parametrize("dashboard", ["students", "cards"])
def test_selection_survives_student_pagination(card_browser, db_session, dashboard):
    from app.models.student import Student

    page, _ = card_browser
    expect = playwright.expect
    students = [
        Student(name=f"Student {i:02d}", nisn=f"{i:010d}", current=True)
        for i in range(51)
    ]
    db_session.add_all(students)
    db_session.commit()
    first_id, last_id = students[0].id, students[-1].id
    page.goto(f"http://testserver/admin/{dashboard}")
    page.locator("[data-selection-toggle]").click()
    page.locator(f'.row-selection[value="{first_id}"]').check()
    page.get_by_role("link", name="Selanjutnya", exact=True).click()
    expect(page.locator(f'.row-selection[value="{last_id}"]')).to_be_visible()
    page.locator(f'.row-selection[value="{last_id}"]').check()
    page.get_by_role("link", name="Sebelumnya", exact=True).click()
    expect(page.locator(f'.row-selection[value="{first_id}"]')).to_be_checked()
    expect(page.locator("[data-selection-count]")).to_have_text(
        "2 dipilih · 1 di luar tampilan ini"
    )
    ids = page.locator("#table-selection").evaluate(
        "form => new FormData(form).getAll('ids')"
    )
    assert set(ids) == {str(first_id), str(last_id)}


@pytest.mark.parametrize("kind", ["classes", "students"])
def test_successful_bulk_delete_removes_hidden_selections(
    card_browser, class_factory, student_factory, kind
):
    page, _ = card_browser
    expect = playwright.expect
    if kind == "classes":
        first = class_factory(class_name="Alpha")
        second = class_factory(class_name="Beta")
        first_id, second_id = first.class_id, second.class_id
        search = "#class-search"
    else:
        first = student_factory(name="Alpha", nisn="0000000001")
        second = student_factory(name="Beta", nisn="0000000002")
        first_id, second_id = first.id, second.id
        search = "#student-search"
    page.goto(f"http://testserver/admin/{kind}")
    page.locator("[data-selection-toggle]").click()
    page.locator(f'.row-selection[value="{first_id}"]').check()
    page.locator(f'.row-selection[value="{second_id}"]').check()
    page.locator(search).fill("TidakAda")
    expect(page.locator(".row-selection")).to_have_count(0)
    page.locator('#table-selection [value="delete"]').click()
    page.locator('#modal-content button[type="submit"]').click()
    expect(page.locator("[data-selection-count]")).to_have_text("0 dipilih")
    expect(page.locator("[data-selection-toggle]")).to_have_text("Selesai")


def test_add_student_modal_uploads_photo(card_browser):
    page, _ = card_browser
    expect = playwright.expect
    page.goto("http://testserver/admin/students")
    page.locator("#add-student").click()
    page.locator("#student-name").fill("Siswa Dengan Foto")
    page.locator("#student-nisn").fill("0081234567")
    image = BytesIO()
    Image.new("RGB", (60, 60), "blue").save(image, format="PNG")
    page.locator("#student-photo").set_input_files(
        {"name": "portrait.png", "mimeType": "image/png", "buffer": image.getvalue()}
    )
    page.locator('#modal-content button[type="submit"]').click()
    expect(page.locator("#student-modal")).not_to_be_visible()
    expect(page.locator(".student-name")).to_have_text("Siswa Dengan Foto")
    page.wait_for_function(
        "document.querySelector('.student-row .avatar img')?.naturalWidth > 0"
    )

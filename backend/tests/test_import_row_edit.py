"""Pending row edits preserve validation, atomic writes, ownership and photos."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image
from sqlalchemy import select
from app.models.import_batch import ImportPhoto
from app.models.student import Student
from app.services import import_service
from app.services.exceptions import AppException
from tests.test_import import batch_for, importer, preview, workbook_bytes  # noqa: F401


def student_values():
    return dict(name='Edited draft', nisn='0012345678', class_id='', current='Tidak aktif', guardian_phone='081234567890')


def test_edit_student_draft_then_confirm(client, importer, db_session, existing_student):
    student = existing_student
    batch, page = batch_for(preview(client, rows=[
        [student.id, 'From file', student.class_id, student.nisn, 'Aktif', None],
        [None, 'Unselected', None, '0012345679', 'Aktif', None],
    ]), client, db_session)
    before = deepcopy(batch.payload['rows'][0]['before'])
    url = f'/admin/import/{batch.token}/rows/2/edit'
    assert url in page.text
    assert 'Simpan ke Pratinjau' in client.get(url).text
    response = client.post(url, data={**student_values(), 'revision': 0, 'selected': [2], 'id': 999})
    assert response.status_code == 200, response.text
    assert response.headers['HX-Retarget'] == '#import-review'
    assert 'Edited draft' in response.text
    db_session.refresh(student)
    assert student.name != 'Edited draft'
    db_session.refresh(batch)
    row = batch.payload['rows'][0]
    assert row['before'] == before and row['values']['id'] == student.id
    assert row['values']['current'] is False and row['revision'] == 1
    assert set(row['changed']) == {'name', 'nisn', 'class_id', 'current', 'guardian_phone'}
    assert client.post(f'/admin/import/{batch.token}/confirm', data={'selected': [2]}).status_code == 200
    db_session.refresh(student)
    assert student.name == 'Edited draft' and student.nisn == '0012345678'
    assert student.class_id is None and student.current is False
    assert db_session.scalar(select(Student).where(Student.nisn == '0012345679')) is None


@pytest.mark.parametrize('changes', [
    {'nisn': '123'}, {'name': ' '}, {'guardian_phone': 'bad'}, {'current': 'true'},
    {'class_id': '2147483647'}, {'nisn': '0012345679'},
])
def test_invalid_edits_keep_original_draft(client, importer, db_session, changes):
    batch, _ = batch_for(preview(client, rows=[
        [None, 'One', None, '0012345678', 'Aktif', None],
        [None, 'Two', None, '0012345679', 'Aktif', None],
    ]), client, db_session)
    original = deepcopy(batch.payload)
    response = client.post(f'/admin/import/{batch.token}/rows/2/edit', data={**student_values(), **changes, 'revision': 0})
    assert response.status_code == 422
    assert response.headers['X-Admin-Fragment'] == 'modal'
    assert 'role="alert"' in response.text
    db_session.refresh(batch)
    assert batch.payload == original
    assert db_session.scalar(select(Student)) is None


def test_class_edit_and_revision_conflict(client, importer, db_session, existing_class):
    batch, _ = batch_for(preview(client, 'classes', [[existing_class.class_id, 10, 'Draft']]), client, db_session)
    url = f'/admin/import/{batch.token}/rows/2/edit'
    data = dict(grade='12', class_name='12Z', revision=0, selected=[2], class_id='999')
    assert client.post(url, data=data).status_code == 200
    assert client.post(url, data={**data, 'class_name': 'Stale'}).status_code == 409
    db_session.refresh(existing_class)
    assert existing_class.class_name != '12Z'
    assert client.post(f'/admin/import/{batch.token}/confirm', data={'selected': [2]}).status_code == 200
    db_session.refresh(existing_class)
    assert existing_class.class_name == '12Z' and existing_class.grade == 12
    assert client.post(url, data={**data, 'revision': 1}).status_code == 409


def test_edit_does_not_refresh_stale_snapshot(client, importer, db_session, existing_student):
    batch, _ = batch_for(preview(client, rows=[[existing_student.id, 'Draft', None, existing_student.nisn, 'Aktif', None]]), client, db_session)
    existing_student.name = 'Concurrent edit'
    db_session.commit()
    assert client.post(f'/admin/import/{batch.token}/rows/2/edit', data={**student_values(), 'revision': 0}).status_code == 200
    assert client.post(f'/admin/import/{batch.token}/confirm', data={'selected': [2]}).status_code == 409
    db_session.refresh(existing_student)
    assert existing_student.name == 'Concurrent edit'


def test_editor_ownership_state_and_expiry(client, importer, db_session):
    batch, _ = batch_for(preview(client, 'classes', [[None, 10, '10X']]), client, db_session)
    with pytest.raises(AppException) as error:
        import_service.edit_preview_row(db_session, importer.id + 1, batch.token, 2, {}, 0)
    assert error.value.status_code == 404
    assert client.get(f'/admin/import/{batch.token}/rows/999/edit').status_code == 404
    batch.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(f'/admin/import/{batch.token}/rows/2/edit').status_code == 404
    batch.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    batch.state = 'cancelled'
    db_session.commit()
    assert client.get(f'/admin/import/{batch.token}/rows/2/edit').status_code == 409
    client.cookies.clear()
    assert client.get(f'/admin/import/{batch.token}/rows/2/edit', follow_redirects=False).status_code == 303
    assert client.post(f'/admin/import/{batch.token}/rows/2/edit', data={'revision': 0}, follow_redirects=False).status_code == 303


def test_nisn_edit_retains_staged_photo(client, importer, db_session, monkeypatch):
    image = BytesIO()
    Image.new('RGB', (10, 10), 'red').save(image, 'PNG')
    archive = BytesIO()
    with ZipFile(archive, 'w') as output:
        output.writestr('students.xlsx', workbook_bytes('students', [[None, 'Photo', None, '0012345678', 'Aktif', None]]))
        output.writestr('photos/0012345678.png', image.getvalue())
    batch, _ = batch_for(preview(client, content=archive.getvalue(), filename='data.zip'), client, db_session)
    response = client.post(f'/admin/import/{batch.token}/rows/2/edit', data={**student_values(), 'nisn': '0012345679', 'revision': 0, 'selected': [2]})
    assert response.status_code == 200
    assert '/photos/0012345678' in response.text
    assert db_session.get(ImportPhoto, (batch.token, '0012345678')) is not None
    saved = []
    def save_photo(content):
        saved.append(content)
        return 'edited-photo.jpg'
    monkeypatch.setattr(import_service.student_photo_service, 'store_normalized_photo', save_photo)
    assert client.post(f'/admin/import/{batch.token}/confirm', data={'selected': [2]}).status_code == 200
    assert len(saved) == 1
    assert db_session.scalar(select(Student).where(Student.nisn == '0012345679')).photo_path == 'edited-photo.jpg'

from app.models.scan_log import ScanLog
from sqlalchemy import func, select


class TestDeleteBulk:
    """POST /scans/delete-bulk — all-or-nothing bulk delete by scan_id."""

    ENDPOINT = "/scans/delete-bulk"

    def test_all_ids_exist_returns_204(
        self,
        client,
        db_session,
        existing_student,
        scan_log_factory,
    ):
        log1 = scan_log_factory(student=existing_student)
        log2 = scan_log_factory(student=existing_student)

        response = client.post(
            self.ENDPOINT,
            json={"ids": [log1.scan_id, log2.scan_id]},
        )

        assert response.status_code == 204

        remaining_ids = db_session.scalars(
            select(ScanLog.scan_id).where(
                ScanLog.scan_id.in_([log1.scan_id, log2.scan_id])
            )
        ).all()

        assert remaining_ids == []

    def test_empty_ids_returns_204(self, client, db_session):
        response = client.post(
            self.ENDPOINT,
            json={"ids": []},
        )

        assert response.status_code == 204

        # Nothing should have been created or deleted.
        count = db_session.scalar(select(func.count()).select_from(ScanLog))
        assert count == 0

    def test_missing_id_returns_422_and_deletes_nothing(
        self,
        client,
        db_session,
        existing_student,
        scan_log_factory,
    ):
        log1 = scan_log_factory(student=existing_student)

        max_scan_id = db_session.scalar(select(func.max(ScanLog.scan_id)))
        nonexistent_id = (max_scan_id or 0) + 1

        response = client.post(
            self.ENDPOINT,
            json={"ids": [log1.scan_id, nonexistent_id]},
        )

        assert response.status_code == 422

        body = response.json()
        assert body["missing_ids"] == [nonexistent_id]

        # Bulk delete must be all-or-nothing.
        remaining_log = db_session.scalar(
            select(ScanLog).where(ScanLog.scan_id == log1.scan_id)
        )
        assert remaining_log is not None

    def test_all_ids_missing_returns_422(self, client, db_session):
        max_scan_id = db_session.scalar(select(func.max(ScanLog.scan_id)))

        nonexistent_id_1 = (max_scan_id or 0) + 1
        nonexistent_id_2 = nonexistent_id_1 + 1

        response = client.post(
            self.ENDPOINT,
            json={"ids": [nonexistent_id_1, nonexistent_id_2]},
        )

        assert response.status_code == 422

        body = response.json()
        assert body["missing_ids"] == [
            nonexistent_id_1,
            nonexistent_id_2,
        ]

        count = db_session.scalar(select(func.count()).select_from(ScanLog))
        assert count == 0

    def test_duplicate_ids_deduped_not_treated_as_missing(
        self,
        client,
        db_session,
        existing_student,
        scan_log_factory,
    ):
        log1 = scan_log_factory(student=existing_student)

        response = client.post(
            self.ENDPOINT,
            json={"ids": [log1.scan_id, log1.scan_id]},
        )

        # Sending the same existing ID twice should behave like sending it once.
        assert response.status_code == 204

        remaining_log = db_session.scalar(
            select(ScanLog).where(ScanLog.scan_id == log1.scan_id)
        )
        assert remaining_log is None

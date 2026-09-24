"""Schema contracts that must survive shared-base inheritance."""

from types import SimpleNamespace

import pytest
from app.schemas.class_ import ClassListQuery, ClassResponse
from app.schemas.scan import ScanCreateRequest, ScanListQuery
from app.schemas.student import (
    StudentBulkCreateRequest,
    StudentBulkResponse,
    StudentBulkUpdateRequest,
    StudentListQuery,
    StudentResponse,
    StudentWriteRequest,
)
from pydantic import ValidationError


@pytest.mark.parametrize("model", [ClassListQuery, StudentListQuery])
def test_list_query_preserves_class_alias_and_pagination(model):
    query = model.model_validate({"class": "10A"})
    assert query.class_name == "10A"
    assert query.limit == 10
    assert query.page == 1
    assert query.model_dump(by_alias=True)["class"] == "10A"
    with pytest.raises(ValidationError):
        model(limit=101)
    with pytest.raises(ValidationError):
        model(page=0)


def test_scan_query_preserves_default_limit_and_date_validation():
    assert ScanListQuery().limit == 30
    with pytest.raises(ValidationError, match="date_to is earlier than date_from"):
        ScanListQuery(date_from="2026-07-11", date_to="2026-07-10")
    assert ScanCreateRequest(nisn=1234567890).nisn == "1234567890"


def test_response_bases_preserve_orm_support():
    class_ = SimpleNamespace(class_id=1, class_name="10A", grade=10)
    assert ClassResponse.model_validate(class_).model_dump() == vars(class_)
    student = SimpleNamespace(
        id=2, name="Shaun", nisn="1234567890", current=True, class_id=1
    )
    assert StudentResponse.model_validate(student).model_dump() == {
        **vars(student),
        "class_name": None,
        "photo_path": None,
    }


def test_student_write_stays_required_while_bulk_fields_allow_missing_values():
    with pytest.raises(ValidationError):
        StudentWriteRequest()
    assert StudentBulkCreateRequest().model_dump() == {
        "nisn": None,
        "name": None,
        "class_id": None,
        "current": None,
    }
    assert StudentBulkUpdateRequest().id is None
    with pytest.raises(ValidationError):
        StudentBulkCreateRequest(nisn="short")


def test_bulk_response_preserves_nested_fields_and_failure_default():
    result = StudentBulkResponse.model_validate(
        {
            "succeeded": [
                {
                    "index": 0,
                    "item": {
                        "id": 1,
                        "nisn": "1234567890",
                        "name": "Shaun",
                        "current": True,
                    },
                }
            ],
            "failed": [{"index": 1, "error": "missing fields", "item": {}}],
        }
    ).model_dump()
    assert result == {
        "succeeded": [
            {
                "index": 0,
                "item": {
                    "id": 1,
                    "nisn": "1234567890",
                    "name": "Shaun",
                    "current": True,
                    "class_id": None,
                    "class_name": None,
                    "photo_path": None,
                },
            }
        ],
        "failed": [
            {
                "index": 1,
                "error": "missing fields",
                "item": {"nisn": None, "name": None, "class_id": None, "current": True},
            }
        ],
    }

# """
# POST /students/bulk
#     body: {"items": [StudentRequest, ...]}
#     -> 201 {"succeeded": [{"index": int, "data": StudentResponse}, ...],
#             "failed": []}

# PUT /students/bulk
#     body: {"items": [{"id": int, **StudentRequest fields}, ...]}
#     -> 200 {"succeeded": [{"index": int, "data": StudentResponse}, ...],
#             "failed": []}

# POST /students/bulk-delete
#     body: {"ids": [int, ...]}
#     -> 200 {"deleted_ids": [int, ...]}   (all-or-nothing)
# These tests assume `client` and `db_session` fixtures already exist in
# conftest.py (per your rollback-per-test setup) and that a `class_factory`
# / `student_factory` fixture exists for seeding rows directly via the ORM
# -- adjust the fixture names below if yours differ.
# """

# import pytest


# # ---------------------------------------------------------------------------
# # Bulk create — /students/bulk
# # ---------------------------------------------------------------------------


# def test_bulk_create_students_teacher_pastes_a_new_class_roster(client):
#     """The core spreadsheet-paste use case: a teacher pastes N new students
#     at once, all valid, none overlapping with existing data."""
#     payload = {
#         "items": [
#             {"name": "Shaun", "nisn": "1000000001", "class_id": None, "current": True},
#             {"name": "Timmy", "nisn": "1000000002", "class_id": None, "current": True},
#             {"name": "Bitzer", "nisn": "1000000003", "class_id": None, "current": True},
#         ]
#     }

#     response = client.post("/students/bulk", json=payload)

#     assert response.status_code == 201
#     body = response.json()

#     assert body["failed"] == []
#     assert len(body["succeeded"]) == 3
#     # order and index alignment preserved -- important for a spreadsheet UI
#     # that needs to map response rows back to the rows the user pasted
#     for i, item in enumerate(body["succeeded"]):
#         assert item["index"] == i
#         assert item["data"]["nisn"] == payload["items"][i]["nisn"]
#         assert item["data"]["name"] == payload["items"][i]["name"]
#         assert "id" in item["data"]  # server-assigned id present


# def test_bulk_create_students_with_valid_class_id(client, class_factory):
#     """Teacher pastes students that are being assigned into an existing
#     class in the same batch."""
#     existing_class = class_factory(class_name="Flock A")

#     payload = {
#         "items": [
#             {
#                 "name": "Shirley",
#                 "nisn": "1000000010",
#                 "class_id": existing_class.class_id,
#                 "current": True,
#             },
#         ]
#     }

#     response = client.post("/students/bulk", json=payload)

#     assert response.status_code == 201
#     body = response.json()
#     assert body["succeeded"][0]["data"]["class_id"] == existing_class.class_id


# # ---------------------------------------------------------------------------
# # Bulk update — /students/bulk (PUT)
# # ---------------------------------------------------------------------------


# def test_bulk_update_students_teacher_reassigns_class_for_several_students(
#     client, student_factory, class_factory
# ):
#     """Common real workflow: mass-move students into a new class, e.g.
#     after a class merge or start-of-year reassignment."""
#     new_class = class_factory(class_name="Flock B")
#     s1 = student_factory(name="Shaun", nisn="2000000001")
#     s2 = student_factory(name="Timmy", nisn="2000000002")

#     payload = {
#         "items": [
#             {
#                 "id": s1.id,
#                 "name": s1.name,
#                 "nisn": s1.nisn,
#                 "class_id": new_class.class_id,
#                 "current": True,
#             },
#             {
#                 "id": s2.id,
#                 "name": s2.name,
#                 "nisn": s2.nisn,
#                 "class_id": new_class.class_id,
#                 "current": True,
#             },
#         ]
#     }

#     response = client.put("/students/bulk", json=payload)

#     assert response.status_code == 200
#     body = response.json()

#     assert body["failed"] == []
#     assert len(body["succeeded"]) == 2
#     assert all(
#         item["data"]["class_id"] == new_class.class_id for item in body["succeeded"]
#     )


# # ---------------------------------------------------------------------------
# # Bulk delete — /students/bulk-delete
# # ---------------------------------------------------------------------------


# def test_bulk_delete_students_teacher_removes_graduated_batch(client, student_factory):
#     """Teacher selects several rows in the spreadsheet UI and deletes them
#     together, e.g. clearing out a graduated cohort."""
#     s1 = student_factory(name="Shaun", nisn="3000000001")
#     s2 = student_factory(name="Timmy", nisn="3000000002")
#     s3 = student_factory(name="Bitzer", nisn="3000000003")

#     response = client.post("/students/bulk-delete", json={"ids": [s1.id, s2.id, s3.id]})

#     assert response.status_code == 200
#     body = response.json()
#     assert sorted(body["deleted_ids"]) == sorted([s1.id, s2.id, s3.id])

#     # actually gone
#     for sid in (s1.id, s2.id, s3.id):
#         assert client.get(f"/students?nisn={sid}").json() == []


# # ---------------------------------------------------------------------------
# # Same shape, /classes/bulk* -- classes have simpler payloads (just class_name)
# # ---------------------------------------------------------------------------


# def test_bulk_create_classes_teacher_sets_up_classes_for_new_year(client):
#     payload = {
#         "items": [
#             {"class_name": "Flock A"},
#             {"class_name": "Flock B"},
#             {"class_name": "Flock C"},
#         ]
#     }

#     response = client.post("/classes/bulk", json=payload)

#     assert response.status_code == 201
#     body = response.json()
#     assert body["failed"] == []
#     assert len(body["succeeded"]) == 3


# def test_bulk_delete_classes(client, class_factory):
#     c1 = class_factory(class_name="Flock A")
#     c2 = class_factory(class_name="Flock B")

#     response = client.post(
#         "/classes/bulk-delete", json={"ids": [c1.class_id, c2.class_id]}
#     )

#     assert response.status_code == 200
#     assert sorted(response.json()["deleted_ids"]) == sorted([c1.class_id, c2.class_id])

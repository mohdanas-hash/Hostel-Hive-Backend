import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"  # never hit Neon from tests
os.environ["STORAGE_DIR"] = "./.test_storage"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Role, User
from app.security import hash_password


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(name="Admin", email="admin@c.edu", password_hash=hash_password("secret1"), role=Role.central_admin))
    db.commit()
    db.close()
    with TestClient(app) as c:
        yield c


def login(c, email, pw):
    r = c.post("/auth/login", data={"username": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


def upload(c, headers, aid, doc, content, name="f.bin"):
    return c.put(f"/admissions/{aid}/documents/{doc}", headers=headers, files={"file": (name, content)})


def submit_admission(c, headers, aid):
    for doc, content in (("passport_photo", JPEG), ("fee_receipt", PDF), ("aadhaar", PNG), ("pan", JPEG)):
        assert upload(c, headers, aid, doc, content).status_code == 200
    r = c.post(f"/admissions/{aid}/submit", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "submitted"


def test_full_flow(client):
    admin = login(client, "admin@c.edu", "secret1")
    cid = client.post("/colleges", json={"name": "ABC", "city": "Bhopal"}, headers=admin).json()["id"]
    for name, cat in (("wifi", "hostel"), ("ac", "hostel"), ("ro_water", "mess"), ("late_night", "cafeteria")):
        assert client.post("/amenities", headers=admin, json={"name": name, "category": cat}).status_code == 201
    base = dict(college_id=cid, gender="boys")
    bad = client.post("/hostels", headers=admin, json={**base, "name": "X", "location": "on_campus",
                      "monthly_rent": 1, "amenities": ["ro_water"]})
    assert bad.status_code == 422  # mess amenity on a hostel
    h1 = client.post("/hostels", headers=admin, json={**base, "name": "On", "location": "on_campus",
                     "monthly_rent": 4000, "available_beds": 2, "amenities": ["wifi"], "security_deposit": 2000}).json()["id"]
    h2 = client.post("/hostels", headers=admin, json={**base, "name": "Off", "location": "off_campus",
                     "monthly_rent": 3000, "amenities": ["wifi", "ac"]}).json()["id"]
    m = client.post("/messes", headers=admin, json={"college_id": cid, "name": "M", "location": "off_campus",
                    "monthly_price": 2500}).json()["id"]

    cafe = dict(college_id=cid, location="off_campus", food_type="veg")
    c1 = client.post("/cafeterias", headers=admin, json={**cafe, "name": "Chai Point", "avg_meal_price": 80,
                     "opens_at": "08:00", "closes_at": "23:00", "amenities": ["late_night"]}).json()["id"]
    c2 = client.post("/cafeterias", headers=admin, json={**cafe, "name": "Campus Cafe", "avg_meal_price": 120,
                     "location": "on_campus"}).json()["id"]
    assert client.post("/cafeterias", headers=admin, json={**cafe, "name": "Bad", "avg_meal_price": 1,
                       "opens_at": "25:99"}).status_code == 422
    assert client.post("/cafeterias", headers=admin, json={**cafe, "name": "Bad", "avg_meal_price": 1,
                       "amenities": ["wifi"]}).status_code == 422  # hostel amenity on cafeteria
    cc = client.get(f"/compare/cafeterias?ids={c1},{c2}").json()
    assert cc["cheapest_id"] == c1
    assert [c["id"] for c in client.get("/cafeterias?amenity=late_night").json()] == [c1]
    assert client.post("/reviews", headers=admin, json={"target_type": "cafeteria", "target_id": c1,
                                                        "rating": 4}).status_code == 201
    assert client.get(f"/cafeterias/{c1}").json()["avg_rating"] == 4
    assert client.post("/posts", headers=admin, json={"college_id": cid, "kind": "cafeteria_menu",
                       "cafeteria_id": c1, "title": "Snacks today"}).status_code == 201

    cmp = client.get(f"/compare/hostels?ids={h1},{h2}").json()
    assert cmp["cheapest_id"] == h2
    assert cmp["amenity_matrix"][str(h2)] == {"ac": True, "wifi": True}
    assert [h["id"] for h in client.get("/hostels?amenity=ac").json()] == [h2]
    prices = client.get(f"/compare/prices/{cid}").json()
    assert prices["hostel"]["off_campus_vs_on_campus_avg"] == -1000
    assert prices["cafeteria"]["off_campus_vs_on_campus_avg"] == -40

    # student cannot post / create listings
    s = client.post("/auth/register", json={"name": "S", "email": "s@x.com", "password": "secret1"}).json()
    stu = {"Authorization": f"Bearer {s['access_token']}"}
    assert client.post("/posts", headers=stu, json={"college_id": cid, "kind": "notice", "title": "x"}).status_code == 403
    assert client.post("/auth/register", json={"name": "X", "email": "x@x.com", "password": "secret1",
                                               "role": "central_admin"}).status_code == 403

    # admin posts daily update
    assert client.post("/posts", headers=admin, json={"college_id": cid, "kind": "mess_menu", "mess_id": m,
                                                      "title": "Menu"}).status_code == 201
    assert len(client.get("/posts/today").json()) == 2

    # payment is blocked until hostel admission documents are submitted
    blocked = client.post("/payments", headers=stu, json={"kind": "hostel_rent", "hostel_id": h1})
    assert blocked.status_code == 403
    adm = client.post("/admissions", headers=stu, json={"hostel_id": h1}).json()
    assert client.post("/payments", headers=stu, json={"kind": "hostel_rent", "hostel_id": h1}).status_code == 403
    submit_admission(client, stu, adm["id"])

    # payment: amount computed server-side
    p = client.post("/payments", headers=stu, json={"kind": "hostel_rent", "hostel_id": h1, "months": 3,
                                                    "include_deposit": True}).json()
    assert p["amount"] == 14000  # 3 x 4000 rent + 2000 deposit
    done = client.post(f"/payments/{p['id']}/confirm", headers=stu, json={"provider_payment_id": "pay_1"}).json()
    assert done["status"] == "paid"
    assert client.get(f"/hostels/{h1}").json()["available_beds"] == 1

    # renewal does not take a second bed
    p2 = client.post("/payments", headers=stu, json={"kind": "hostel_rent", "hostel_id": h1}).json()
    client.post(f"/payments/{p2['id']}/confirm", headers=stu, json={"provider_payment_id": "pay_2"})
    assert client.get(f"/hostels/{h1}").json()["available_beds"] == 1


def test_only_one_admin(client):
    from sqlalchemy.exc import IntegrityError
    db = SessionLocal()
    db.add(User(name="Second", email="b@c.edu", password_hash="x", role=Role.central_admin))
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


def test_admission_rules(client):
    admin = login(client, "admin@c.edu", "secret1")
    cid = client.post("/colleges", json={"name": "ABC", "city": "B"}, headers=admin).json()["id"]
    hid = client.post("/hostels", headers=admin, json={"college_id": cid, "name": "H", "location": "on_campus",
                      "monthly_rent": 1000, "available_beds": 1}).json()["id"]
    full = client.post("/hostels", headers=admin, json={"college_id": cid, "name": "Full", "location": "on_campus",
                       "monthly_rent": 1000, "available_beds": 0}).json()["id"]

    def reg(email):
        t = client.post("/auth/register", json={"name": "S", "email": email, "password": "secret1"}).json()
        return {"Authorization": f"Bearer {t['access_token']}"}
    s1, s2 = reg("a@x.com"), reg("b@x.com")

    assert client.post("/admissions", headers=s1, json={"hostel_id": full}).status_code == 409
    a = client.post("/admissions", headers=s1, json={"hostel_id": hid}).json()
    assert client.post("/admissions", headers=s1, json={"hostel_id": hid}).json()["id"] == a["id"]  # idempotent
    assert len(a["missing_documents"]) == 4

    # submit needs all docs
    assert client.post(f"/admissions/{a['id']}/submit", headers=s1).status_code == 409
    # content validation: sniffed bytes, not extension; passport photo can't be a PDF
    assert upload(client, s1, a["id"], "aadhaar", b"not a real file", "aadhaar.jpg").status_code == 422
    assert upload(client, s1, a["id"], "passport_photo", PDF).status_code == 422
    assert upload(client, s1, a["id"], "pan", b"").status_code == 422
    assert upload(client, s1, a["id"], "pan", JPEG).status_code == 200
    assert upload(client, s1, a["id"], "pan", PNG).status_code == 200  # replace

    # other student / anonymous cannot see or download documents
    assert client.get(f"/admissions/{a['id']}", headers=s2).status_code == 404
    assert client.get(f"/admissions/{a['id']}/documents/pan", headers=s2).status_code == 404
    assert client.get(f"/admissions/{a['id']}/documents/pan").status_code == 401
    assert client.get(f"/admissions/{a['id']}/documents/pan", headers=s1).content == PNG
    assert client.get(f"/admissions/{a['id']}/documents/pan", headers=admin).status_code == 200

    for doc, content in (("passport_photo", JPEG), ("fee_receipt", PDF), ("aadhaar", PNG)):
        upload(client, s1, a["id"], doc, content)
    assert client.post(f"/admissions/{a['id']}/submit", headers=s1).status_code == 200
    # locked after submit
    assert upload(client, s1, a["id"], "pan", JPEG).status_code == 409

    # admin rejects -> student fixes and resubmits; payment blocked while rejected
    assert client.post(f"/admissions/{a['id']}/review", headers=s1, json={"approve": True}).status_code == 403
    assert client.post(f"/admissions/{a['id']}/review", headers=admin, json={"approve": False}).status_code == 422
    r = client.post(f"/admissions/{a['id']}/review", headers=admin, json={"approve": False, "reason": "Blurry PAN"})
    assert r.json()["status"] == "rejected"
    assert client.post("/payments", headers=s1, json={"kind": "hostel_rent", "hostel_id": hid}).status_code == 403
    assert upload(client, s1, a["id"], "pan", JPEG).status_code == 200
    assert client.post(f"/admissions/{a['id']}/submit", headers=s1).status_code == 200
    assert client.post(f"/admissions/{a['id']}/review", headers=admin, json={"approve": True}).json()["status"] == "approved"
    pay = client.post("/payments", headers=s1, json={"kind": "hostel_rent", "hostel_id": hid})
    assert pay.status_code == 201 and pay.json()["application_id"] == a["id"]

    # other student has no admission -> cannot pay for this hostel
    assert client.post("/payments", headers=s2, json={"kind": "hostel_rent", "hostel_id": hid}).status_code == 403
    assert [x["id"] for x in client.get("/admissions", headers=admin).json()] == [a["id"]]
    assert client.get("/admissions", headers=s2).json() == []

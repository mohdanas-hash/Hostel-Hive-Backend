"""Comparison endpoints — the core of the site.

Main focus: off-campus hostels/messes (outside college) vs the college's own.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Cafeteria, College, Hostel, Location, Mess
from ..schemas import CafeteriaOut, HostelOut, MessOut
from .listings import with_ratings

router = APIRouter(prefix="/compare", tags=["compare"])


def parse_ids(ids: str) -> list[int]:
    try:
        parsed = list(dict.fromkeys(int(i) for i in ids.split(",") if i.strip()))
    except ValueError:
        raise HTTPException(422, "ids must be comma separated integers, e.g. 1,2,3")
    if not 2 <= len(parsed) <= 6:
        raise HTTPException(422, "Pick between 2 and 6 items to compare")
    return parsed


def stats(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"count": len(values), "min": min(values), "max": max(values),
            "avg": round(sum(values) / len(values), 2)}


@router.get("/hostels")
def compare_hostels(ids: str = Query(..., examples=["1,2,3"]), db: Session = Depends(get_db)):
    id_list = parse_ids(ids)
    rows = db.scalars(select(Hostel).where(Hostel.id.in_(id_list), Hostel.is_active)).all()
    if len(rows) != len(id_list):
        raise HTTPException(404, "One or more hostels not found")
    items = with_ratings(db, rows, "hostel", HostelOut)
    all_amenities = sorted({f for i in items for f in i.amenities})
    return {
        "items": items,
        "cheapest_id": min(items, key=lambda i: i.monthly_rent).id,
        "closest_id": min(items, key=lambda i: i.distance_from_college_km).id,
        "amenity_matrix": {i.id: {f: f in i.amenities for f in all_amenities} for i in items},
    }


@router.get("/messes")
def compare_messes(ids: str = Query(..., examples=["1,2,3"]), db: Session = Depends(get_db)):
    id_list = parse_ids(ids)
    rows = db.scalars(select(Mess).where(Mess.id.in_(id_list), Mess.is_active)).all()
    if len(rows) != len(id_list):
        raise HTTPException(404, "One or more messes not found")
    items = with_ratings(db, rows, "mess", MessOut)
    all_amenities = sorted({f for i in items for f in i.amenities})
    rated = [i for i in items if i.hygiene_rating is not None]
    return {
        "items": items,
        "cheapest_id": min(items, key=lambda i: i.monthly_price).id,
        "best_hygiene_id": max(rated, key=lambda i: i.hygiene_rating).id if rated else None,
        "amenity_matrix": {i.id: {f: f in i.amenities for f in all_amenities} for i in items},
    }


@router.get("/cafeterias")
def compare_cafeterias(ids: str = Query(..., examples=["1,2,3"]), db: Session = Depends(get_db)):
    id_list = parse_ids(ids)
    rows = db.scalars(select(Cafeteria).where(Cafeteria.id.in_(id_list), Cafeteria.is_active)).all()
    if len(rows) != len(id_list):
        raise HTTPException(404, "One or more cafeterias not found")
    items = with_ratings(db, rows, "cafeteria", CafeteriaOut)
    all_amenities = sorted({f for i in items for f in i.amenities})
    rated = [i for i in items if i.hygiene_rating is not None]
    return {
        "items": items,
        "cheapest_id": min(items, key=lambda i: i.avg_meal_price).id,
        "closest_id": min(items, key=lambda i: i.distance_from_college_km).id,
        "best_hygiene_id": max(rated, key=lambda i: i.hygiene_rating).id if rated else None,
        "amenity_matrix": {i.id: {f: f in i.amenities for f in all_amenities} for i in items},
    }


@router.get("/colleges")
def compare_colleges(ids: str = Query(..., examples=["1,2,3"]), db: Session = Depends(get_db)):
    """Side-by-side infrastructure + price summary for multiple colleges."""
    id_list = parse_ids(ids)
    colleges = db.scalars(select(College).where(College.id.in_(id_list))).all()
    if len(colleges) != len(id_list):
        raise HTTPException(404, "One or more colleges not found")
    result = []
    for c in colleges:
        hostels = db.scalars(select(Hostel).where(Hostel.college_id == c.id, Hostel.is_active)).all()
        messes = db.scalars(select(Mess).where(Mess.college_id == c.id, Mess.is_active)).all()
        cafes = db.scalars(select(Cafeteria).where(Cafeteria.college_id == c.id, Cafeteria.is_active)).all()
        entry = {"college_id": c.id, "name": c.name, "city": c.city}
        for loc in Location:
            hs = [h for h in hostels if h.location == loc]
            ms = [m for m in messes if m.location == loc]
            cs = [x for x in cafes if x.location == loc]
            entry[loc.value] = {
                "hostel_rent": stats([h.monthly_rent for h in hs]),
                "mess_price": stats([m.monthly_price for m in ms]),
                "cafeteria_meal_price": stats([x.avg_meal_price for x in cs]),
                "cafeteria_amenities": sorted({f for x in cs for f in x.amenities}),
                "available_beds": sum(h.available_beds for h in hs),
                "hostel_amenities": sorted({f for h in hs for f in h.amenities}),
                "mess_amenities": sorted({f for m in ms for f in m.amenities}),
            }
        result.append(entry)
    return result


@router.get("/prices/{college_id}")
def college_prices(college_id: int, db: Session = Depends(get_db)):
    """Main college vs outside: on-campus price vs off-campus options around that college."""
    college = db.get(College, college_id)
    if not college:
        raise HTTPException(404, "College not found")
    out = {"college": {"id": college.id, "name": college.name, "city": college.city}}
    for label, model, col in (("hostel", Hostel, Hostel.monthly_rent), ("mess", Mess, Mess.monthly_price),
                              ("cafeteria", Cafeteria, Cafeteria.avg_meal_price)):
        sections = {}
        for loc in Location:
            items = db.scalars(select(model).where(model.college_id == college_id,
                                                   model.location == loc, model.is_active)
                               .order_by(col)).all()
            sections[loc.value] = {
                "summary": stats([getattr(i, col.key) for i in items]),
                "items": [{"id": i.id, "name": i.name, "price": getattr(i, col.key),
                           "distance_km": i.distance_from_college_km} for i in items],
            }
        on, off = sections["on_campus"]["summary"], sections["off_campus"]["summary"]
        sections["off_campus_vs_on_campus_avg"] = (
            round(off["avg"] - on["avg"], 2) if on and off else None)  # negative => outside is cheaper
        out[label] = sections
    return out


@router.get("/city-overview")
def city_overview(city: str, db: Session = Depends(get_db)):
    """Average prices in a city, split on-campus vs off-campus, per college."""
    rows = db.execute(
        select(College.id, College.name, Hostel.location, func.avg(Hostel.monthly_rent), func.count(Hostel.id))
        .join(Hostel, Hostel.college_id == College.id)
        .where(College.city.ilike(city), Hostel.is_active)
        .group_by(College.id, College.name, Hostel.location)
    ).all()
    mrows = db.execute(
        select(College.id, Mess.location, func.avg(Mess.monthly_price))
        .join(Mess, Mess.college_id == College.id)
        .where(College.city.ilike(city), Mess.is_active)
        .group_by(College.id, Mess.location)
    ).all()
    mess_avg = {(cid, loc): round(float(a), 2) for cid, loc, a in mrows}
    crows = db.execute(
        select(College.id, Cafeteria.location, func.avg(Cafeteria.avg_meal_price))
        .join(Cafeteria, Cafeteria.college_id == College.id)
        .where(College.city.ilike(city), Cafeteria.is_active)
        .group_by(College.id, Cafeteria.location)
    ).all()
    cafe_avg = {(cid, loc): round(float(a), 2) for cid, loc, a in crows}
    data: dict[int, dict] = {}
    for cid, name, loc, avg, n in rows:
        d = data.setdefault(cid, {"college_id": cid, "name": name})
        d[loc.value] = {"hostel_avg_rent": round(float(avg), 2), "hostels": n,
                        "mess_avg_price": mess_avg.get((cid, loc)),
                        "cafeteria_avg_meal_price": cafe_avg.get((cid, loc))}
    return {"city": city, "colleges": list(data.values())}

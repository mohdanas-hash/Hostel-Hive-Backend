# Hostel Hive Backend (FastAPI)

Full docs (API, DB schema, flows): [DOCUMENTATION.md](DOCUMENTATION.md)

Colleges ke hostel/mess ka comparison, off-campus (college ke bahar) vs on-campus prices, daily posts by central college, aur student payments.

## Setup (Neon + Drizzle)
1. Neon dashboard se connection string copy karo aur `.env` mein `DATABASE_URL=` ke aage paste karo (`.env.example` dekho). `ADMIN_EMAIL` / `ADMIN_PASSWORD` bhi set karo.
2. Schema/migrations Drizzle se: 
   ```
   npm install
   npm run db:migrate          # drizzle/migrations ko Neon par apply karta hai
   ```
3. API:
   ```
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/uvicorn app.main:app --reload     # /docs ; single admin pehli startup par ban jata hai
   .venv/bin/python seed.py                    # optional sample data
   .venv/bin/pytest                            # SQLite use karta hai, Neon ko touch nahi karta
   ```

### Schema badalna (IMPORTANT — do jagah update karni hai)
Schema ka source of truth [drizzle/schema.ts](drizzle/schema.ts) hai, aur [app/models.py](app/models.py) usko mirror karta hai (FastAPI SQLAlchemy se query karta hai). Kuch badalna ho to dono edit karo, phir `npm run db:generate` (naya SQL banata hai) aur `npm run db:migrate`.

## Roles
- **visitor / student**: browse, compare, review; student rent/mess fee pay karta hai.
- **central_admin**: sirf **ek**. DB unique index (`one_central_admin`) se enforce hota hai, public signup se nahi ban sakta. Colleges, hostels, messes, amenities aur daily posts yahi manage karta hai.

## Amenities
Admin catalog banata hai (`POST /amenities`, category `hostel`, `mess` ya `cafeteria`), phir hostel/mess create karte waqt `"amenities": ["wifi","ac"]` bhejta hai (unknown naam par 422). Filter: `GET /hostels?amenity=wifi&amenity=ac`. Compare responses mein `amenity_matrix` aata hai.

## Hostel admission (documents -> payment)
Rent payment tabhi khulta hai jab student ki admission application `submitted` ho:
1. `POST /admissions {hostel_id}` -> application banta hai (beds available hone chahiye)
2. `PUT /admissions/{id}/documents/{doc_type}` (multipart `file`) — `passport_photo`, `fee_receipt`, `aadhaar`, `pan`. JPEG/PNG/PDF (photo: sirf image), max 5 MB; file type content se check hota hai, extension se nahi. Dobara upload = replace.
3. `POST /admissions/{id}/submit` — chaaron documents ke baad hi (warna 409 + `missing` list)
4. `POST /payments` (`hostel_rent`) — admission ke bina 403
5. Admin: `GET /admissions?status=submitted`, documents dekhna `GET /admissions/{id}/documents/{doc_type}`, `POST /admissions/{id}/review {approve, reason}`. Reject hone par student dobara upload karke resubmit karta hai, aur tab tak payment blocked rehta hai.

Documents sirf owner student aur admin dekh sakte hain (public URL nahi). Files `STORAGE_DIR` (default `./storage`) mein hoti hain, DB mein sirf metadata. Hosting par disk ephemeral ho to is folder ko persistent volume par rakho ya [app/storage.py](app/storage.py) ko S3/R2 se replace karo.

## Key endpoints
| | |
|---|---|
| `POST /auth/register`, `/auth/login`, `GET /auth/me` | auth (JWT) |
| `GET /hostels`, `/messes` | filters: city, college_id, location=on_campus/off_campus, price range, amenity, sort |
| `GET /cafeterias` (+ POST/PUT/DELETE admin) | cafeteria: avg meal price, opening hours, home delivery, amenities; same filters |
| `GET/POST/DELETE /amenities` | amenity catalog (write = admin) |
| `GET /compare/hostels?ids=1,2,3` · `/compare/messes?ids=` · `/compare/cafeterias?ids=` · `/compare/colleges?ids=` | side-by-side |
| `GET /compare/prices/{college_id}` | **main**: on-campus vs off-campus prices around a college |
| `GET /compare/city-overview?city=Bhopal` | avg prices per college, on/off campus |
| `GET /posts`, `/posts/today`; `POST /posts` (central admin) | daily feed |
| `POST /payments` → `POST /payments/{id}/confirm`; `GET /payments` | `kind=hostel_rent` (months, optional `include_deposit`) ya `mess_fee`; amount server-side |

## Payments
Mock gateway by default ([app/payments.py](app/payments.py)). Real Razorpay/Stripe ke liye `PaymentGateway` implement karo aur confirm ko signature-verified webhook se replace karo, warna koi bhi user apna payment "paid" mark kar sakta hai.

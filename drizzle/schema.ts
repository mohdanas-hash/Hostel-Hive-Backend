// Source of truth for the DB schema. Must mirror app/models.py (SQLAlchemy) column-for-column.
import { sql } from "drizzle-orm";
import {
  boolean, date, doublePrecision, index, integer, pgTable, primaryKey, text, timestamp,
  unique, uniqueIndex, varchar,
} from "drizzle-orm/pg-core";

const id = () => integer("id").primaryKey().generatedByDefaultAsIdentity();
const createdAt = () => timestamp("created_at", { withTimezone: true }).notNull().defaultNow();

export const users = pgTable("users", {
  id: id(),
  name: varchar("name", { length: 120 }).notNull(),
  email: varchar("email", { length: 255 }).notNull(),
  passwordHash: varchar("password_hash", { length: 255 }).notNull(),
  role: varchar("role", { length: 30, enum: ["visitor", "student", "central_admin"] }).notNull().default("student"),
  collegeId: integer("college_id").references(() => colleges.id),
  createdAt: createdAt(),
}, (t) => [
  uniqueIndex("ix_users_email").on(t.email),
  // At most ONE central admin.
  uniqueIndex("one_central_admin").on(t.role).where(sql`${t.role} = 'central_admin'`),
]);

export const colleges = pgTable("colleges", {
  id: id(),
  name: varchar("name", { length: 200 }).notNull().unique(),
  city: varchar("city", { length: 100 }).notNull(),
  address: varchar("address", { length: 300 }).notNull().default(""),
  isCentral: boolean("is_central").notNull().default(false),
}, (t) => [index("ix_colleges_city").on(t.city)]);

export const amenities = pgTable("amenities", {
  id: id(),
  name: varchar("name", { length: 60 }).notNull().unique(),
  category: varchar("category", { length: 10, enum: ["hostel", "mess", "cafeteria"] }).notNull(),
}, (t) => [index("ix_amenities_category").on(t.category)]);

const location = () => varchar("location", { length: 30, enum: ["on_campus", "off_campus"] }).notNull();

export const hostels = pgTable("hostels", {
  id: id(),
  collegeId: integer("college_id").notNull().references(() => colleges.id),
  name: varchar("name", { length: 200 }).notNull(),
  location: location(),
  gender: varchar("gender", { length: 30, enum: ["boys", "girls", "co_ed"] }).notNull().default("co_ed"),
  address: varchar("address", { length: 300 }).notNull().default(""),
  distanceFromCollegeKm: doublePrecision("distance_from_college_km").notNull().default(0),
  monthlyRent: doublePrecision("monthly_rent").notNull(),
  securityDeposit: doublePrecision("security_deposit").notNull().default(0),
  roomType: varchar("room_type", { length: 50 }).notNull().default("double"),
  totalBeds: integer("total_beds").notNull().default(0),
  availableBeds: integer("available_beds").notNull().default(0),
  wifiMbps: integer("wifi_mbps"),
  hasAc: boolean("has_ac").notNull().default(false),
  attachedBathroom: boolean("attached_bathroom").notNull().default(false),
  powerBackup: boolean("power_backup").notNull().default(false),
  cctv: boolean("cctv").notNull().default(false),
  includesMess: boolean("includes_mess").notNull().default(false),
  isActive: boolean("is_active").notNull().default(true),
}, (t) => [
  index("ix_hostels_college_id").on(t.collegeId),
  index("ix_hostels_location").on(t.location),
]);

export const messes = pgTable("messes", {
  id: id(),
  collegeId: integer("college_id").notNull().references(() => colleges.id),
  name: varchar("name", { length: 200 }).notNull(),
  location: location(),
  address: varchar("address", { length: 300 }).notNull().default(""),
  distanceFromCollegeKm: doublePrecision("distance_from_college_km").notNull().default(0),
  foodType: varchar("food_type", { length: 30, enum: ["veg", "non_veg", "both"] }).notNull().default("both"),
  monthlyPrice: doublePrecision("monthly_price").notNull(),
  pricePerMeal: doublePrecision("price_per_meal"),
  mealsPerDay: integer("meals_per_day").notNull().default(2),
  hygieneRating: doublePrecision("hygiene_rating"),
  seatingCapacity: integer("seating_capacity"),
  isActive: boolean("is_active").notNull().default(true),
}, (t) => [
  index("ix_messes_college_id").on(t.collegeId),
  index("ix_messes_location").on(t.location),
]);

export const cafeterias = pgTable("cafeterias", {
  id: id(),
  collegeId: integer("college_id").notNull().references(() => colleges.id),
  name: varchar("name", { length: 200 }).notNull(),
  location: location(),
  address: varchar("address", { length: 300 }).notNull().default(""),
  distanceFromCollegeKm: doublePrecision("distance_from_college_km").notNull().default(0),
  foodType: varchar("food_type", { length: 30, enum: ["veg", "non_veg", "both"] }).notNull().default("both"),
  cuisine: varchar("cuisine", { length: 100 }).notNull().default(""),
  avgMealPrice: doublePrecision("avg_meal_price").notNull(),
  minItemPrice: doublePrecision("min_item_price"),
  opensAt: varchar("opens_at", { length: 5 }),
  closesAt: varchar("closes_at", { length: 5 }),
  hygieneRating: doublePrecision("hygiene_rating"),
  seatingCapacity: integer("seating_capacity"),
  homeDelivery: boolean("home_delivery").notNull().default(false),
  isActive: boolean("is_active").notNull().default(true),
}, (t) => [
  index("ix_cafeterias_college_id").on(t.collegeId),
  index("ix_cafeterias_location").on(t.location),
]);

export const cafeteriaAmenities = pgTable("cafeteria_amenities", {
  cafeteriaId: integer("cafeteria_id").notNull().references(() => cafeterias.id, { onDelete: "cascade" }),
  amenityId: integer("amenity_id").notNull().references(() => amenities.id, { onDelete: "cascade" }),
}, (t) => [primaryKey({ columns: [t.cafeteriaId, t.amenityId] })]);

export const hostelAmenities = pgTable("hostel_amenities", {
  hostelId: integer("hostel_id").notNull().references(() => hostels.id, { onDelete: "cascade" }),
  amenityId: integer("amenity_id").notNull().references(() => amenities.id, { onDelete: "cascade" }),
}, (t) => [primaryKey({ columns: [t.hostelId, t.amenityId] })]);

export const messAmenities = pgTable("mess_amenities", {
  messId: integer("mess_id").notNull().references(() => messes.id, { onDelete: "cascade" }),
  amenityId: integer("amenity_id").notNull().references(() => amenities.id, { onDelete: "cascade" }),
}, (t) => [primaryKey({ columns: [t.messId, t.amenityId] })]);

export const dailyPosts = pgTable("daily_posts", {
  id: id(),
  authorId: integer("author_id").notNull().references(() => users.id),
  collegeId: integer("college_id").notNull().references(() => colleges.id),
  kind: varchar("kind", { length: 30, enum: ["mess_menu", "cafeteria_menu", "hostel_update", "notice"] }).notNull(),
  messId: integer("mess_id").references(() => messes.id),
  hostelId: integer("hostel_id").references(() => hostels.id),
  cafeteriaId: integer("cafeteria_id").references(() => cafeterias.id),
  title: varchar("title", { length: 200 }).notNull(),
  body: text("body").notNull().default(""),
  postDate: date("post_date", { mode: "string" }).notNull(),
  createdAt: createdAt(),
}, (t) => [
  index("ix_daily_posts_college_id").on(t.collegeId),
  index("ix_daily_posts_kind").on(t.kind),
  index("ix_daily_posts_post_date").on(t.postDate),
]);

export const reviews = pgTable("reviews", {
  id: id(),
  userId: integer("user_id").notNull().references(() => users.id),
  targetType: varchar("target_type", { length: 10, enum: ["hostel", "mess", "cafeteria"] }).notNull(),
  targetId: integer("target_id").notNull(),
  rating: integer("rating").notNull(),
  comment: text("comment").notNull().default(""),
  createdAt: createdAt(),
}, (t) => [index("ix_reviews_target_id").on(t.targetId)]);

export const admissionApplications = pgTable("admission_applications", {
  id: id(),
  userId: integer("user_id").notNull().references(() => users.id),
  hostelId: integer("hostel_id").notNull().references(() => hostels.id),
  status: varchar("status", { length: 30, enum: ["draft", "submitted", "approved", "rejected"] }).notNull().default("draft"),
  rejectReason: text("reject_reason"),
  createdAt: createdAt(),
  submittedAt: timestamp("submitted_at", { withTimezone: true }),
  reviewedAt: timestamp("reviewed_at", { withTimezone: true }),
}, (t) => [
  index("ix_admission_applications_user_id").on(t.userId),
  index("ix_admission_applications_hostel_id").on(t.hostelId),
  unique("uq_admission_user_hostel").on(t.userId, t.hostelId),
]);

export const admissionDocuments = pgTable("admission_documents", {
  id: id(),
  applicationId: integer("application_id").notNull().references(() => admissionApplications.id, { onDelete: "cascade" }),
  docType: varchar("doc_type", { length: 30, enum: ["passport_photo", "fee_receipt", "aadhaar", "pan"] }).notNull(),
  storageKey: varchar("storage_key", { length: 100 }).notNull(),
  originalName: varchar("original_name", { length: 255 }).notNull(),
  contentType: varchar("content_type", { length: 50 }).notNull(),
  sizeBytes: integer("size_bytes").notNull(),
  uploadedAt: timestamp("uploaded_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("ix_admission_documents_application_id").on(t.applicationId),
  unique("uq_admission_doc_type").on(t.applicationId, t.docType),
]);

export const payments = pgTable("payments", {
  id: id(),
  userId: integer("user_id").notNull().references(() => users.id),
  kind: varchar("kind", { length: 30, enum: ["hostel_rent", "mess_fee"] }).notNull(),
  hostelId: integer("hostel_id").references(() => hostels.id),
  messId: integer("mess_id").references(() => messes.id),
  applicationId: integer("application_id").references(() => admissionApplications.id),
  months: integer("months").notNull().default(1),
  includeDeposit: boolean("include_deposit").notNull().default(false),
  amount: doublePrecision("amount").notNull(),
  currency: varchar("currency", { length: 3 }).notNull().default("INR"),
  status: varchar("status", { length: 30, enum: ["created", "paid", "failed"] }).notNull().default("created"),
  provider: varchar("provider", { length: 30 }).notNull().default("mock"),
  providerOrderId: varchar("provider_order_id", { length: 100 }).notNull().default(""),
  providerPaymentId: varchar("provider_payment_id", { length: 100 }),
  createdAt: createdAt(),
  paidAt: timestamp("paid_at", { withTimezone: true }),
}, (t) => [index("ix_payments_user_id").on(t.userId)]);

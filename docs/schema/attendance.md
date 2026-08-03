# Schema: Attendance

## Summary
Attendance tracking via QR scans or manual marking. Use this doc when query involves attendance, present/absent, scan, QR, daily attendance.

---

## studentattendances

Student attendance records.

```js
{
  _id: ObjectId,
  enrollmentId: ObjectId,          // ref: "StudentTrackEnrollment"
  studentId: ObjectId,             // ref: "User"
  trackSessionConfigId: ObjectId,  // ref: "TrackSessionConfig"
  trackId: ObjectId,               // ref: "Track"
  sessionId: ObjectId,             // ref: "AcademicYear"
  dateKey: String,                 // format: "YYYY-MM-DD"
  attendanceSession: String,       // "MORNING" | "EVENING"
  status: String,                  // "PRESENT" | "ABSENT"
  markedByMentorId: ObjectId,      // ref: "User"
  markedAt: Date,
  source: String,                  // "MANUAL" | "QR_SCAN"
  evidence: {                      // embedded — scan evidence (nullable)
    attendanceScanSessionId: ObjectId,
    selfieUrl: String,
    scanTime: Date,
    device: {browser: String, os: String, deviceIdHash: String, userAgent: String},
    gps: {latitude: Number, longitude: Number, accuracyMeters: Number, capturedAt: Date},
    distanceFromMentorMeters: Number,
    confidence: String             // "HIGH" | "REVIEW" | "SUSPICIOUS"
  }
}
```

**Key index:** `{ enrollmentId: 1, dateKey: 1, attendanceSession: 1 }` — unique

---

## attendantscansessions

QR scan sessions started by a mentor.

```js
{
  _id: ObjectId,
  mentorId: ObjectId,              // ref: "User"
  trackId: ObjectId,               // ref: "Track"
  dateKey: String,                 // format: "YYYY-MM-DD"
  attendanceSession: String,       // "MORNING" | "EVENING"
  isActive: Boolean,
  startedAt: Date,
  endedAt: Date
}
```

---

## attendantscanevents

Individual student QR scan events.

```js
{
  _id: ObjectId,
  studentId: ObjectId,
  mentorId: ObjectId,
  dateKey: String,
  attendanceSession: String,
  decision: String,                // "SUCCESS" | "REJECTED"
  reviewStatus: String,            // "PENDING" | "APPROVED" | "REJECTED"
  rejectionReason: String,
  scanTime: Date,
  confidence: String               // "HIGH" | "REVIEW" | "SUSPICIOUS"
}
```

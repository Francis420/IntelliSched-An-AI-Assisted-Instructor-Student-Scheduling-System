from django.core.management.base import BaseCommand
from scheduling.models import Schedule, Semester
from datetime import datetime


class Command(BaseCommand):
    help = "Checks for conflicts among FINALIZED schedules in the active semester."

    def handle(self, *args, **options):
        # 🧠 Auto-detect active semester
        semester = Semester.objects.filter(isActive=True).order_by("-semesterId").first()

        if not semester:
            self.stdout.write("⚠️ No active semester found.")
            return

        self.stdout.write(f"\n📘 Active semester: {semester.name}\n")

        finalized = (
            Schedule.objects
            .filter(semester=semester, status="finalized")
            .select_related("room", "section", "instructor")
            .order_by("dayOfWeek", "startTime")
        )

        total = finalized.count()
        if total == 0:
            self.stdout.write("⚠️ No FINALIZED schedules found.\n")
            return

        self.stdout.write(f"🔍 Checking {total} FINALIZED schedule(s)...\n")

        room = self.check_room_conflicts(finalized)
        instr = self.check_instructor_conflicts(finalized)
        sect = self.check_section_conflicts(finalized)
        combo = self.check_combined_conflicts(finalized)

        if not any([room, instr, sect, combo]):
            self.stdout.write("\n✅ NO CONFLICTS FOUND IN FINALIZED SCHEDULES.\n")

    # --------------------------------------------------
    # ROOM conflicts
    # --------------------------------------------------
    def check_room_conflicts(self, schedules):
        found = False
        grouped = {}

        for s in schedules:
            if not s.room_id:
                continue
            grouped.setdefault((s.room_id, s.dayOfWeek), []).append(s)

        for (room_id, day), lst in grouped.items():
            lst.sort(key=lambda s: s.startTime)
            for i in range(len(lst) - 1):
                a, b = lst[i], lst[i + 1]
                if self._overlaps(a, b):
                    if not found:
                        self.stdout.write("⚠️ ROOM CONFLICTS:\n")
                        found = True
                    self.stdout.write(
                        f"  • Room {a.room.roomCode} on {day}: "
                        f"Section {a.section.sectionId} ({a.startTime}-{a.endTime}) "
                        f"↔ Section {b.section.sectionId} ({b.startTime}-{b.endTime})"
                    )

        if not found:
            self.stdout.write("✅ No room conflicts.\n")
        return found

    # --------------------------------------------------
    # INSTRUCTOR conflicts
    # --------------------------------------------------
    def check_instructor_conflicts(self, schedules):
        found = False
        grouped = {}

        for s in schedules:
            grouped.setdefault((s.instructor_id, s.dayOfWeek), []).append(s)

        for (instr, day), lst in grouped.items():
            lst.sort(key=lambda s: s.startTime)
            for i in range(len(lst) - 1):
                a, b = lst[i], lst[i + 1]
                if self._overlaps(a, b):
                    if not found:
                        self.stdout.write("⚠️ INSTRUCTOR CONFLICTS:\n")
                        found = True
                    self.stdout.write(
                        f"  • Instructor {a.instructor.instructorId} on {day}: "
                        f"{a.startTime}-{a.endTime} ↔ {b.startTime}-{b.endTime}"
                    )

        if not found:
            self.stdout.write("✅ No instructor conflicts.\n")
        return found

    # --------------------------------------------------
    # SECTION conflicts
    # --------------------------------------------------
    def check_section_conflicts(self, schedules):
        found = False
        grouped = {}

        for s in schedules:
            grouped.setdefault((s.section_id, s.dayOfWeek), []).append(s)

        for (sec, day), lst in grouped.items():
            lst.sort(key=lambda s: s.startTime)
            for i in range(len(lst) - 1):
                a, b = lst[i], lst[i + 1]
                if self._overlaps(a, b):
                    if not found:
                        self.stdout.write("⚠️ SECTION CONFLICTS:\n")
                        found = True
                    self.stdout.write(
                        f"  • Section {a.section.sectionId} on {day}: "
                        f"{a.startTime}-{a.endTime} ↔ {b.startTime}-{b.endTime}"
                    )

        if not found:
            self.stdout.write("✅ No section conflicts.\n")
        return found

    # --------------------------------------------------
    # COMBINED Room + Instructor conflicts
    # --------------------------------------------------
    def check_combined_conflicts(self, schedules):
        found = False
        grouped = {}

        for s in schedules:
            if not s.room_id:
                continue
            grouped.setdefault((s.instructor_id, s.room_id, s.dayOfWeek), []).append(s)

        for (instr, room, day), lst in grouped.items():
            lst.sort(key=lambda s: s.startTime)
            for i in range(len(lst) - 1):
                a, b = lst[i], lst[i + 1]
                if self._overlaps(a, b):
                    if not found:
                        self.stdout.write("⚠️ COMBINED ROOM + INSTRUCTOR CONFLICTS:\n")
                        found = True
                    self.stdout.write(
                        f"  • Instructor {a.instructor.instructorId} "
                        f"& Room {a.room.roomCode} on {day}: "
                        f"{a.startTime}-{a.endTime} ↔ {b.startTime}-{b.endTime}"
                    )

        if not found:
            self.stdout.write("✅ No combined conflicts.\n")
        return found

    # --------------------------------------------------
    # Time overlap helper
    # --------------------------------------------------
    def _overlaps(self, a, b):
        return (
            datetime.combine(datetime.today(), a.startTime)
            < datetime.combine(datetime.today(), b.endTime)
            and datetime.combine(datetime.today(), a.endTime)
            > datetime.combine(datetime.today(), b.startTime)
        )

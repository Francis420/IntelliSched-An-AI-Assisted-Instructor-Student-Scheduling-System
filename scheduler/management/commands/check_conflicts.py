from django.core.management.base import BaseCommand
from scheduling.models import Schedule, Semester
from datetime import datetime


class Command(BaseCommand):
    help = "Checks for overlapping room, instructor, section, and combined room+instructor conflicts for the active semester."

    def handle(self, *args, **options):
        # 🧠 Try to find the active semester automatically
        active_semester = Semester.objects.filter(isActive=True).order_by("-semesterId").first()

        if not active_semester:
            self.stdout.write("⚠️ No active semester found. Please activate one in the database.")
            return

        semester_name = active_semester.name
        self.stdout.write(f"\n📘 Active semester detected: {semester_name}\n")

        # ✅ Only include active schedules
        schedules = (
            Schedule.objects
            .filter(semester=active_semester, status="active")
            .select_related("room", "section", "instructor")
            .order_by("dayOfWeek", "startTime")
        )

        total = schedules.count()
        self.stdout.write(f"🔍 Checking {total} active schedule(s)...\n")

        if total == 0:
            self.stdout.write("⚠️ No active schedules found — nothing to check.\n")
            return

        room_conf = self.check_room_conflicts(schedules)
        instr_conf = self.check_instructor_conflicts(schedules)
        sect_conf = self.check_section_conflicts(schedules)
        combo_conf = self.check_combined_conflicts(schedules)

        if not any([room_conf, instr_conf, sect_conf, combo_conf]):
            self.stdout.write("\n✅ No scheduling conflicts found among active schedules!\n")

    # -----------------------------
    # Room Conflicts
    # -----------------------------
    def check_room_conflicts(self, schedules):
        grouped = {}
        for sch in schedules:
            room = getattr(sch.room, "roomCode", "TBA")
            grouped.setdefault((room, sch.dayOfWeek), []).append(sch)

        found = False
        for (room, day), lst in grouped.items():
            lst.sort(key=lambda s: s.startTime)
            for i in range(len(lst) - 1):
                cur, nxt = lst[i], lst[i + 1]
                if self._overlaps(cur, nxt):
                    if not found:
                        self.stdout.write("⚠️ ROOM CONFLICTS:\n")
                        found = True
                    self.stdout.write(
                        f"  • {room} on {day}: "
                        f"Section {cur.section.sectionId} ({cur.startTime}-{cur.endTime}) "
                        f"overlaps with Section {nxt.section.sectionId} ({nxt.startTime}-{nxt.endTime})"
                    )
        if not found:
            self.stdout.write("✅ No room conflicts found.\n")
        return found

    # -----------------------------
    # Instructor Conflicts
    # -----------------------------
    def check_instructor_conflicts(self, schedules):
        grouped = {}
        for sch in schedules:
            instr = getattr(sch.instructor, "instructorId", None)
            if not instr:
                continue
            grouped.setdefault((instr, sch.dayOfWeek), []).append(sch)

        found = False
        for (instr, day), lst in grouped.items():
            lst.sort(key=lambda s: s.startTime)
            for i in range(len(lst) - 1):
                cur, nxt = lst[i], lst[i + 1]
                if self._overlaps(cur, nxt):
                    if not found:
                        self.stdout.write("\n⚠️ INSTRUCTOR CONFLICTS:\n")
                        found = True
                    self.stdout.write(
                        f"  • Instructor {instr} on {day}: "
                        f"Section {cur.section.sectionId} ({cur.startTime}-{cur.endTime}) "
                        f"overlaps with Section {nxt.section.sectionId} ({nxt.startTime}-{nxt.endTime})"
                    )
        if not found:
            self.stdout.write("✅ No instructor conflicts found.\n")
        return found

    # -----------------------------
    # Section Conflicts
    # -----------------------------
    def check_section_conflicts(self, schedules):
        grouped = {}
        for sch in schedules:
            sec = getattr(sch.section, "sectionId", None)
            if not sec:
                continue
            grouped.setdefault((sec, sch.dayOfWeek), []).append(sch)

        found = False
        for (sec, day), lst in grouped.items():
            lst.sort(key=lambda s: s.startTime)
            for i in range(len(lst) - 1):
                cur, nxt = lst[i], lst[i + 1]
                if self._overlaps(cur, nxt):
                    if not found:
                        self.stdout.write("\n⚠️ SECTION CONFLICTS:\n")
                        found = True
                    self.stdout.write(
                        f"  • Section {sec} on {day}: "
                        f"{cur.startTime}-{cur.endTime} overlaps with {nxt.startTime}-{nxt.endTime}"
                    )
        if not found:
            self.stdout.write("✅ No section conflicts found.\n")
        return found

    # -----------------------------
    # Combined Instructor + Room Conflicts
    # -----------------------------
    def check_combined_conflicts(self, schedules):
        grouped = {}
        for sch in schedules:
            instr = getattr(sch.instructor, "instructorId", None)
            room = getattr(sch.room, "roomCode", "TBA")
            grouped.setdefault((instr, room, sch.dayOfWeek), []).append(sch)

        found = False
        for (instr, room, day), lst in grouped.items():
            if not instr or not room or room == "TBA":
                continue
            lst.sort(key=lambda s: s.startTime)
            for i in range(len(lst) - 1):
                cur, nxt = lst[i], lst[i + 1]
                if self._overlaps(cur, nxt):
                    if not found:
                        self.stdout.write("\n⚠️ COMBINED ROOM+INSTRUCTOR CONFLICTS:\n")
                        found = True
                    self.stdout.write(
                        f"  • Instructor {instr} & Room {room} on {day}: "
                        f"Section {cur.section.sectionId} ({cur.startTime}-{cur.endTime}) "
                        f"overlaps with Section {nxt.section.sectionId} ({nxt.startTime}-{nxt.endTime})"
                    )
        if not found:
            self.stdout.write("✅ No combined room+instructor conflicts found.\n")
        return found

    # -----------------------------
    # Helper overlap checker
    # -----------------------------
    def _overlaps(self, a, b):
        a_end = datetime.combine(datetime.today(), a.endTime)
        b_start = datetime.combine(datetime.today(), b.startTime)
        return a_end > b_start

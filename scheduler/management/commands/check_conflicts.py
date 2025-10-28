from django.core.management.base import BaseCommand
from scheduling.models import Schedule
from datetime import datetime


class Command(BaseCommand):
    help = "Checks for overlapping room, instructor, section, and combined room+instructor conflicts in a given semester."

    def add_arguments(self, parser):
        parser.add_argument(
            "semester_name",
            type=str,
            help="Name of the semester to check for conflicts",
        )

    def handle(self, *args, **options):
        semester_name = options["semester_name"]

        schedules = (
            Schedule.objects
            .filter(semester__name=semester_name, status="active")
            .select_related("room", "section", "instructor")
            .order_by("dayOfWeek", "startTime")
        )

        self.stdout.write(f"\n🔍 Checking schedule conflicts for semester: {semester_name}\n")

        room_conf = self.check_room_conflicts(schedules)
        instr_conf = self.check_instructor_conflicts(schedules)
        sect_conf = self.check_section_conflicts(schedules)
        combo_conf = self.check_combined_conflicts(schedules)

        if not any([room_conf, instr_conf, sect_conf, combo_conf]):
            self.stdout.write("✅ No scheduling conflicts found!\n")

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

# scheduler/solver.py

from ortools.sat.python import cp_model
from scheduling.models import Schedule
from core.models import Instructor
from scheduling.models import SubjectOffering, Subject
import random

def simulateTestData(semester, numSections=6):
    instructors = list(Instructor.objects.all())[:3]
    
    # Create mock subject offerings if none exist
    offerings = list(SubjectOffering.objects.filter(semester=semester))
    if not offerings:
        print("⚠️ No real SubjectOffering found — simulating fake ones.")
        subjects = list(Subject.objects.all())[:3]
        offerings = []
        for subj in subjects:
            fakeOffering = SubjectOffering(subject=subj, semester=semester, numberOfSections=2)
            offerings.append(fakeOffering)

    fakeSections = []
    sid = 1
    for offering in offerings:
        for i in range(min(numSections, offering.numberOfSections)):
            fakeSections.append({
                "id": sid,
                "subject": offering.subject,
                "type": "Lec" if i % 2 == 0 else "Lab",
                "units": 3,
            })
            sid += 1
            if len(fakeSections) >= numSections:
                break
        if len(fakeSections) >= numSections:
            break

    return fakeSections, instructors

def generateSchedule(semester, verbose=True):
    model = cp_model.CpModel()
    sections, instructors = simulateTestData(semester)
    
    instructorIndexMap = {inst.instructorId: idx for idx, inst in enumerate(instructors)}

    # Time setup
    minutesStart = 8 * 60
    minutesEnd = 20 * 60
    possibleStarts = list(range(minutesStart, minutesEnd - 60 + 1, 60))
    days = list(range(1, 6))  # Monday to Friday

    sectionVars = {}
    for sec in sections:
        start = model.NewIntVarFromDomain(cp_model.Domain.FromValues(possibleStarts), f"start_{sec['id']}")
        day = model.NewIntVar(1, 5, f"day_{sec['id']}")
        duration = sec["units"] * 60
        instructor = model.NewIntVar(0, len(instructors) - 1, f"instructor_{sec['id']}")
        interval = model.NewIntervalVar(start, duration, start + duration, f"interval_{sec['id']}")

        sectionVars[(sec["id"], sec["type"])] = {
            "start": start,
            "day": day,
            "instructor": instructor,
            "interval": interval,
            "duration": duration,
        }

    # You can insert constraint function calls here if needed

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    results = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for (sectionId, component), vars in sectionVars.items():
            start = solver.Value(vars["start"])
            day = solver.Value(vars["day"])
            instIdx = solver.Value(vars["instructor"])
            instructor = instructors[instIdx]

            results.append(Schedule(
                semester=semester,
                section_id=None,  # no real Section object yet
                instructor=instructor,
                dayOfWeek=day,
                startTime=f"{start // 60:02d}:{start % 60:02d}",
                endTime=f"{(start + vars['duration']) // 60:02d}:{(start + vars['duration']) % 60:02d}",
                scheduleType=component,  # 🛠️ replace with your real Schedule field name
            ))
    else:
        print("❌ No feasible schedule found.")

    if verbose:
        for r in results:
            print(f"{r.scheduleType} by {r.instructor} on Day {r.dayOfWeek} from {r.startTime} to {r.endTime}")

    return status, results

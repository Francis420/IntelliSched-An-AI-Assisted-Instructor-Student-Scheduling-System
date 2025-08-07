from ortools.sat.python import cp_model

def checkInstructorAvailability(instructorData, day, start, end):
    for block in instructorData["availability"]:
        if block["day"] == day and block["start"] <= start and block["end"] >= end:
            return True
    return False

def checkInstructorLoad(instructorData, assignedHours):
    if assignedHours <= instructorData["normalLoad"]:
        return True
    elif assignedHours <= instructorData["normalLoad"] + instructorData["overloadUnits"]:
        return True
    return False

def enforceLectureLabSplitDay(model, sectionVars, sections):
    for section in sections:
        if section.subject.hasLab:
            lecDay = sectionVars[(section.sectionId, "Lecture")]["day"]
            labDay = sectionVars[(section.sectionId, "Lab")]["day"]
            model.Add(lecDay != labDay)

def enforceSameInstructorForLectureLab(model, sectionVars, sections):
    for section in sections:
        if section.subject.hasLab:
            lecInst = sectionVars[(section.sectionId, "Lecture")]["instructor"]
            labInst = sectionVars[(section.sectionId, "Lab")]["instructor"]
            model.Add(lecInst == labInst)

def enforceNoInstructorOverlap(model, sectionVars, sections):
    from collections import defaultdict
    instructorToIntervals = defaultdict(list)

    for (secId, typ), vars in sectionVars.items():
        inst = vars["instructor"]
        interval = vars["interval"]
        instructorToIntervals[inst].append(interval)

    for intervals in instructorToIntervals.values():
        model.AddNoOverlap(intervals)

def enforceNoSectionOverlap(model, sectionVars, sections):
    from collections import defaultdict
    sectionToIntervals = defaultdict(list)

    for (secId, typ), vars in sectionVars.items():
        interval = vars["interval"]
        sectionToIntervals[secId].append(interval)

    for intervals in sectionToIntervals.values():
        model.AddNoOverlap(intervals)

def enforceGenEdBlocking(model, sectionVars, genedBlocks):
    for block in genedBlocks:
        blockStart = block.startTime.hour * 60 + block.startTime.minute
        blockEnd = block.endTime.hour * 60 + block.endTime.minute
        blockDay = block.dayOfWeek

        for key, vars in sectionVars.items():
            day = vars["day"]
            start = vars["start"]
            end = vars["end"]

            dayMatch = model.NewBoolVar(f"gened_day_{key}")
            startBeforeEnd = model.NewBoolVar(f"gened_startbefore_{key}")
            endAfterStart = model.NewBoolVar(f"gened_endafter_{key}")
            blocked = model.NewBoolVar(f"gened_blocked_{key}")

            model.Add(day == blockDay).OnlyEnforceIf(dayMatch)
            model.Add(start < blockEnd).OnlyEnforceIf(startBeforeEnd)
            model.Add(end > blockStart).OnlyEnforceIf(endAfterStart)

            model.AddBoolAnd([dayMatch, startBeforeEnd, endAfterStart]).OnlyEnforceIf(blocked)
            model.Add(blocked == 0)

def enforceTimeWindow(model, sectionVars):
    for key, vars in sectionVars.items():
        model.Add(vars["start"] >= 8 * 60)
        model.Add(vars["end"] <= 20 * 60)

def addFairnessSoftConstraint(model, instructorLoadVars):
    maxLoad = model.NewIntVar(0, 100, "maxLoad")
    minLoad = model.NewIntVar(0, 100, "minLoad")
    model.AddMaxEquality(maxLoad, list(instructorLoadVars.values()))
    model.AddMinEquality(minLoad, list(instructorLoadVars.values()))
    model.Minimize(maxLoad - minLoad)

def enforceInstructorAvailability(model, sectionVars, instructorDataMap):
    for key, vars in sectionVars.items():
        instId = vars["instructor"]
        dayVar = vars["day"]
        startVar = vars["start"]
        endVar = vars["end"]

        # Instructor availability assumed as list of {day, start, end} in minutes
        if instId not in instructorDataMap:
            continue
        availability = instructorDataMap[instId]["availability"]

        allowed = []
        for block in availability:
            day = block["day"]
            start = block["start"]
            end = block["end"]

            b1 = model.NewBoolVar(f"avail_{key}_day")
            b2 = model.NewBoolVar(f"avail_{key}_start")
            b3 = model.NewBoolVar(f"avail_{key}_end")
            valid = model.NewBoolVar(f"avail_{key}_valid")

            model.Add(dayVar == day).OnlyEnforceIf(b1)
            model.Add(startVar >= start).OnlyEnforceIf(b2)
            model.Add(endVar <= end).OnlyEnforceIf(b3)
            model.AddBoolAnd([b1, b2, b3]).OnlyEnforceIf(valid)
            allowed.append(valid)

        if allowed:
            model.AddBoolOr(allowed)

def enforceInstructorLoadCap(model, instructorLoadVars, instructorDataMap):
    for instId, loadVar in instructorLoadVars.items():
        cap = instructorDataMap[instId]["normalLoad"]
        model.Add(loadVar <= cap)

def enforceInstructorOverloadLimit(model, instructorLoadVars, instructorDataMap):
    for instId, loadVar in instructorLoadVars.items():
        cap = instructorDataMap[instId]["normalLoad"] + instructorDataMap[instId]["overloadUnits"]
        model.Add(loadVar <= cap)

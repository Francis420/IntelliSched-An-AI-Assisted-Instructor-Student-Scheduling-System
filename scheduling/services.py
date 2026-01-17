from django.db.models import Sum
from instructors.models import Instructor
from scheduling.models import Section, InstructorSchedulingConfiguration

def getPreSchedulingAnalysis(semester):
    """
    Returns a dictionary with 'summary' (for dashboards) and 'details' (for the full report).
    """
    
    # --- 1. DEMAND (Required Hours from Sections) ---
    sections = Section.objects.filter(semester=semester).select_related('subject')
    
    year_levels = {
        1: {'label': '1st Year', 'hours': 0, 'sections': 0},
        2: {'label': '2nd Year', 'hours': 0, 'sections': 0},
        3: {'label': '3rd Year', 'hours': 0, 'sections': 0},
        4: {'label': '4th Year', 'hours': 0, 'sections': 0},
        0: {'label': 'Others', 'hours': 0, 'sections': 0},
    }

    total_demand_minutes = 0

    for section in sections:
        subject = section.subject
        
        lec = subject.durationMinutes or 0
        lab = subject.labDurationMinutes or 0
        duration = lec + lab
        
        total_demand_minutes += duration
        
        if hasattr(subject, 'yearLevel') and subject.yearLevel in [1, 2, 3, 4]:
            lvl = subject.yearLevel
        else:
            lvl = 0
            
        year_levels[lvl]['hours'] += (duration / 60)
        year_levels[lvl]['sections'] += 1

    total_demand_hours = round(total_demand_minutes / 60, 2)
    demand_details = [data for _, data in year_levels.items() if data['sections'] > 0]
    demand_details.sort(key=lambda x: x['label'])


    # --- 2. SUPPLY (Available Faculty Hours) ---
    instructors = Instructor.objects.filter(
        userlogin__user__isActive=True
    ).select_related('rank', 'designation')

    config = InstructorSchedulingConfiguration.objects.first()
    if not config:
        config = InstructorSchedulingConfiguration() 

    total_supply_hours = 0
    total_regular = 0
    total_overload = 0
    instructor_details = []

    for instr in instructors:
        reg_load = 0
        max_overload = 0
        
        # --- NEW: DETERMINE DISPLAY TITLE (Rank vs Designation) ---
        role_title = "" 
        
        # -- PERMANENT --
        if instr.employmentType == 'permanent':
            # Check for valid Designation first (Not None, Not 'N/A')
            has_designation = (instr.designation and instr.designation.name != 'N/A')
            
            if has_designation:
                # Use Designation limits
                reg_load = instr.designation.instructionHours
                max_overload = config.overload_limit_with_designation
                role_title = instr.designation.name  # e.g., "Dean", "Chairperson"
            else:
                # Fallback to Rank limits
                reg_load = instr.rank.instructionHours if instr.rank else 0
                max_overload = config.overload_limit_no_designation
                role_title = instr.rank.name if instr.rank else "Unranked" # e.g., "Instructor I"
        
        # -- PART-TIME --
        elif instr.employmentType == 'part-time':
            reg_load = config.part_time_normal_limit
            max_overload = config.part_time_overload_limit
            role_title = "Part-Time Instructor"
            
        # -- PURE OVERLOAD --
        elif instr.employmentType == 'overload':
            reg_load = config.pure_overload_normal_limit 
            max_overload = config.pure_overload_max_limit
            role_title = "Overload Only"

        capacity = reg_load + max_overload
        
        total_supply_hours += capacity
        total_regular += reg_load
        total_overload += max_overload

        instructor_details.append({
            'name': instr.full_name, 
            'type': instr.get_employmentType_display(), # Still useful for badges (Permanent/Part-Time)
            'role_title': role_title,                   # The specific title (Dean/Instructor I)
            'regular': reg_load,
            'overload': max_overload,
            'total': capacity
        })

    instructor_details.sort(key=lambda x: x['total'], reverse=True)

    # --- 3. STATUS ---
    gap = total_supply_hours - total_demand_hours
    status = 'deficit' if gap < 0 else 'surplus'
    
    return {
        'semester': semester,
        'summary': {
            'total_demand': total_demand_hours,
            'total_supply': total_supply_hours,
            'gap': abs(round(gap, 2)),
            'status': status,
            'section_count': sections.count(),
            'instructor_count': instructors.count()
        },
        'details': {
            'demand_by_year': demand_details,
            'instructor_supply': instructor_details,
            'total_regular': total_regular,
            'total_overload': total_overload
        }
    }
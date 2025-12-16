# scheduler/diagnostics.py
from django.db.models import Sum
from scheduling.models import Semester, Section
from scheduler.data_extractors import get_solver_data

def check_supply_vs_demand(semester_id=None):
    """
    Analyzes the instructor hours (Supply) vs Section hours needed (Demand).
    If semester_id is NOT provided, it automatically finds the Active Semester.
    """
    
    # --- 1. Get the Active Semester ---
    if semester_id is None:
        # Find the most recently created active semester
        semester = Semester.objects.filter(isActive=True).order_by('-createdAt').first()
        if not semester:
            print("❌ ERROR: No active semester found in the database.")
            print("   Please set a semester to 'Active' in the admin panel or pass an ID.")
            return
    else:
        try:
            semester = Semester.objects.get(pk=semester_id)
        except Semester.DoesNotExist:
            print(f"❌ ERROR: Semester with ID {semester_id} not found.")
            return

    print(f"\n🔎 Running Diagnostics for Semester: {semester.name} ({semester.academicYear})")
    
    # --- 2. Extract Data ---
    # We use your existing helper to ensure we see exactly what the solver sees
    try:
        data = get_solver_data(semester)
    except Exception as e:
        print(f"❌ Error extracting solver data: {e}")
        return

    instructors = data.get("instructors", [])      # List of instructor IDs
    instructor_caps = data.get("instructor_caps", {}) 
    sections = data.get("sections", [])            # List of section IDs
    section_hours = data.get("section_hours", {})

    # --- 3. Calculate SUPPLY (Instructor Hours) ---
    total_regular_min = 0
    total_overload_min = 0
    instructor_count = len(instructors)

    for instr_id in instructors:
        caps = instructor_caps.get(instr_id, {})
        # Safety check: default to 0 if key is missing
        r_lim = caps.get("normal_limit_min", 0) 
        o_lim = caps.get("overload_limit_min", 0)
        
        total_regular_min += r_lim
        total_overload_min += o_lim

    total_capacity_min = total_regular_min + total_overload_min

    # --- 4. Calculate DEMAND (Section Hours) ---
    total_needed_min = 0
    section_count = len(sections)

    for sec_id in sections:
        hours = section_hours.get(sec_id, {"lecture_min": 0, "lab_min": 0})
        l_min = hours.get("lecture_min", 0) or 0
        b_min = hours.get("lab_min", 0) or 0
        total_needed_min += (l_min + b_min)

    # --- 5. Convert & Format ---
    def min_to_hr(m): return round(m / 60.0, 2)

    total_regular_hr = min_to_hr(total_regular_min)
    total_overload_hr = min_to_hr(total_overload_min)
    total_capacity_hr = min_to_hr(total_capacity_min)
    total_needed_hr = min_to_hr(total_needed_min)
    
    balance_hr = total_capacity_hr - total_needed_hr

    # --- 6. Print Report ---
    print("\n" + "="*50)
    print(f"📊 SUPPLY VS DEMAND REPORT")
    print("="*50)
    print(f"Target: {semester.name} | {semester.academicYear} | {semester.term}")
    print("-" * 50)
    
    print(f"Counts:")
    print(f"  • Instructors:     {instructor_count}")
    print(f"  • Sections:        {section_count}")
    
    print(f"\nSupply (Instructor Capability):")
    print(f"  • Regular Load:    {total_regular_hr} hrs")
    print(f"  • Overload:        {total_overload_hr} hrs")
    print(f"  • TOTAL SUPPLY:    {total_capacity_hr} hrs")

    print(f"\nDemand (Section Requirements):")
    print(f"  • TOTAL DEMAND:    {total_needed_hr} hrs")

    print("-" * 50)
    
    if balance_hr >= 0:
        print(f"✅ FEASIBLE (Mathematically)")
        print(f"   You have a SURPLUS of {balance_hr:.2f} instructor hours.")
        print(f"   (Note: Schedule conflicts might still exist, but you have enough raw hours.)")
    else:
        print(f"❌ IMPOSSIBLE (Deficit)")
        print(f"   You are MISSING {-balance_hr:.2f} instructor hours.")
        print(f"   The solver will likely fail or run forever.")
    
    print("="*50 + "\n")
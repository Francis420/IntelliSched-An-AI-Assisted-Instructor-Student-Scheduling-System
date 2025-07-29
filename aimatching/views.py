from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from authapi.views import has_role
from aimatching.models import MatchingRun, MatchingConfig, MatchingProgress, InstructorSubjectMatch
from aimatching.matcher import run_matching
from scheduling.models import Semester, Subject
import uuid
from django.http import JsonResponse
from django.core.paginator import Paginator
from core.models import User
from aimatching.tasks import run_matching_task


# ---------- MATCHING ----------

@login_required
@has_role('deptHead')
def matchingDashboard(request):
    from aimatching.models import InstructorSubjectMatch, MatchingRun

    batchId = request.GET.get('batchId')
    semester_id = request.GET.get('semester')

    semester = get_object_or_404(Semester, pk=semester_id) if semester_id else Semester.objects.filter(isActive=True).first()

    if not semester:
        messages.error(request, "❌ No active semester found.")
        return redirect('configList')

    if not batchId:
        latest_run = MatchingRun.objects.order_by('-generatedAt').first()
        if latest_run:
            batchId = latest_run.batchId
            print(f"[DEBUG] Using latest batchId: {batchId}")
        else:
            messages.error(request, "❌ No matching runs found.")
            return redirect('configList')

    term_map = {'1st': 0, '2nd': 1, 'Midyear': 2}
    default_term = term_map.get(semester.term)

    if default_term is None:
        messages.error(request, f"❌ Unrecognized term: {semester.term}")
        return redirect('configList')

    subjects = Subject.objects.filter(defaultTerm=default_term, isActive=True)

    print(f"[DEBUG] Semester: {semester.name} | Subjects found: {subjects.count()}")

    for subject in subjects:
        matches = InstructorSubjectMatch.objects.filter(
            batchId=batchId,
            subject=subject,
            isLatest=True,   # keep only latest to avoid stale data
        ).select_related('instructor', 'latestHistory') \
         .order_by('-latestHistory__confidenceScore')[:5]

        subject.top_matches = matches
        print(f"[DEBUG] Subject {subject.code} - Matches loaded: {matches.count()}")

    return render(request, 'aimatching/matching/dashboard.html', {
        "subjects": subjects,
        "batchId": batchId,
        "semester": semester,
    })



@login_required
@has_role('deptHead')
def matchingStart(request):
    # Only get active semesters
    semesters = Semester.objects.filter(isActive=True).order_by('-createdAt')
    if not semesters.exists():
        messages.error(request, "❌ No active semester available. Please create or activate one first.")
        return redirect('semesterList')

    return render(request, 'aimatching/matching/start.html', {
        'semesters': semesters,
    })


@login_required
@has_role('deptHead')
def matchingRun(request):
    if request.method != 'POST':
        messages.error(request, "Invalid request.")
        return redirect('matchingDashboard')

    semester_id = request.POST.get('semesterId')
    semester = get_object_or_404(Semester, pk=semester_id)
    batch_id = str(uuid.uuid4())

    try:
        term_map = {'1st': 0, '2nd': 1, 'Midyear': 2}
        valid_subjects = Subject.objects.filter(
            defaultTerm=term_map[semester.term],
            isActive=True
        )
        instructors = User.objects.filter(
            roles__name="Instructor",
            isActive=True
        ).distinct()

        total_tasks = valid_subjects.count() * instructors.count()

        MatchingProgress.objects.create(
            batchId=batch_id,
            semester=semester,
            totalTasks=total_tasks,
            completedTasks=0,
            status="running",
        )

        # 🔥 Run matching asynchronously
        run_matching_task.delay(semester.semesterId, batch_id, request.user.id)

        MatchingRun.objects.create(
            semester=semester,
            batchId=batch_id,
            totalSubjects=valid_subjects.count(),
            totalInstructors=instructors.count(),
            generatedBy=request.user,
        )

        return render(request, 'aimatching/matching/progress.html', {
            "batchId": batch_id,
            "semester": semester,
        })

    except Exception as e:
        messages.error(request, f"❌ Error running matching: {str(e)}")
        return redirect('matchingDashboard')


@login_required
@has_role('deptHead')
def matchingProgress(request, run_id):
    try:
        progress = get_object_or_404(MatchingProgress, batchId=run_id)
        semester = progress.semester

        term_map = {'1st': 0, '2nd': 1, 'Midyear': 2}
        default_term = term_map.get(semester.term)
        valid_subjects = Subject.objects.filter(defaultTerm=default_term, isActive=True)

        instructors = User.objects.filter(
            roles__name="Instructor",
            isActive=True
        ).distinct()

        subject_count = valid_subjects.count()
        instructor_count = instructors.count()
        total_tasks = subject_count * instructor_count

        print(f"[DEBUG] Progress calc — Subjects: {subject_count}, Instructors: {instructor_count}, Total Tasks: {total_tasks}")

        data = {
            "totalTasks": total_tasks,
            "completedTasks": progress.completedTasks,
            "status": progress.status,
            "percentage": (progress.completedTasks / total_tasks) * 100 if total_tasks > 0 else 0,
        }
        return JsonResponse(data)

    except Exception as e:
        print(f"❌ Exception in matchingProgress: {e}")
        return JsonResponse({"error": str(e)}, status=500)



@login_required
@has_role('deptHead')
def matchingProgressPage(request, batchId):
    progress = get_object_or_404(MatchingProgress, batchId=batchId)
    return render(request, 'aimatching/matching/progress.html', {
        "batchId": batchId,
        "semester": progress.semester,
    })


@login_required
@has_role('deptHead')
def matchingResults(request, batchId):
    subject_id = request.GET.get('subject')
    instructor_id = request.GET.get('instructor')
    sort_by = request.GET.get('sort', 'total')  # default sort by total confidence
    direction = request.GET.get('dir', 'desc')  # asc or desc

    # Get the semester for this batch
    progress = get_object_or_404(MatchingProgress, batchId=batchId)
    semester = progress.semester

    # Map semester term -> subject defaultTerm
    term_map = {'1st': 0, '2nd': 1, 'Midyear': 2}
    valid_subjects = Subject.objects.filter(
        defaultTerm=term_map[semester.term],
        isActive=True
    ).values_list("subjectId", flat=True)

    matches = InstructorSubjectMatch.objects.filter(
        batchId=batchId,
        subject_id__in=valid_subjects
    ).select_related(
        'instructor', 'subject', 'latestHistory'
    )

    if subject_id:
        matches = matches.filter(subject_id=subject_id)
    if instructor_id:
        matches = matches.filter(instructor_id=instructor_id)

    # Map sort options to model fields
    sort_map = {
        "teaching": "latestHistory__teachingScore",
        "credentials": "latestHistory__credentialScore",
        "experience": "latestHistory__experienceScore",
        "preference": "latestHistory__preferenceScore",
        "total": "latestHistory__confidenceScore",
    }

    sort_field = sort_map.get(sort_by, "latestHistory__confidenceScore")
    if direction == "desc":
        sort_field = "-" + sort_field
    matches = matches.order_by(sort_field)

    paginator = Paginator(matches, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'aimatching/matching/results.html', {
        "matches": page_obj,
        "batchId": batchId,
        "subject_id": subject_id,
        "instructor_id": instructor_id,
        "sort_by": sort_by,
        "direction": direction,
        "semester": semester,
    })


# ---------- CONFIG ----------

@login_required
@has_role('deptHead')
def configList(request):
    active_semesters = Semester.objects.filter(isActive=True)
    for sem in active_semesters:
        MatchingConfig.objects.get_or_create(
            semester=sem,
            defaults={
                "teachingWeight": 0.2,
                "credentialsWeight": 0.3,
                "experienceWeight": 0.3,
                "preferenceWeight": 0.2,
            }
        )

    configs = MatchingConfig.objects.select_related('semester').all().order_by('-createdAt')
    return render(request, 'aimatching/config/list.html', {'configs': configs})


@login_required
@has_role('deptHead')
@transaction.atomic
def configUpdate(request, semesterId):
    semester = get_object_or_404(Semester, pk=semesterId)
    config, created = MatchingConfig.objects.get_or_create(semester=semester)

    if request.method == 'POST':
        config.teachingWeight = float(request.POST.get('teachingWeight', 0.2))
        config.credentialsWeight = float(request.POST.get('credentialsWeight', 0.3))
        config.experienceWeight = float(request.POST.get('experienceWeight', 0.3))
        config.preferenceWeight = float(request.POST.get('preferenceWeight', 0.2))

        total = (
            config.teachingWeight
            + config.credentialsWeight
            + config.experienceWeight
            + config.preferenceWeight
        )
        if abs(total - 1.0) > 0.01:
            messages.error(request, "❌ Weights must add up to 1.0")
        else:
            config.save()
            messages.success(request, f"✅ Matching config updated for {semester.name}")
            return redirect('configList')

    return render(request, 'aimatching/config/update.html', {
        'semester': semester,
        'config': config
    })

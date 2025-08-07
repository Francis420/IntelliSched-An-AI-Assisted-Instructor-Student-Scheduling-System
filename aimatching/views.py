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
from django.core.cache import cache
from django.db import models
from django.template.loader import render_to_string
from django.db.models import Window, F, Q, OuterRef, Subquery, IntegerField, Value
from django.db.models.functions import Rank
from django.db.models.functions import Concat




# ---------- MATCHING ----------

@login_required
@has_role('deptHead')
def matchingDashboard(request):
    from aimatching.models import InstructorSubjectMatch, MatchingRun

    batchId = request.GET.get('batchId')
    semester_id = request.GET.get('semester')
    subject_query = request.GET.get('subject', '').strip()

    semester = (
        get_object_or_404(Semester, pk=semester_id)
        if semester_id
        else Semester.objects.filter(isActive=True).first()
    )

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

    if subject_query:
        subjects = subjects.filter(
            Q(name__icontains=subject_query) | Q(code__icontains=subject_query)
        )

    for subject in subjects:
        matches = (
            InstructorSubjectMatch.objects.filter(
                batchId=batchId,
                subject=subject,
                isLatest=True,
            )
            .select_related('instructor', 'latestHistory')
            .order_by('-latestHistory__confidenceScore')[:5]
        )

        # Attach readable names using Instructor.full_name property
        for m in matches:
            m.instructor_display_name = m.instructor.full_name

        subject.top_matches = matches

    return render(
        request,
        'aimatching/matching/dashboard.html',
        {
            "subjects": subjects,
            "batchId": batchId,
            "semester": semester,
            "subject_query": subject_query,
        },
    )


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
def matchingResultsLive(request, batchId):
    return _matching_results_common(request, batchId, live=True)


@login_required
@has_role('deptHead')
def matchingResults(request, batchId):
    return _matching_results_common(request, batchId, live=False)


def _matching_results_common(request, batchId, live=False):
    subject_query = request.GET.get('subject', '').strip()
    instructor_query = request.GET.get('instructor', '').strip()
    sort_by = request.GET.get('sort', 'rank')
    direction = request.GET.get('dir', 'asc')
    page = int(request.GET.get('page', 1))

    progress = get_object_or_404(MatchingProgress, batchId=batchId)
    semester = progress.semester

    term_map = {'1st': 0, '2nd': 1, 'Midyear': 2}
    valid_subjects = Subject.objects.filter(
        defaultTerm=term_map[semester.term],
        isActive=True
    ).values_list("subjectId", flat=True)

    cache_key_base = f"ranked_matches:{batchId}:{semester.term}"
    ranked_matches = cache.get(cache_key_base)

    if not ranked_matches:
        qs = InstructorSubjectMatch.objects.filter(
            batchId=batchId,
            subject_id__in=valid_subjects
        ).select_related('instructor', 'subject', 'latestHistory')

        qs = qs.annotate(
            fixed_rank=Window(
                expression=Rank(),
                partition_by=[F("subject_id")],
                order_by=F("latestHistory__confidenceScore").desc()
            )
        )

        ranked_matches = list(
            qs.values("matchId", "subject_id", "fixed_rank")
        )
        cache.set(cache_key_base, ranked_matches, timeout=300)

    rank_map = {r["matchId"]: r["fixed_rank"] for r in ranked_matches}

    qs = InstructorSubjectMatch.objects.filter(
        batchId=batchId,
        subject_id__in=valid_subjects
    ).select_related('instructor', 'subject', 'latestHistory')

    if subject_query:
        qs = qs.filter(
            Q(subject__name__icontains=subject_query) |
            Q(subject__code__icontains=subject_query)
        )
    qs = qs.annotate(
        full_name=Concat(
            F("instructor__userlogin__user__firstName"),
            Value(" "),
            F("instructor__userlogin__user__lastName")
        )
    )

    if instructor_query:
        qs = qs.filter(full_name__icontains=instructor_query)

    results = []
    for obj in qs:
        obj.fixed_rank = rank_map.get(obj.matchId, None)

        if obj.latestHistory:
            obj.latestHistory.teachingScorePct = obj.latestHistory.teachingScore * 100
            obj.latestHistory.credentialScorePct = obj.latestHistory.credentialScore * 100
            obj.latestHistory.experienceScorePct = obj.latestHistory.experienceScore * 100
            obj.latestHistory.preferenceScorePct = obj.latestHistory.preferenceScore * 100
            obj.latestHistory.confidenceScorePct = obj.latestHistory.confidenceScore * 100

        results.append(obj)


    sort_map = {
        "rank": lambda x: (x.fixed_rank if x.fixed_rank is not None else 9999),
        "teaching": lambda x: x.latestHistory.teachingScore if x.latestHistory else 0,
        "credentials": lambda x: x.latestHistory.credentialScore if x.latestHistory else 0,
        "experience": lambda x: x.latestHistory.experienceScore if x.latestHistory else 0,
        "preference": lambda x: x.latestHistory.preferenceScore if x.latestHistory else 0,
        "total": lambda x: x.latestHistory.confidenceScore if x.latestHistory else 0,
    }

    key_func = sort_map.get(sort_by, sort_map["rank"])
    results = sorted(results, key=key_func, reverse=(direction == "desc"))

    paginator = Paginator(results, 10)
    page_obj = paginator.get_page(page)

    context = {
        "matches": page_obj,
        "batchId": batchId,
        "semester": semester,
        "columns": [
            ("teaching", "Teaching"),
            ("credentials", "Credentials"),
            ("experience", "Experience"),
            ("preference", "Preference"),
            ("total", "Total Confidence Score"),
        ],
        "sort_by": sort_by,
        "direction": direction,
        "subject_query": subject_query,
        "instructor_query": instructor_query,
    }

    if live:
        html = render_to_string("aimatching/matching/_results_table.html", context, request=request)
        return JsonResponse({"html": html, "cached": True})
    else:
        return render(request, 'aimatching/matching/results.html', context)


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

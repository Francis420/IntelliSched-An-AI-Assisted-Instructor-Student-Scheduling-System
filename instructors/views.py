from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from instructors.models import (
    InstructorExperience, 
    InstructorCredentials, 
    InstructorRank,
    InstructorDesignation,
    InstructorAcademicAttainment,
    InstructorLegacyExperience,
)
from core.models import UserLogin
from scheduling.models import Semester
from authapi.views import has_role
from django.utils.timezone import now
from scheduling.models import Subject
from django.utils.dateparse import parse_time
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.db.models import Q

# ---------- Instructor Portfolio ----------
@login_required
@has_role('instructor')
def instructorPortfolio(request):
    return render(request, 'instructors/portfolio.html')


# ---------- Instructor Experience ----------

@login_required
@has_role('instructor') 
def experienceList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    experiences = InstructorExperience.objects.filter(
        instructor=instructor
    ).prefetch_related("relatedSubjects").order_by("-startDate")

    if query:
        experiences = experiences.filter(
            Q(title__icontains=query) |
            Q(organization__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query) |
            Q(experienceType__icontains=query) |
            Q(employmentType__icontains=query) |
            Q(relatedSubjects__name__icontains=query) |
            Q(relatedSubjects__code__icontains=query)
        ).distinct()

    paginator = Paginator(experiences, 5)
    page_obj = paginator.get_page(page)

    return render(request, "instructors/experiences/list.html", {
        "experiences": page_obj,
        "query": query,
    })


@login_required
@has_role('instructor')
def experienceListLive(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return JsonResponse({"error": "Instructor not found"}, status=400)

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    experiences = InstructorExperience.objects.filter(
        instructor=instructor
    ).prefetch_related("relatedSubjects").order_by("-startDate")

    if query:
        experiences = experiences.filter(
            Q(title__icontains=query) |
            Q(organization__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query) |
            Q(experienceType__icontains=query) |
            Q(employmentType__icontains=query) |
            Q(relatedSubjects__name__icontains=query) |
            Q(relatedSubjects__code__icontains=query)
        ).distinct()

    paginator = Paginator(experiences, 5)
    page_obj = paginator.get_page(page)

    html = render_to_string("instructors/experiences/_table.html", {
        "experiences": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@login_required
@has_role('instructor')
def experienceCreate(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor

    if request.method == 'POST':
        title = request.POST.get('title')
        organization = request.POST.get('organization')
        location = request.POST.get('location')
        startDate = request.POST.get('startDate')
        endDate = request.POST.get('endDate')
        description = request.POST.get('description')
        experienceType = request.POST.get('experienceType')
        employmentType = request.POST.get('employmentType')
        relatedSubjectIds = request.POST.getlist('relatedSubjects')
        
        # Handle current job checkbox
        isCurrent = request.POST.get('isCurrent') == 'on'
        
        if isCurrent:
            endDate = None
        elif not endDate:
             endDate = None

        experience = InstructorExperience.objects.create(
            instructor=instructor,
            title=title,
            organization=organization,
            location=location,
            startDate=startDate,
            endDate=endDate,
            isCurrent=isCurrent,
            description=description,
            experienceType=experienceType,
            employmentType=employmentType
        )
        
        if relatedSubjectIds:
            experience.relatedSubjects.set(relatedSubjectIds)

        messages.success(request, 'Experience added successfully.')
        return redirect('instructorDashboard')

    subjects = Subject.objects.all().order_by('code')
    context = {
        'subjects': subjects,
        'experience_types': InstructorExperience.EXPERIENCE_TYPE_CHOICES,
        'employment_types': InstructorExperience.EMPLOYMENT_TYPE_CHOICES
    }
    return render(request, 'instructors/experiences/create.html', context)


@login_required
@has_role('instructor')
def experienceUpdate(request, experienceId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    experience = get_object_or_404(InstructorExperience, pk=experienceId, instructor=instructor)

    if request.method == 'POST':
        experience.title = request.POST.get('title')
        experience.organization = request.POST.get('organization')
        experience.location = request.POST.get('location')
        experience.startDate = request.POST.get('startDate')
        
        isCurrent = request.POST.get('isCurrent') == 'on'
        experience.isCurrent = isCurrent
        
        if isCurrent:
            experience.endDate = None
        else:
            endDate = request.POST.get('endDate')
            experience.endDate = endDate if endDate else None

        experience.description = request.POST.get('description')
        experience.experienceType = request.POST.get('experienceType')
        experience.employmentType = request.POST.get('employmentType')
        
        relatedSubjectIds = request.POST.getlist('relatedSubjects')

        experience.save()
        experience.relatedSubjects.set(relatedSubjectIds)

        messages.success(request, 'Experience updated successfully.')
        return redirect('instructorDashboard')

    subjects = Subject.objects.all().order_by('code')
    
    # Pre-select logic
    selected_subject_ids = list(experience.relatedSubjects.values_list('subjectId', flat=True))

    context = {
        'experience': experience,
        'subjects': subjects,
        'experience_types': InstructorExperience.EXPERIENCE_TYPE_CHOICES,
        'employment_types': InstructorExperience.EMPLOYMENT_TYPE_CHOICES,
        'selected_subjects': selected_subject_ids
    }
    return render(request, 'instructors/experiences/update.html', context)


@login_required
@has_role('instructor')
def experienceDelete(request, experienceId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    experience = get_object_or_404(InstructorExperience, pk=experienceId, instructor=login.instructor)
    experience.delete()
    messages.success(request, "Experience deleted successfully.")
    return redirect('instructorDashboard')


# ---------- Instructor Credential ----------
@login_required
@has_role('instructor')
def credentialList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    # Fetch credentials
    credentials = InstructorCredentials.objects.filter(
        instructor=instructor
    ).prefetch_related("relatedSubjects").order_by("-dateEarned")

    # Apply search filter
    if query:
        credentials = credentials.filter(
            Q(title__icontains=query) |
            Q(credentialType__icontains=query) |
            Q(issuer__icontains=query) |
            Q(relatedSubjects__code__icontains=query) |
            Q(relatedSubjects__name__icontains=query)
        ).distinct()

    paginator = Paginator(credentials, 5)
    page_obj = paginator.get_page(page)

    return render(request, "instructors/credentials/list.html", {
        "credentials": page_obj,
        "query": query,
    })


@login_required
@has_role('instructor')
def credentialListLive(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return JsonResponse({"error": "Instructor not found"}, status=400)

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    credentials = InstructorCredentials.objects.filter(
        instructor=instructor
    ).prefetch_related("relatedSubjects").order_by("-dateEarned")

    if query:
        credentials = credentials.filter(
            Q(title__icontains=query) |
            Q(credentialType__icontains=query) |
            Q(issuer__icontains=query) |
            Q(relatedSubjects__code__icontains=query) |
            Q(relatedSubjects__name__icontains=query)
        ).distinct()

    paginator = Paginator(credentials, 5)
    page_obj = paginator.get_page(page)

    html = render_to_string("instructors/credentials/_table.html", {
        "credentials": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@login_required
@has_role('instructor')
def credentialCreate(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    subjects = Subject.objects.all()

    types = InstructorCredentials.CREDENTIAL_TYPE_CHOICES 

    if request.method == 'POST':
        credentialType = request.POST.get('credentialType')
        title = request.POST.get('title')
        issuer = request.POST.get('issuer')
        dateEarned = request.POST.get('dateEarned')
        expirationDate = request.POST.get('expirationDate')
        
        if not expirationDate:
            expirationDate = None
            
        relatedSubjectIds = request.POST.getlist('relatedSubjects')

        credential = InstructorCredentials.objects.create(
            instructor=instructor,
            credentialType=credentialType,
            title=title,
            issuer=issuer,
            dateEarned=dateEarned,
            expirationDate=expirationDate
        )
        
        if relatedSubjectIds:
            credential.relatedSubjects.set(relatedSubjectIds)

        messages.success(request, "Credential added successfully.")
        return redirect('instructorDashboard')

    return render(request, 'instructors/credentials/create.html', {
        'types': types,
        'subjects': subjects
    })


@login_required
@has_role('instructor')
def credentialUpdate(request, credentialId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    credential = get_object_or_404(InstructorCredentials, pk=credentialId, instructor=login.instructor)
    subjects = Subject.objects.all()
    types = InstructorCredentials.CREDENTIAL_TYPE_CHOICES

    if request.method == 'POST':
        credential.credentialType = request.POST.get('credentialType')
        credential.title = request.POST.get('title')
        credential.issuer = request.POST.get('issuer')
        credential.dateEarned = request.POST.get('dateEarned')
        
        expirationDate = request.POST.get('expirationDate')
        if not expirationDate:
            credential.expirationDate = None
        else:
            credential.expirationDate = expirationDate
            
        credential.relatedSubjects.set(request.POST.getlist('relatedSubjects'))
        
        credential.save()

        messages.success(request, "Credential updated successfully.")
        return redirect('instructorDashboard')

    return render(request, 'instructors/credentials/update.html', {
        'credential': credential,
        'types': types,
        'subjects': subjects,
        'selected_subjects': list(credential.relatedSubjects.values_list('subjectId', flat=True))
    })


@login_required
@has_role('instructor')
def credentialDelete(request, credentialId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    credential = get_object_or_404(InstructorCredentials, pk=credentialId, instructor=login.instructor)
    credential.delete()
    messages.success(request, "Credential deleted successfully.")
    return redirect('instructorDashboard')


# ---------- Instructor Teaching History ----------
@login_required
@has_role('instructor')
def legacyExperienceList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    experiences = InstructorLegacyExperience.objects.filter(
        instructor=instructor
    ).select_related("subject").order_by("-lastTaughtYear", "-updatedAt")

    if query:
        experiences = experiences.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(remarks__icontains=query)
        )

    paginator = Paginator(experiences, 5)
    page_obj = paginator.get_page(page)

    return render(request, "instructors/teachingHistory/list.html", {
        "experiences": page_obj,
        "query": query,
    })


@login_required
@has_role('instructor')
def legacyExperienceListLive(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return JsonResponse({"error": "Instructor not found"}, status=400)

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    experiences = InstructorLegacyExperience.objects.filter(
        instructor=instructor
    ).select_related("subject").order_by("-lastTaughtYear", "-updatedAt")

    if query:
        experiences = experiences.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(remarks__icontains=query)
        )

    paginator = Paginator(experiences, 5)
    page_obj = paginator.get_page(page)

    html = render_to_string("instructors/teachingHistory/_table.html", {
        "experiences": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@login_required
@has_role('instructor')
def legacyExperienceCreate(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    subjects = Subject.objects.all().order_by('code')

    if request.method == 'POST':
        try:
            subjectId = request.POST.get('subject')
            priorTimesTaught = request.POST.get('priorTimesTaught', 0)
            priorYearsExperience = request.POST.get('priorYearsExperience', 0)
            lastTaughtYear = request.POST.get('lastTaughtYear')
            remarks = request.POST.get('remarks', '')

            subject = get_object_or_404(Subject, pk=subjectId)
            
            if not lastTaughtYear:
                lastTaughtYear = None

            obj, created = InstructorLegacyExperience.objects.get_or_create(
                instructor=login.instructor,
                subject=subject,
                defaults={
                    'priorTimesTaught': priorTimesTaught,
                    'priorYearsExperience': priorYearsExperience,
                    'lastTaughtYear': lastTaughtYear,
                    'remarks': remarks
                }
            )

            if not created:
                messages.error(request, f"Legacy record for {subject.code} already exists. Please update the existing record.")
            else:
                messages.success(request, "Legacy teaching experience added successfully.")
                return redirect('instructorDashboard')

        except Exception as e:
            messages.error(request, f"Error creating record: {e}")

    return render(request, 'instructors/teachingHistory/create.html', {
        'subjects': subjects,
    })


@login_required
@has_role('instructor')
def legacyExperienceUpdate(request, experienceId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    experience = get_object_or_404(InstructorLegacyExperience, pk=experienceId, instructor=login.instructor)

    if request.method == 'POST':
        try:
            new_subject_id = request.POST.get('subject')
            
            experience.subject_id = new_subject_id
            experience.priorTimesTaught = request.POST.get('priorTimesTaught', 0)
            experience.priorYearsExperience = request.POST.get('priorYearsExperience', 0)
            
            lastTaught = request.POST.get('lastTaughtYear')
            experience.lastTaughtYear = lastTaught if lastTaught else None
            
            experience.remarks = request.POST.get('remarks', '')
            
            experience.save()
            messages.success(request, "Legacy teaching experience updated successfully.")
            return redirect('instructorDashboard')

        except Exception as e:
            messages.error(request, f"Error updating record. Ensure this subject doesn't already have a legacy entry.")

    subjects = Subject.objects.all().order_by('code')

    return render(request, 'instructors/teachingHistory/update.html', {
        'experience': experience,
        'subjects': subjects,
    })


@login_required
@has_role('instructor')
def legacyExperienceDelete(request, experienceId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return redirect('home')

    experience = get_object_or_404(InstructorLegacyExperience, pk=experienceId, instructor=login.instructor)

    if request.method == 'POST':
        experience.delete()
        messages.success(request, "Legacy experience deleted successfully.")
        return redirect('instructorDashboard')
    
    return redirect('instructorDashboard')

# ---------- Instructor Rank Configuration ----------
@login_required
@has_role('deptHead') 
def instructorRankList(request):
    ranks = InstructorRank.objects.all()
    
    return render(request, "instructors/ranks/list.html", {"ranks": ranks})


@login_required
@has_role('deptHead')
def instructorRankCreate(request):
    if request.method == "POST":
        try:
            name = request.POST.get('name').strip()
            
            data = {
                'instructionHours': int(request.POST.get('instructionHours', 0)),
                'researchHours': int(request.POST.get('researchHours', 0)),
                'extensionHours': int(request.POST.get('extensionHours', 0)),
                'productionHours': int(request.POST.get('productionHours', 0)),
                'consultationHours': int(request.POST.get('consultationHours', 0)),
                'classAdviserHours': int(request.POST.get('classAdviserHours', 0)),
            }
            
            if not name:
                messages.error(request, "Rank name cannot be empty.")
                return redirect('instructorRankCreate')

            for key, value in data.items():
                if value < 0:
                    messages.error(request, f"Hours for {key} must be non-negative.")
                    return redirect('instructorRankCreate')
            
            InstructorRank.objects.create(
                name=name,
                **data
            )
            
            messages.success(request, f"Instructor Rank '{name}' created successfully.")
            return redirect('instructorRankList')
            
        except ValueError:
            messages.error(request, "Invalid number entered for one of the hour fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/ranks/create.html")


@login_required
@has_role('deptHead')
def instructorRankUpdate(request, rankId):
    rank = get_object_or_404(InstructorRank, pk=rankId)

    if request.method == "POST":
        try:
            rank.name = request.POST.get('name').strip()
            
            rank.instructionHours = int(request.POST.get('instructionHours', rank.instructionHours))
            rank.researchHours = int(request.POST.get('researchHours', rank.researchHours))
            rank.extensionHours = int(request.POST.get('extensionHours', rank.extensionHours))
            rank.productionHours = int(request.POST.get('productionHours', rank.productionHours))
            rank.consultationHours = int(request.POST.get('consultationHours', rank.consultationHours))
            rank.classAdviserHours = int(request.POST.get('classAdviserHours', rank.classAdviserHours))

            if not rank.name:
                messages.error(request, "Rank name cannot be empty.")
                # Fall through to render
            elif any(h < 0 for h in [rank.instructionHours, rank.researchHours, rank.extensionHours, rank.productionHours, rank.consultationHours, rank.classAdviserHours]):
                messages.error(request, "All hour fields must be non-negative.")
                # Fall through to render
            else:
                rank.save()
                messages.success(request, f"Instructor Rank '{rank.name}' updated successfully.")
                return redirect('instructorRankList')

        except ValueError:
            messages.error(request, "Invalid number entered for one of the hour fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/ranks/update.html", {"rank": rank})



# ---------- Instructor Designation Configuration ----------
@login_required
@has_role('deptHead') 
def instructorDesignationList(request):
    designations = InstructorDesignation.objects.all()
    
    return render(request, "instructors/designations/list.html", {
        "designations": designations,
    })


@login_required
@has_role('deptHead')
def instructorDesignationCreate(request):
    if request.method == "POST":
        try:
            name = request.POST.get('name').strip()
            
            data = {
                'adminSupervisionHours': int(request.POST.get('adminSupervisionHours', 0)),
                'instructionHours': int(request.POST.get('instructionHours', 0)),
                'researchHours': int(request.POST.get('researchHours', 0)),
                'extensionHours': int(request.POST.get('extensionHours', 0)),
                'productionHours': int(request.POST.get('productionHours', 0)),
                'consultationHours': int(request.POST.get('consultationHours', 0)),
            }
            
            if not name:
                messages.error(request, "Designation name cannot be empty.")
                return redirect('instructorDesignationCreate')

            for key, value in data.items():
                if value < 0:
                    messages.error(request, f"Hours for {key} must be non-negative.")
                    return redirect('instructorDesignationCreate')
            
            InstructorDesignation.objects.create(
                name=name,
                **data
            )
            
            messages.success(request, f"Instructor Designation '{name}' created successfully.")
            return redirect('instructorDesignationList')
            
        except ValueError:
            messages.error(request, "Invalid number entered for one of the hour fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/designations/create.html")


@login_required
@has_role('deptHead')
def instructorDesignationUpdate(request, designationId):
    designation = get_object_or_404(InstructorDesignation, pk=designationId)

    if request.method == "POST":
        try:
            designation.name = request.POST.get('name').strip()
            
            designation.adminSupervisionHours = int(request.POST.get('adminSupervisionHours', designation.adminSupervisionHours))
            designation.instructionHours = int(request.POST.get('instructionHours', designation.instructionHours))
            designation.researchHours = int(request.POST.get('researchHours', designation.researchHours))
            designation.extensionHours = int(request.POST.get('extensionHours', designation.extensionHours))
            designation.productionHours = int(request.POST.get('productionHours', designation.productionHours))
            designation.consultationHours = int(request.POST.get('consultationHours', designation.consultationHours))

            if not designation.name:
                messages.error(request, "Designation name cannot be empty.")
            elif any(h < 0 for h in [designation.adminSupervisionHours, designation.instructionHours, designation.researchHours, designation.extensionHours, designation.productionHours, designation.consultationHours]):
                messages.error(request, "All hour fields must be non-negative.")
            else:
                designation.save()
                messages.success(request, f"Instructor Designation '{designation.name}' updated successfully.")
                return redirect('instructorDesignationList')

        except ValueError:
            messages.error(request, "Invalid number entered for one of the hour fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/designations/update.html", {
        "designation": designation,
    })


# ---------- Instructor Academic Attainment Configuration ----------
@login_required
@has_role('deptHead') 
def instructorAttainmentList(request):
    attainments = InstructorAcademicAttainment.objects.all()
    
    return render(request, "instructors/attainments/list.html", {
        "attainments": attainments,
    })

@login_required
@has_role('deptHead')
def instructorAttainmentCreate(request):
    if request.method == "POST":
        try:
            name = request.POST.get('name').strip()
            suffix = request.POST.get('suffix').strip()
            
            data = {
                'overloadUnitsHasDesignation': int(request.POST.get('overloadUnitsHasDesignation', 0)),
                'overloadUnitsNoDesignation': int(request.POST.get('overloadUnitsNoDesignation', 0)),
            }
            
            if not name:
                messages.error(request, "Attainment name cannot be empty.")
                return redirect('instructorAttainmentCreate')

            for key, value in data.items():
                if value < 0:
                    messages.error(request, f"Units must be non-negative.")
                    return redirect('instructorAttainmentCreate')
            
            InstructorAcademicAttainment.objects.create(
                name=name,
                suffix=suffix,
                **data
            )
            
            messages.success(request, f"Academic Attainment '{name}' created successfully.")
            return redirect('instructorAttainmentList')
            
        except ValueError:
            messages.error(request, "Invalid number entered for one of the unit fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/attainments/create.html")

@login_required
@has_role('deptHead')
def instructorAttainmentUpdate(request, attainmentId):
    attainment = get_object_or_404(InstructorAcademicAttainment, pk=attainmentId)

    if request.method == "POST":
        try:
            attainment.name = request.POST.get('name').strip()
            attainment.suffix = request.POST.get('suffix').strip()
            
            attainment.overloadUnitsHasDesignation = int(request.POST.get('overloadUnitsHasDesignation', attainment.overloadUnitsHasDesignation))
            attainment.overloadUnitsNoDesignation = int(request.POST.get('overloadUnitsNoDesignation', attainment.overloadUnitsNoDesignation))

            if not attainment.name:
                messages.error(request, "Attainment name cannot be empty.")
            elif attainment.overloadUnitsHasDesignation < 0 or attainment.overloadUnitsNoDesignation < 0:
                messages.error(request, "All unit fields must be non-negative.")
            else:
                attainment.save()
                messages.success(request, f"Academic Attainment '{attainment.name}' updated successfully.")
                return redirect('instructorAttainmentList')

        except ValueError:
            messages.error(request, "Invalid number entered for one of the unit fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/attainments/update.html", {
        "attainment": attainment,
    })

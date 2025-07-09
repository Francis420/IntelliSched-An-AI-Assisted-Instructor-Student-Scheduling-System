from django.shortcuts import render, redirect, get_object_or_404
from .models import College, Department, Course, Subject
from django.contrib.auth.decorators import login_required, user_passes_test



# ---------- Access Control ----------
def isSysAdmin(user):
    return user.role == 'sysAdmin'



# ---------- College ----------
@login_required
@user_passes_test(isSysAdmin)
def collegeList(request):
    colleges = College.objects.all()
    return render(request, 'core/colleges/list.html', {'colleges': colleges})

@login_required
@user_passes_test(isSysAdmin)
def collegeCreate(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        acronym = request.POST.get('acronym')
        description = request.POST.get('description')
        College.objects.create(name=name, acronym=acronym, description=description)
        return redirect('collegeList')
    return render(request, 'core/colleges/create.html')

@login_required
@user_passes_test(isSysAdmin)
def collegeUpdate(request, collegeId):
    college = get_object_or_404(College, pk=collegeId)
    if request.method == 'POST':
        college.name = request.POST.get('name')
        college.acronym = request.POST.get('acronym')
        college.description = request.POST.get('description')
        college.save()
        return redirect('collegeList')
    return render(request, 'core/colleges/update.html', {'college': college})

@login_required
@user_passes_test(isSysAdmin)
def collegeDelete(request, collegeId):
    college = get_object_or_404(College, pk=collegeId)
    if request.method == 'POST':
        college.delete()
        return redirect('collegeList')
    return render(request, 'core/colleges/delete.html', {'college': college})



# ---------- Department ----------

@login_required
@user_passes_test(isSysAdmin)
def departmentList(request):
    departments = Department.objects.select_related('college').all()
    return render(request, 'core/departments/list.html', {'departments': departments})

@login_required
@user_passes_test(isSysAdmin)
def departmentCreate(request):
    colleges = College.objects.all()
    if request.method == 'POST':
        name = request.POST.get('name')
        collegeId = request.POST.get('college')
        college = College.objects.get(pk=collegeId)
        Department.objects.create(name=name, college=college)
        return redirect('departmentList')
    return render(request, 'core/departments/create.html', {'colleges': colleges})

@login_required
@user_passes_test(isSysAdmin)
def departmentUpdate(request, departmentId):
    department = get_object_or_404(Department, pk=departmentId)
    colleges = College.objects.all()
    if request.method == 'POST':
        department.name = request.POST.get('name')
        collegeId = request.POST.get('college')
        department.college = College.objects.get(pk=collegeId)
        department.save()
        return redirect('departmentList')
    return render(request, 'core/departments/update.html', {'department': department, 'colleges': colleges})

@login_required
@user_passes_test(isSysAdmin)
def departmentDelete(request, departmentId):
    department = get_object_or_404(Department, pk=departmentId)
    if request.method == 'POST':
        department.delete()
        return redirect('departmentList')
    return render(request, 'core/departments/delete.html', {'department': department})



# ---------- Course ----------

@login_required
@user_passes_test(isSysAdmin)
def courseList(request):
    courses = Course.objects.select_related('department').all()
    return render(request, 'core/courses/list.html', {'courses': courses})

@login_required
@user_passes_test(isSysAdmin)
def courseCreate(request):
    departments = Department.objects.all()
    if request.method == 'POST':
        courseName = request.POST.get('courseName')
        acronym = request.POST.get('acronym')
        departmentId = request.POST.get('department')
        department = Department.objects.get(pk=departmentId)
        Course.objects.create(courseName=courseName, acronym=acronym, department=department)
        return redirect('courseList')
    return render(request, 'core/courses/create.html', {'departments': departments})

@login_required
@user_passes_test(isSysAdmin)
def courseUpdate(request, courseId):
    course = get_object_or_404(Course, pk=courseId)
    departments = Department.objects.all()
    if request.method == 'POST':
        course.courseName = request.POST.get('courseName')
        course.acronym = request.POST.get('acronym')
        departmentId = request.POST.get('department')
        course.department = Department.objects.get(pk=departmentId)
        course.save()
        return redirect('courseList')
    return render(request, 'core/courses/update.html', {'course': course, 'departments': departments})

@login_required
@user_passes_test(isSysAdmin)
def courseDelete(request, courseId):
    course = get_object_or_404(Course, pk=courseId)
    if request.method == 'POST':
        course.delete()
        return redirect('courseList')
    return render(request, 'core/courses/delete.html', {'course': course})



# ---------- Subject ----------

@login_required
@user_passes_test(isSysAdmin)
def subjectList(request):
    subjects = Subject.objects.select_related('course').all()
    return render(request, 'core/subjects/list.html', {'subjects': subjects})

@login_required
@user_passes_test(isSysAdmin)
def subjectCreate(request):
    courses = Course.objects.all()
    if request.method == 'POST':
        subjectCode = request.POST.get('subjectCode')
        subjectName = request.POST.get('subjectName')
        units = request.POST.get('units')
        yearLevel = request.POST.get('yearLevel')
        semester = request.POST.get('semester')
        courseId = request.POST.get('course')
        course = Course.objects.get(pk=courseId)
        Subject.objects.create(
            subjectCode=subjectCode,
            subjectName=subjectName,
            units=units,
            yearLevel=yearLevel,
            semester=semester,
            course=course
        )
        return redirect('subjectList')
    return render(request, 'core/subjects/create.html', {'courses': courses})

@login_required
@user_passes_test(isSysAdmin)
def subjectUpdate(request, subjectId):
    subject = get_object_or_404(Subject, pk=subjectId)
    courses = Course.objects.all()
    if request.method == 'POST':
        subject.subjectCode = request.POST.get('subjectCode')
        subject.subjectName = request.POST.get('subjectName')
        subject.units = request.POST.get('units')
        subject.yearLevel = request.POST.get('yearLevel')
        subject.semester = request.POST.get('semester')
        courseId = request.POST.get('course')
        subject.course = Course.objects.get(pk=courseId)
        subject.save()
        return redirect('subjectList')
    return render(request, 'core/subjects/update.html', {'subject': subject, 'courses': courses})

@login_required
@user_passes_test(isSysAdmin)
def subjectDelete(request, subjectId):
    subject = get_object_or_404(Subject, pk=subjectId)
    if request.method == 'POST':
        subject.delete()
        return redirect('subjectList')
    return render(request, 'core/subjects/delete.html', {'subject': subject})

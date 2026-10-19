from django.contrib import admin

from .models import Device, School, Classroom, Student, Class, Enrollment, VeyonActionLog, AssistanceRequest, MediaFolder, MediaAsset


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name", "code")
    ordering = ("name",)


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "school", "room_number", "capacity", "active")
    list_filter = ("school", "active")
    search_fields = ("name", "code", "room_number")
    ordering = ("school__name", "name")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "classroom", "ip_address", "device_uuid", "is_absent", "is_blocked", "active")
    list_filter = ("classroom", "active", "is_absent", "is_blocked")
    list_editable = ("ip_address",)
    search_fields = ("name", "ip_address", "hostname", "device_uuid")
    ordering = ("classroom__name", "number")
    readonly_fields = ("device_uuid",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "full_name", "active", "preferred_language", "assigned_device")
    list_filter = ("active", "preferred_language")
    search_fields = ("student_id", "full_name")
    ordering = ("full_name",)


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "grade", "section", "learning_language", "academic_year", "active")
    list_filter = ("grade", "section", "learning_language", "active")
    search_fields = ("name", "code", "grade", "section")
    ordering = ("grade", "section", "name")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "class_obj", "status", "created_at")
    list_filter = ("status", "class_obj__grade", "class_obj__section")
    search_fields = ("student__full_name", "student__student_id", "class_obj__name")
    ordering = ("-created_at",)


@admin.register(VeyonActionLog)
class VeyonActionLogAdmin(admin.ModelAdmin):
    list_display = ("action", "teacher", "classroom", "device", "success", "created_at")
    list_filter = ("action", "success", "teacher", "classroom")
    search_fields = ("teacher__username", "device__name", "device__ip_address", "error_message")
    ordering = ("-created_at",)
    readonly_fields = ("teacher", "classroom", "device", "action", "detail", "success", "error_message", "created_at")


@admin.register(AssistanceRequest)
class AssistanceRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "device", "classroom", "request_type", "status", "created_at", "resolved_by")
    list_filter = ("request_type", "status", "classroom", "resolved_by")
    search_fields = ("student__username", "device__number", "classroom__name")
    ordering = ("-created_at",)
    readonly_fields = ("student", "device", "classroom", "request_type", "status", "created_at", "resolved_at", "resolved_by")


@admin.register(MediaFolder)
class MediaFolderAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "created_by", "created_at")
    list_filter = ("created_by",)
    search_fields = ("name",)
    ordering = ["name"]


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("title", "media_type", "mime_type", "size", "content_language", "folder", "created_by", "created_at")
    list_filter = ("media_type", "content_language", "folder", "created_by")
    search_fields = ("title", "description", "mime_type")
    ordering = ["-created_at"]
    readonly_fields = ("file", "size", "mime_type", "created_at", "updated_at")

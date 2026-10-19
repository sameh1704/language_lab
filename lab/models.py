from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid


class School(models.Model):
    """المدرسة."""

    name = models.CharField(_("Name"), max_length=255, unique=True)
    code = models.CharField(_("Code"), max_length=50, unique=True)
    active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("School")
        verbose_name_plural = _("Schools")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Classroom(models.Model):
    """Classroom/Lab."""

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="classrooms",
        verbose_name=_("School"),
    )
    name = models.CharField(_("Name"), max_length=255)
    code = models.CharField(_("Code"), max_length=50, unique=True)
    room_number = models.CharField(_("Room number"), max_length=50, blank=True)
    description = models.TextField(_("Description"), blank=True)
    capacity = models.PositiveIntegerField(_("Capacity"), default=40)
    active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Classroom")
        verbose_name_plural = _("Classrooms")
        ordering = ["school__name", "name"]

    def __str__(self):
        return f"{self.school.name} - {self.name}"


class Device(models.Model):
    """Student device in the lab (number 1-40)."""

    device_uuid = models.UUIDField(
        _("Unique identifier"),
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="devices",
        verbose_name=_("Classroom"),
    )
    number = models.PositiveSmallIntegerField(
        _("Device number"),
        validators=[MinValueValidator(1), MaxValueValidator(40)],
    )
    name = models.CharField(_("Name"), max_length=60, blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    hostname = models.CharField(_("Hostname"), max_length=255, blank=True)
    last_seen = models.DateTimeField(_("Last seen"), null=True, blank=True)
    active = models.BooleanField(_("Active"), default=True)
    is_absent = models.BooleanField(_("Student absent"), default=False)
    is_blocked = models.BooleanField(_("Blocked (locked)"), default=False)

    class Meta:
        ordering = ["classroom__name", "number"]
        verbose_name = _("Device")
        verbose_name_plural = _("Devices")
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "number"],
                name="unique_device_number_per_classroom",
            ),
        ]

    def __str__(self):
        return f"{self.classroom.name} - {_('Device')} {self.number}"


class Student(models.Model):
    """Student."""

    student_id = models.CharField(_("External ID"), max_length=100, unique=True)
    full_name = models.CharField(_("Full name"), max_length=255)
    active = models.BooleanField(_("Active"), default=True)
    preferred_language = models.CharField(_("Preferred language"), max_length=50, blank=True)
    assigned_device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_students",
        verbose_name=_("Assigned device"),
    )
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Student")
        verbose_name_plural = _("Students")
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Class(models.Model):
    """Class/Grade."""

    name = models.CharField(_("Name"), max_length=255)
    code = models.CharField(_("Code"), max_length=50, unique=True)
    grade = models.CharField(_("Grade"), max_length=50)
    section = models.CharField(_("Section"), max_length=50, blank=True)
    learning_language = models.CharField(_("Learning language"), max_length=50, blank=True)
    academic_year = models.CharField(_("Academic year"), max_length=20, blank=True)
    active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Class")
        verbose_name_plural = _("Classes")
        ordering = ["grade", "section", "name"]

    def __str__(self):
        return f"{self.name} ({self.grade}{self.section and f' - {self.section}'})"


class Enrollment(models.Model):
    """Student enrollment in a class."""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name=_("Student"),
    )
    class_obj = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name=_("Class"),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=[
            ("active", _("Active")),
            ("inactive", _("Inactive")),
            ("completed", _("Completed")),
            ("dropped", _("Dropped")),
        ],
        default="active",
    )
    created_at = models.DateTimeField(_("Enrolled at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Enrollment")
        verbose_name_plural = _("Enrollments")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "class_obj"],
                name="unique_student_class_enrollment",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.full_name} - {self.class_obj.name} ({self.status})"


class VeyonActionLog(models.Model):
    """Audit log for Veyon control actions."""

    ACTION_CHOICES = [
        ("lock", _("Lock")),
        ("unlock", _("Unlock")),
        ("remote_view", _("Remote View")),
        ("remote_control", _("Remote Control")),
        ("broadcast_fullscreen", _("Broadcast Fullscreen")),
        ("broadcast_window", _("Broadcast Window")),
        ("text_message", _("Text Message")),
        ("open_website", _("Open Website")),
        ("start_app", _("Start App")),
        ("screenshot", _("Screenshot")),
        ("power_on", _("Power On")),
        ("reboot", _("Reboot")),
        ("power_down", _("Power Down")),
    ]

    teacher = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="veyon_actions",
        verbose_name=_("Teacher"),
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="veyon_actions",
        verbose_name=_("Classroom"),
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="veyon_actions",
        verbose_name=_("Device"),
    )
    action = models.CharField(_("Action"), max_length=30, choices=ACTION_CHOICES)
    detail = models.CharField(_("Detail"), max_length=255, blank=True)
    success = models.BooleanField(_("Success"), default=False)
    error_message = models.TextField(_("Error message"), blank=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Veyon action log")
        verbose_name_plural = _("Veyon action logs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} {_('on')} {self.device} {_('at')} {self.created_at:%Y-%m-%d %H:%M}"


class AssistanceRequest(models.Model):
    """Real-time student assistance request."""

    REQUEST_TYPES = [
        ("hand_raise", _("Hand Raise")),
        ("help", _("Need Help")),
    ]
    STATUS_CHOICES = [
        ("open", _("Open")),
        ("acknowledged", _("Acknowledged")),
        ("resolved", _("Resolved")),
        ("dismissed", _("Dismissed")),
    ]

    student = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="assistance_requests",
        verbose_name=_("Student"),
        blank=True,
        null=True,
        help_text=_(
            "Null when the request comes from a device-identified student "
            "page (no login); the Device and Classroom are authoritative."
        ),
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistance_requests",
        verbose_name=_("Device"),
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="assistance_requests",
        verbose_name=_("Classroom"),
    )
    request_type = models.CharField(_("Request type"), max_length=20, choices=REQUEST_TYPES)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default="open")
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    resolved_at = models.DateTimeField(_("Resolved at"), null=True, blank=True)
    resolved_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_assistance_requests",
        verbose_name=_("Resolved by"),
    )

    class Meta:
        verbose_name = _("Assistance request")
        verbose_name_plural = _("Assistance requests")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["classroom", "status", "-created_at"]),
            models.Index(fields=["student", "-created_at"]),
            models.Index(fields=["device", "-created_at"]),
        ]


class MediaFolder(models.Model):
    """مجلد في المكتبة الوسائطية."""

    name = models.CharField(_("Name"), max_length=255)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Parent folder"),
    )
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_folders",
        verbose_name=_("Created by"),
    )
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Media folder")
        verbose_name_plural = _("Media folders")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "parent"],
                name="unique_folder_name_per_parent",
            )
        ]

    def __str__(self):
        return self.name


class MediaAsset(models.Model):
    """ملف وسائطي."""

    MEDIA_TYPE_AUDIO = "audio"
    MEDIA_TYPE_VIDEO = "video"
    MEDIA_TYPE_IMAGE = "image"
    MEDIA_TYPE_PDF = "pdf"
    MEDIA_TYPE_DOCUMENT = "document"

    MEDIA_TYPES = [
        (MEDIA_TYPE_AUDIO, _("Audio")),
        (MEDIA_TYPE_VIDEO, _("Video")),
        (MEDIA_TYPE_IMAGE, _("Image")),
        (MEDIA_TYPE_PDF, _("PDF")),
        (MEDIA_TYPE_DOCUMENT, _("Document")),
    ]

    title = models.CharField(_("Title"), max_length=255)
    description = models.TextField(_("Description"), blank=True)
    file = models.FileField(_("File"), upload_to="media/%Y/%m/%d/")
    media_type = models.CharField(_("Media type"), max_length=20, choices=MEDIA_TYPES)
    mime_type = models.CharField(_("MIME type"), max_length=100)
    size = models.PositiveIntegerField(_("Size (bytes)"))
    content_language = models.CharField(_("Content language"), max_length=10, blank=True)
    folder = models.ForeignKey(
        MediaFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
        verbose_name=_("Folder"),
    )
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_assets",
        verbose_name=_("Created by"),
    )
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Media asset")
        verbose_name_plural = _("Media assets")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["media_type", "-created_at"]),
            models.Index(fields=["content_language", "-created_at"]),
            models.Index(fields=["folder", "-created_at"]),
        ]

    def __str__(self):
        return self.title

    def __str__(self):
        return f"{self.get_request_type_display()} {_('from')} {self.student} {_('in')} {self.classroom}"

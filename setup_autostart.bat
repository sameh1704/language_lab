@echo off
chcp 65001 >nul
REM ============================================
REM  تفعيل التشغيل التلقائي مع Windows
REM  ينشئ مهمة مجدولة تبدأ عند بدء التشغيل
REM ============================================

REM التحقق من صلاحية المسؤول
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [خطأ] هذا السكربت يحتاج صلاحية المسؤول.
    echo        كليك يمين عليه واختر "تشغيل كمسؤول".
    pause
    exit /b 1
)

set "TASK_NAME=LanguageLab"
set "PROJECT_DIR=%~dp0"

REM إزالة المهمة القديمة إن وُجدت
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM إنشاء المهمة الجديدة
schtasks /create /tn "%TASK_NAME%" /tr "cmd /c cd /d \"%PROJECT_DIR% && start_lab.bat" /sc onstart /rl highest /f

if %errorLevel% equ 0 (
    echo.
    echo ============================================
    echo  تم تفعيل التشغيل التلقائي
    echo  سيبدأ المعمل تلقائيًا عند بدء تشغيل Windows
    echo  لإيقافه: schtasks /delete /tn "%TASK_NAME%" /f
    echo ============================================
) else (
    echo.
    echo [فشل] تعذر إنشاء المهمة المجدولة
)

pause

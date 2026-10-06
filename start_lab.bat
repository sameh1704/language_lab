@echo off
chcp 65001 >nul
REM ============================================
REM  تشغيل معمل اللغات - وضع التشغيل الفعلي
REM  LAB_SIMULATE=0 (أوامر حقيقية إلى Veyon)
REM ============================================
setlocal

cd /d "%~dp0"

REM تفعيل الوضع الفعلي
set LAB_SIMULATE=0

REM مسار veyon-cli (عدّله إن اختلف)
if not exist "C:\Program Files\Veyon\veyon-cli.exe" (
    echo [تحذير] لم يُعثر على veyon-cli في المسار الافتراضي.
    echo          عدّل متغير البيئة VEYON_CLI إن كان في مكان آخر.
)

REM تفعيل البيئة الافتراضية إن وُجدت
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

echo ============================================
echo  معمل اللغات - تشغيل فعلي
echo  اللوحة: http://localhost:8000
echo  صفحة الطالب: http://IP:8000/student/
echo ============================================
echo.

REM تشغيل الخادم
python manage.py migrate --noinput
python manage.py runserver 0.0.0.0:8000 --noreload

endlocal

@echo off
chcp 65001 >nul
REM ============================================
REM  إعداد جدار الحماية لمعمل اللغات
REM  يشغّل بصلاحية المسؤول (Administrator)
REM ============================================

REM التحقق من صلاحية المسؤول
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [خطأ] هذا السكربت يحتاج صلاحية المسؤول.
    echo        كليك يمين عليه واختر "تشغيل كمسؤول".
    pause
    exit /b 1
)

echo ============================================
echo  إعداد جدار الحماية لمعمل اللغات
echo ============================================

REM قراءة المنفذ من المتغير أو الافتراضي 8000
set "LAB_PORT=8000"
if not "%LAB_PORT%"=="" goto :have_port
:have_port

REM فتح منفذ الخادم (الدخول)
netsh advfirewall firewall add rule name="LanguageLab Server" dir=in action=allow protocol=TCP localport=%LAB_PORT% profile=any >nul
if %errorLevel% equ 0 (
    echo [تم] فتح المنفذ %LAB_PORT% للدخول (TCP)
) else (
    echo [فشل] تعذر فتح المنفذ %LAB_PORT%
)

REM السماح بـ veyon-cli بالمرور عبر الجدار
netsh advfirewall firewall add rule name="LanguageLab Veyon" dir=out action=allow program="C:\Program Files\Veyon\veyon-cli.exe" profile=any >nul
if %errorLevel% equ 0 (
    echo [تم] السماح لـ veyon-cli بالاتصال الخارج
) else (
    echo [تحذير] تعذر إضافة قاعدة veyon-cli (قد لا يكون مثبتًا بعد)
)

REM السماح لخدمة Veyon بالاستماع (المنفذ 11100)
netsh advfirewall firewall add rule name="LanguageLab Veyon Service" dir=in action=allow protocol=TCP localport=11100 profile=any >nul
if %errorLevel% equ 0 (
    echo [تم] فتح المنفذ 11100 للدخول (خدمة Veyon)
) else (
    echo [فشل] تعذر فتح المنفذ 11100
)

echo.
echo ============================================
echo  اكتمل إعداد جدار الحماية
echo ============================================
pause

@echo off
setlocal

REM Update these paths for the target Windows machine.
set ODOO_ROOT=E:\Odoo Setup\server
set ODOO_PYTHON=E:\Odoo Setup\python\python.exe
set ODOO_CONF=E:\Odoo Setup\aimaze_laundry_erp\Clients\GoldVerse Premium Laundry\goldverse_premium_laundry.conf

cd /d "%ODOO_ROOT%"
"%ODOO_PYTHON%" "%ODOO_ROOT%\odoo-bin" -c "%ODOO_CONF%"

endlocal

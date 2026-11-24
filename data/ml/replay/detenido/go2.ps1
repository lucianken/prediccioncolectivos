$py="C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe"
$d="c:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos"
$b="$d\data\ml\replay\detenido"
$env:GROUP="2"
$p=Start-Process -FilePath $py -ArgumentList @("`"$b\extrae.py`"","`"$b\run2`"","-","-","3") -WorkingDirectory $b -RedirectStandardOutput "$b\run2.log" -RedirectStandardError "$b\run2.err" -PassThru -WindowStyle Hidden
$k=Start-Process -FilePath $py -ArgumentList @("-m","prediccion.scripts.keep_awake","$($p.Id)") -WorkingDirectory $d -RedirectStandardOutput "$b\keep2.log" -RedirectStandardError "$b\keep2.err" -PassThru -WindowStyle Hidden
Start-Sleep 15
"pid $($p.Id)"; Get-Content "$b\keep2.log"

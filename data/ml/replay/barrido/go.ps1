$py="C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe"
$d="c:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos"
$b="$d\data\ml\replay\barrido"
$env:GROUP="2"
$p=Start-Process -FilePath $py -ArgumentList @("`"$b\barrido_sentido.py`"","`"$b\run`"","`"@$b\cfgs.txt`"","-","-","6") -WorkingDirectory $b -RedirectStandardOutput "$b\run.log" -RedirectStandardError "$b\run.err" -PassThru -WindowStyle Hidden
$k=Start-Process -FilePath $py -ArgumentList @("-m","prediccion.scripts.keep_awake","$($p.Id)") -WorkingDirectory $d -RedirectStandardOutput "$b\keep.log" -RedirectStandardError "$b\keep.err" -PassThru -WindowStyle Hidden
Start-Sleep 10
"pid $($p.Id)"; Get-Content "$b\keep.log"

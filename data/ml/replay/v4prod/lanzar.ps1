# uso: lanzar.ps1 -Out <dir> -Model <export> -Lines <csv> -Days <csv> -Workers N [-Stops 40]
param($Out,$Model,$Lines,$Days,$Workers=3,$Stops=40,$Tag="run")
$PY="C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location "C:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos"
$env:PYTHONPATH="."
$log="data\ml\replay\v4prod\$Tag"
$p=Start-Process $PY -ArgumentList "-u","data/ml/replay/v4prod/run_idle.py","--model",$Model,"--variants","base","--lines",$Lines,"--days",$Days,"--stops",$Stops,"--out",$Out,"--workers",$Workers -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log.log" -RedirectStandardError "$log.err"
$p.PriorityClass='Idle'; $p.ProcessorAffinity=255
$k=Start-Process $PY -ArgumentList "prediccion/scripts/keep_awake.py",$p.Id -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log.keep.log" -RedirectStandardError "$log.keep.err"
$k.PriorityClass='Idle'; $k.ProcessorAffinity=255
"pid=$($p.Id) keep=$($k.Id)"

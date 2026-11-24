# uso: lanzar.ps1 -Days <csv> -Lines <csv> -Workers N -Tag nombre
param($Days,$Lines="39,42,92,168,152",$Workers=2,$Tag="run")
$PY="C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location "C:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos"
$env:PYTHONPATH="."
$log="data\ml\replay\cuandosubo\$Tag"
$p=Start-Process $PY -ArgumentList "-u","-m","prediccion.replay.cuandosubo_cmp","--days",$Days,"--lines",$Lines,"--workers",$Workers,"--out","data/ml/replay/cuandosubo/run" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log.log" -RedirectStandardError "$log.err"
$p.PriorityClass='Idle'; $p.ProcessorAffinity=255
$k=Start-Process $PY -ArgumentList "prediccion/scripts/keep_awake.py",$p.Id -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log.keep.log" -RedirectStandardError "$log.keep.err"
$k.PriorityClass='Idle'; $k.ProcessorAffinity=255
"pid=$($p.Id) keep=$($k.Id)"

param($Lines="")
$PY="C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location "C:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos"
$env:PYTHONPATH="."
$a=@("-u","data/ml/replay/v4prod/reporte.py"); if($Lines){$a+=$Lines}
$p=Start-Process $PY -ArgumentList $a -WindowStyle Hidden -PassThru -RedirectStandardOutput data\ml\replay\v4prod\rep.log -RedirectStandardError data\ml\replay\v4prod\rep.err
$p.PriorityClass='Idle'; $p.ProcessorAffinity=0x5555
$p.WaitForExit()

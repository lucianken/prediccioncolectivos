$PY="C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location "C:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos"
$p=Start-Process $PY -ArgumentList "-u","data/ml/v4_eval_ext/build_and_eval.py" -WindowStyle Hidden -PassThru -RedirectStandardOutput data\ml\v4_eval_ext\run.log -RedirectStandardError data\ml\v4_eval_ext\run.err
$p.PriorityClass='Idle'; $p.ProcessorAffinity=255
$k=Start-Process $PY -ArgumentList "prediccion/scripts/keep_awake.py",$p.Id -WindowStyle Hidden -PassThru -RedirectStandardOutput data\ml\v4_eval_ext\keep.log -RedirectStandardError data\ml\v4_eval_ext\keep.err
$k.PriorityClass='Idle'; $k.ProcessorAffinity=255
"pid=$($p.Id)"

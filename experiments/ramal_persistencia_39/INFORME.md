# Persistencia de ramal, linea 39 (7 dias: 15-18,21 sep habiles; 19 sab; 20 dom)
Verdad: shape asignado ex post por pipeline (v4 trips). ramal A=382202/3, B=382208/9, C=382210/11; sentido por nombre del shape (Barracas->=ida).
```
n viajes 39 con shape: 5635 | coche-dias: 577 | por dia: {'2026-09-15': 965, '2026-09-16': 972, '2026-09-17': 960, '2026-09-18': 966, '2026-09-19': 632, '2026-09-20': 471, '2026-09-21': 669}

## 1 Base
dist ramal global: {'C': 0.363, 'B': 0.325, 'A': 0.311}
acierto global (ramal mas frecuente): 0.363 n 5635
por sentido x franja (acierto, n):
  ('ida', '0-5') 0.407 396
  ('ida', '6-9') 0.405 692
  ('ida', '10-15') 0.374 805
  ('ida', '16-20') 0.374 633
  ('ida', '21-23') 0.379 269
  ('vuelta', '0-5') 0.401 334
  ('vuelta', '6-9') 0.336 670
  ('vuelta', '10-15') 0.348 807
  ('vuelta', '16-20') 0.398 704
  ('vuelta', '21-23') 0.378 325
acierto ponderado sentido x franja (in-sample): 0.377

## 2 Persistencia: P(ramal=ramal previo)
general 0.357 n 5058

## sentido previo vs actual
          mean  size
opuesto             
mismo    0.591   110
opuesto  0.352  4948

## posicion del viaje (8=8+)
       mean  size
posb             
2     0.361   563
3     0.359   554
4     0.350   548
5     0.345   536
6     0.371   520
7     0.366   481
8     0.355  1856

## habil/sabado/domingo
       mean  size
tipo             
D     0.410   415
H     0.345  4081
S     0.411   562

## habil vs finde
        mean  size
fin               
finde  0.410   977
habil  0.345  4081

## opuesto x habil/finde
                mean  size
opuesto fin               
mismo   finde  0.000     2
        habil  0.602   108
opuesto finde  0.411   975
        habil  0.338  3973

base mismos viajes (A mas frec): 0.365

## 3 Consistencia intra-dia
coche-dias con >=2 viajes: 563 | un solo ramal: 0.007
coche-dias >=4 viajes: 548 un solo ramal: 0.002
distrib ramales distintos/coche-dia: {1: 4, 2: 71, 3: 488}
cambios de ramal por coche-dia: media 5.77 dist {0: 4, 1: 16, 2: 30, 3: 45, 4: 72, 5: 85, 6: 96, 7: 77, 8: 61, 9: 50, 10: 24, 11: 2, 12: 1}
cambios por transicion:  0.643
P(igual) si independiente (sum p^2): 0.335

## 4 Transicion ramal previo -> siguiente (n; fila %)
r     A    B    C
rp               
A   535  469  545
B   535  548  576
C   510  616  724
r       A      B      C
rp                     
A   0.345  0.303  0.352
B   0.322  0.330  0.347
C   0.276  0.333  0.391
```


# Verificacion (24, 25 y 26 sep 2026; 2 habiles + sabado)
Scripts: verif39.py (corre con PYTHONPATH=. desde prediccion colectivos), r39.py (analisis inicial). Salida cruda: verif39_out.txt. Ramal CuandoSubo = route_id mas frecuente del viaje -> ROUTE_AGENCY_MAP.json (copia 2026-11-13) -> terna -> ramal_cuandosubo.json -> shape_ids (solo si todos son del mismo ramal).
Limite: el ramal A no tiene tramo exclusivo (a >=100 m de B y C) en ninguno de sus viajes, asi que "confirmado" solo existe para B y C (A 0/705).
```
dias ['2026-09-24', '2026-09-25', '2026-09-26'] | viajes 39 con shape: 2096 | con ramal CuandoSubo resuelto a ramal unico: 1750

### 1 Calidad etiqueta (ping exclusivo = a <=40 m del ramal y >=100 m de los otros; confirmado = >=3 pings exclusivos del ramal asignado)
viajes confirmados: 1295 de 2096 0.618
confirmados por ramal (media, n): {'A': {'mean': 0.0, 'size': 705}, 'B': {'mean': 0.888, 'size': 668}, 'C': {'mean': 0.971, 'size': 723}}
fraccion de pings del viaje en tramo exclusivo propio: mediana 0.082 | viajes con >=3 pings exclusivos de OTRO ramal: 2

TODOS (pipeline, 3 dias): pares 1850 | P(igual previo) 0.354 | base mas frecuente 0.343 | sentido opuesto 0.350 (n 1716) | mismo sentido 0.403 (n 134)
r     A    B    C
rp               
A   218  188  204
B   192  203  198
C   222  192  233
r       A      B      C
rp                     
A   0.357  0.308  0.334
B   0.324  0.342  0.334
C   0.343  0.297  0.360

PARES CONFIRMADOS (viaje y previo inmediato ambos confirmados): pares 726 | P(igual previo) 0.530 | base mas frecuente 0.548 | sentido opuesto 0.528 (n 706) | mismo sentido 0.600 (n 20)
r     B    C
rp          
B   158  171
C   170  227
r       B      C
rp              
B   0.480  0.520
C   0.428  0.572
consistencia todos: coche-dias >=2 viajes 234 | un solo ramal 0.004 | 3 ramales 0.816
consistencia solo viajes confirmados: coche-dias >=2 viajes 224 | un solo ramal 0.076 | 3 ramales 0.000

### 2 Contraste CuandoSubo (route_id -> ramal)
viajes con ramal CS: 1750 de 2096 0.835 | acuerdo pipeline-CS: 0.907 | solo confirmados: 0.985 n 1131
matriz pipeline (fila) vs CS (col):
csr    A    B    C
r                 
A    402   87   55
B      5  579    1
C      6    9  606
acuerdo por dia: {'2026-09-24': np.float64(0.916), '2026-09-25': np.float64(0.879), '2026-09-26': np.float64(0.942)}

CUANDOSUBO como verdad (viajes con CS; previo = previo inmediato con CS): pares 1506 | P(igual previo) 0.368 | base mas frecuente 0.380 | sentido opuesto 0.373 (n 1367) | mismo sentido 0.317 (n 139)
csr    A    B    C
rp                
A     78  147  128
B    128  241  209
C    156  184  235
csr      A      B      C
rp                      
A    0.221  0.416  0.363
B    0.221  0.417  0.362
C    0.271  0.320  0.409
consistencia CS: coche-dias >=2 viajes 233 | un solo ramal 0.004 | 3 ramales 0.712
```
